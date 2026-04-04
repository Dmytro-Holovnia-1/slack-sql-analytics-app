"""
Slack event handlers and graph-reply orchestration.

Public API
----------
``BotHandlers(graph, settings).register(app)``
    Preferred class-based entry-point with explicit dependency injection.

``register_handlers(app, graph, settings)``
    Thin shim for backward compatibility.

Every Bolt entry-point acks Slack immediately, then delegates all heavy work
to ``BotHandlers._post_reply`` via a safe background task.
"""

import asyncio
from typing import Any

from loguru import logger
from slack_bolt import BoltContext
from slack_bolt.async_app import AsyncApp
from slack_bolt.middleware.assistant.async_assistant import AsyncAssistant
from slack_sdk.web.async_client import AsyncWebClient

from app.config import Settings
from app.graph.messages import user_message

from .utils import build_thread_context_key, extract_user_text, get_channel, is_transient_error

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maps LangGraph node names → set_status kwargs.
# Add entries here when the graph topology changes — no logic required.
_NODE_STATUS: dict[str, dict[str, Any]] = {
    "intent_router_node": {"status": "Thinking..."},
    "sql_expert_node": {
        "status": "Generating SQL...",
        "loading_messages": ["Analyzing your question...", "Planning the query..."],
    },
    "sql_executor_node": {
        "status": "Querying database...",
        "loading_messages": [
            "Running your SQL query...",
            "Crunching the numbers...",
            "Almost there...",
        ],
    },
    "sql_repair_node": {"status": "Fixing query..."},
    "result_formatter_node": {
        "status": "Generating answer...",
        "loading_messages": ["Formatting the results...", "Preparing your answer..."],
    },
    "meta_analyst_node": {"status": "Analyzing context and schema..."},
}

_TRANSIENT_ERROR_MSG = "The AI service is temporarily unavailable. Please try again in a moment."

# ---------------------------------------------------------------------------
# Module-level utilities (stateless, not tied to any instance)
# ---------------------------------------------------------------------------


async def _noop_set_status(status: str, **_kwargs: Any) -> None:
    """No-op coroutine used in place of AsyncSetStatus outside Assistant threads."""


async def _update_status_for_chain_start(name: str, set_status: Any) -> None:
    """Call set_status with the kwargs mapped to *name* in _NODE_STATUS, if any."""
    if config := _NODE_STATUS.get(name):
        await set_status(**config)


def _log_task_exception(task: asyncio.Task) -> None:
    """Done-callback: log unhandled task exceptions instead of silently dropping them."""
    if not task.cancelled() and (exc := task.exception()):
        logger.error("Unhandled error in background task: {}", exc, exc_info=exc)


def _create_safe_task(coro: Any) -> asyncio.Task:
    """Schedule *coro* as a fire-and-forget task with automatic error logging."""
    task = asyncio.create_task(coro)
    task.add_done_callback(_log_task_exception)
    return task


# ---------------------------------------------------------------------------
# BotHandlers
# ---------------------------------------------------------------------------


class BotHandlers:
    """Encapsulates graph and settings; registers all Slack event handlers."""

    def __init__(self, graph: Any, settings: Settings) -> None:
        """Store graph and settings as instance dependencies."""
        self._graph = graph
        self._settings = settings

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, app: AsyncApp) -> None:
        """Wire all Slack listeners onto *app*."""
        self._register_assistant(app)
        app.event("assistant_thread_started")(self._handle_assistant_thread_started)
        app.event("app_mention")(self._handle_app_mention)
        app.event("message")(self._handle_direct_message)
        logger.info("Slack event handlers registered")

    def _register_assistant(self, app: AsyncApp) -> None:
        """Register the AsyncAssistant side-panel handler; no-op if unsupported."""
        try:
            assistant = AsyncAssistant()
            app.assistant(assistant)
            assistant.user_message(self._handle_assistant_message)
            logger.info("Assistant handler registered")
        except Exception as e:
            logger.warning("Could not register Assistant handler: {}", e)

    # ------------------------------------------------------------------
    # Bolt event handlers
    # ------------------------------------------------------------------

    async def _handle_assistant_message(
        self,
        payload: dict,
        ack: Any,
        set_status: Any,
        client: AsyncWebClient,
        context: BoltContext,
    ) -> None:
        """Ack immediately; dispatch graph reply with the real set_status."""
        logger.info("Assistant user message in channel={}", context.channel_id)
        await ack()
        _create_safe_task(self._post_reply(payload, set_status, client, context))

    async def _handle_assistant_thread_started(self, event: dict, ack: Any) -> None:
        """Ack the panel-open lifecycle event; no further action needed."""
        await ack()
        logger.info("Assistant thread started for channel={}", get_channel(event))

    async def _handle_app_mention(self, event: dict, client: AsyncWebClient, ack: Any, context: BoltContext) -> None:
        """Ack and dispatch; _noop_set_status replaces unavailable AsyncSetStatus."""
        logger.info("App mention in channel={}", get_channel(event, context))
        await ack()
        _create_safe_task(self._post_reply(event, _noop_set_status, client, context))

    async def _handle_direct_message(self, event: dict, client: AsyncWebClient, ack: Any, context: BoltContext) -> None:
        """Handle human DMs only; best-effort typing indicator via assistant_threads_setStatus."""
        if event.get("channel_type") != "im" or event.get("bot_id"):
            await ack()
            return

        channel = get_channel(event, context)
        thread_ts = event.get("thread_ts") or event.get("ts")
        logger.info("Direct message in channel={}", channel)
        await ack()

        async def _status_updater(status: str, **_kwargs: Any) -> None:
            """Call assistant_threads_setStatus; swallow errors at DEBUG level."""
            if not thread_ts:
                return
            try:
                await client.assistant_threads_setStatus(
                    channel_id=channel,
                    thread_ts=thread_ts,
                    status=status,
                )
            except Exception as exc:
                logger.debug("Status update skipped for channel={}: {}", channel, exc)

        _create_safe_task(self._post_reply(event, _status_updater, client, context))

    # ------------------------------------------------------------------
    # Graph orchestration
    # ------------------------------------------------------------------

    async def _post_reply(
        self,
        event: dict[str, Any],
        set_status: Any,
        client: AsyncWebClient,
        context: BoltContext,
    ) -> None:
        """Run the full request-reply cycle: sanitise → stream graph → dispatch."""
        channel = get_channel(event, context)
        thread_ts = event.get("thread_ts") or event.get("ts")
        logger.info("Processing message from channel={}, thread_ts={}", channel, thread_ts)

        reply_kwargs: dict[str, Any] = {"channel": event["channel"]}
        if thread_ts:
            reply_kwargs["thread_ts"] = thread_ts

        result: dict | None = None
        try:
            user_text = extract_user_text(event)
            thread_id = build_thread_context_key(event)
            logger.debug("Graph invocation: thread_id={}, user_text='{}'", thread_id, user_text)

            result, intent = await self._stream_graph(user_text, thread_id, channel, set_status)

            reply_text = (
                (result.get("formatted_response") or "").strip() or self._settings.fallback_text
                if result
                else self._settings.fallback_text
            )
            logger.info(
                "Graph completed: channel={}, intent={}, response_length={}",
                channel,
                intent,
                len(reply_text),
            )
            logger.debug("Graph result: {}", result)

        except Exception as e:
            error_msg = str(e)
            logger.error(
                "Error processing graph reply for channel={}: {}",
                channel,
                error_msg,
                exc_info=True,
            )
            result = None
            reply_text = _TRANSIENT_ERROR_MSG if is_transient_error(error_msg) else self._settings.fallback_text

        await self._dispatch_reply(client, reply_kwargs, result, reply_text)
        logger.info("Reply posted to channel={}", channel)

    async def _stream_graph(
        self,
        user_text: str,
        thread_id: str,
        channel: str,
        set_status: Any,
    ) -> tuple[dict | None, str]:
        """
        Stream LangGraph v2 events, updating Slack status on each chain start.

        Returns ``(result, intent)`` where *result* is the first output dict
        containing ``"formatted_response"``, or ``None``. Re-raises on error.
        """
        result: dict | None = None
        try:
            async for ev in self._graph.astream_events(
                {"messages": [user_message(user_text)]},
                config={"configurable": {"thread_id": thread_id}},
                version="v2",
            ):
                name = ev.get("name", "")
                etype = ev["event"]
                logger.debug("Graph event: name={}, event={}", name, etype)

                if etype == "on_chain_start":
                    await _update_status_for_chain_start(name, set_status)
                elif etype == "on_chain_end":
                    output = ev.get("data", {}).get("output")
                    if isinstance(output, dict) and "formatted_response" in output:
                        result = output

        except Exception as e:
            logger.error("Graph streaming failed for channel={}: {}", channel, e)
            raise

        return result, (result.get("intent", "unknown") if result else "unknown")

    @staticmethod
    async def _dispatch_reply(
        client: AsyncWebClient,
        reply_kwargs: dict[str, Any],
        result: dict | None,
        reply_text: str,
    ) -> None:
        """Post a plain message or upload a SQL/CSV artefact with *reply_text* as comment."""
        artifact_format = result.get("artifact_format") if result else None

        if artifact_format in {"sql", "csv"} and result:
            logger.info(
                "Uploading artifact: format={}, title={}",
                artifact_format,
                result.get("artifact_title"),
            )
            await client.files_upload_v2(
                **reply_kwargs,
                content=result["artifact_content"],
                title=result["artifact_title"],
                filename=result["artifact_title"],
                initial_comment=reply_text,
            )
        else:
            logger.debug("Posting text reply")
            await client.chat_postMessage(**reply_kwargs, text=reply_text)
