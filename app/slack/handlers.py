"""
Slack event handlers and graph-reply orchestration.

Entry-point
-----------
``register_handlers(app, graph, settings)``
    Wires all Slack listeners onto an :class:`~slack_bolt.async_app.AsyncApp`.

Internal flow
~~~~~~~~~~~~~
Every user-facing entry-point (DM, ``@mention``, AI-Assistant thread) calls
:func:`post_graph_reply` inside an ``asyncio`` background task so that Slack's
3-second acknowledgement deadline is always met before graph execution begins.

``post_graph_reply`` sanitises the message text, maps it to a LangGraph
thread ID, streams the graph via ``astream_events``, and posts the final reply
(plain text or an uploaded SQL/CSV artefact) back to the originating channel.
"""

import asyncio
import re
from typing import Any

from loguru import logger
from slack_bolt import BoltContext
from slack_bolt.async_app import AsyncApp
from slack_bolt.middleware.assistant.async_assistant import AsyncAssistant
from slack_sdk.web.async_client import AsyncWebClient

from app.config import Settings
from app.graph.messages import user_message

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MENTION_RE = re.compile(r"<@[^>]+>")

#: Maps LangGraph node names to keyword-arguments forwarded to ``set_status``.
#: Add or edit entries here when the graph topology changes — no logic needed.
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

#: Lowercase substrings that identify a transient upstream failure.
_TRANSIENT_ERROR_TOKENS: tuple[str, ...] = ("503", "unavailable", "resource_exhausted")
_TRANSIENT_ERROR_MSG = "The AI service is temporarily unavailable. Please try again in a moment."


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def build_thread_context_key(event: dict[str, Any]) -> str:
    """
    Build a deterministic LangGraph thread ID from a Slack event payload.

    Combines the channel ID and thread/message timestamp into a stable string
    key used to scope per-conversation graph memory across requests.

    Args:
        event: Slack event payload.  Uses ``channel_id`` or ``channel`` for the
            channel and ``thread_ts`` or ``ts`` for the timestamp.

    Returns:
        A string of the form ``"<channel>-<ts>"``,
        e.g. ``"C0123456789-1700000000.000100"``.
    """
    channel = event.get("channel_id") or event.get("channel") or "unknown-channel"
    thread_ts = event.get("thread_ts") or event.get("ts") or "unknown-ts"
    return f"{channel}-{thread_ts}"


def extract_user_text(event: dict[str, Any] | str | None) -> str:
    """
    Return sanitised user text from a Slack event or raw string.

    Strips all ``<@USERID>`` mention tokens so the graph receives clean
    natural-language input without Slack formatting artefacts.

    Args:
        event: A Slack event dict with a ``"text"`` key, a plain string, or
            ``None``.  Any falsy value yields an empty string.

    Returns:
        Whitespace-trimmed text with mention tokens removed.
    """
    raw = event if isinstance(event, str) else (event or {}).get("text")
    return MENTION_RE.sub("", (raw or "").strip()).strip()


def _get_channel(event: dict[str, Any], context: BoltContext | None = None) -> str:
    """
    Resolve the Slack channel ID with a safe sentinel fallback.

    Prefers ``BoltContext.channel_id`` over the raw event fields to take
    advantage of Bolt's normalisation layer.

    Args:
        event: Slack event payload dict.
        context: Optional ``BoltContext``; its ``channel_id`` is used when set.

    Returns:
        Channel ID string, or ``"unknown"`` if none could be resolved.
    """
    return (context.channel_id if context else None) or event.get("channel_id") or event.get("channel") or "unknown"


def _is_transient_error(message: str) -> bool:
    """
    Return ``True`` when *message* signals a transient upstream failure.

    Performs a case-insensitive substring search against
    ``_TRANSIENT_ERROR_TOKENS`` (HTTP 503, gRPC UNAVAILABLE, resource exhausted).

    Args:
        message: Stringified exception message.

    Returns:
        ``True`` if the error is likely transient and worth retrying.
    """
    lower = message.lower()
    return any(token in lower for token in _TRANSIENT_ERROR_TOKENS)


# ---------------------------------------------------------------------------
# Background-task safety
# ---------------------------------------------------------------------------


def _log_task_exception(task: asyncio.Task) -> None:
    """
    Done-callback that logs unhandled exceptions from fire-and-forget tasks.

    Attach to every task created via ``asyncio.create_task`` so that
    exceptions are never silently swallowed by the event loop.

    Args:
        task: The completed ``asyncio.Task`` instance.
    """
    if not task.cancelled() and (exc := task.exception()):
        logger.error("Unhandled error in background task: {}", exc, exc_info=exc)


def _create_safe_task(coro: Any) -> asyncio.Task:
    """
    Schedule a coroutine as a background task with automatic error logging.

    Wraps ``asyncio.create_task`` and attaches :func:`_log_task_exception` so
    that unhandled exceptions are logged rather than silently discarded by the
    event loop.

    Args:
        coro: Awaitable coroutine to schedule.

    Returns:
        The created ``asyncio.Task``.
    """
    task = asyncio.create_task(coro)
    task.add_done_callback(_log_task_exception)
    return task


# ---------------------------------------------------------------------------
# Status-update helpers
# ---------------------------------------------------------------------------


async def _noop_set_status(status: str, **_kwargs: Any) -> None:
    """
    No-op coroutine compatible with the ``AsyncSetStatus`` interface.

    Used as a placeholder when status updates are unavailable or unwanted,
    e.g. for ``app_mention`` events that run outside the AI-Assistant context.

    Args:
        status: Ignored status string.
        **_kwargs: Additional keyword arguments accepted for interface
            compatibility with ``AsyncSetStatus``.
    """


async def _update_status_for_chain_start(name: str, set_status: Any) -> None:
    """
    Forward a LangGraph ``on_chain_start`` event to the Slack status indicator.

    Looks up *name* in :data:`_NODE_STATUS` and calls ``set_status`` with the
    corresponding kwargs.  Unrecognised node names are silently ignored so that
    new nodes added to the graph do not require changes here.

    Args:
        name: LangGraph node name from the streaming event.
        set_status: Async callable compatible with ``AsyncSetStatus``
            (or a no-op coroutine for non-Assistant contexts).
    """
    if config := _NODE_STATUS.get(name):
        await set_status(**config)


# ---------------------------------------------------------------------------
# Graph streaming
# ---------------------------------------------------------------------------


async def _stream_graph(
    graph: Any,
    user_text: str,
    thread_id: str,
    channel: str,
    set_status: Any,
) -> tuple[dict | None, str]:
    """
    Drive the LangGraph ``astream_events`` loop and collect the final output.

    Iterates over LangGraph v2 streaming events:

    * ``on_chain_start``  → updates the Slack typing indicator via
      :func:`_update_status_for_chain_start`.
    * ``on_chain_end``    → captures the first output dict that contains a
      ``"formatted_response"`` key as the canonical final result.

    Any exception is logged and re-raised so that :func:`post_graph_reply`
    can apply user-friendly fallback logic.

    Args:
        graph: Compiled ``CompiledStateGraph`` instance supporting
            ``astream_events``.
        user_text: Sanitised user message submitted as the first graph message.
        thread_id: LangGraph ``thread_id`` config value for memory scoping.
        channel: Channel ID used only for structured error logging.
        set_status: Async status-update callable forwarded to
            :func:`_update_status_for_chain_start`.

    Returns:
        ``(result, intent)`` where *result* is the first output dict containing
        ``"formatted_response"``, or ``None``; and *intent* is
        ``result["intent"]`` or ``"unknown"``.

    Raises:
        Exception: Re-raises any exception emitted during graph streaming.
    """
    result: dict | None = None

    try:
        async for ev in graph.astream_events(
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


# ---------------------------------------------------------------------------
# Reply dispatch
# ---------------------------------------------------------------------------


async def _dispatch_reply(
    client: AsyncWebClient,
    reply_kwargs: dict[str, Any],
    result: dict | None,
    reply_text: str,
) -> None:
    """
    Post the reply to Slack, uploading a file when an artefact is present.

    When *result* signals a SQL or CSV artefact (``artifact_format`` ∈
    ``{"sql", "csv"}``), uploads the content via ``files_upload_v2`` with
    *reply_text* as the initial comment.  Otherwise posts a plain
    ``chat_postMessage``.

    Args:
        client: ``AsyncWebClient`` instance for all Web API calls.
        reply_kwargs: Base keyword-arguments for the API call (``channel`` and
            optionally ``thread_ts``).
        result: Graph output dict, or ``None`` on error/fallback.
        reply_text: The final reply text shown to the user.
    """
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


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------


async def post_graph_reply(
    event: dict[str, Any],
    set_status: Any,
    client: AsyncWebClient,
    context: BoltContext,
    graph: Any,
    settings: Settings,
) -> None:
    """
    Orchestrate the full request-reply cycle for a single Slack message.

    Performs the following steps in order:

    1. Resolve channel and thread coordinates from context and event.
    2. Sanitise user text and build the LangGraph thread ID.
    3. Stream the graph and collect the formatted response via
       :func:`_stream_graph`.
    4. Resolve the reply text, falling back to ``settings.fallback_text`` when
       the graph produces no output.
    5. Classify errors: transient upstream failures (503, UNAVAILABLE,
       resource_exhausted) surface a user-friendly retry message; all other
       errors fall back to ``settings.fallback_text``.
    6. Dispatch the reply via :func:`_dispatch_reply` (plain message or artefact
       upload).

    Args:
        event: Raw Slack event payload.  Must contain ``"channel"`` as the post
            target; ``"thread_ts"`` / ``"ts"`` are used to thread replies.
        set_status: Async status-update callable (``AsyncSetStatus`` from Slack
            Bolt's Assistant middleware, or :func:`_noop_set_status`).
        client: ``AsyncWebClient`` used for all Web API calls.
        context: ``BoltContext`` providing ``channel_id`` and other
            request-scoped values.
        graph: Compiled LangGraph instance.
        settings: Application settings; ``settings.fallback_text`` is used when
            the graph produces no usable output.
    """
    channel = _get_channel(event, context)
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

        result, intent = await _stream_graph(
            graph=graph,
            user_text=user_text,
            thread_id=thread_id,
            channel=channel,
            set_status=set_status,
        )

        reply_text = (
            (result.get("formatted_response") or "").strip() or settings.fallback_text
            if result
            else settings.fallback_text
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
        reply_text = _TRANSIENT_ERROR_MSG if _is_transient_error(error_msg) else settings.fallback_text

    await _dispatch_reply(client, reply_kwargs, result, reply_text)
    logger.info("Reply posted to channel={}", channel)


# ---------------------------------------------------------------------------
# Handler registration
# ---------------------------------------------------------------------------


def register_handlers(app: AsyncApp, graph: Any, settings: Settings) -> None:
    """
    Register all Slack event listeners on *app*.

    Wires up four entry-points for receiving user messages:

    - **AI Assistant side panel** (``AsyncAssistant.user_message``): messages
      sent inside the native Slack AI Assistant tab.  Registration is wrapped in
      a try/except because this requires the ``assistants:write`` scope and a
      compatible Slack plan; the app starts normally without it.
    - **``assistant_thread_started``**: lifecycle acknowledgement when the
      Assistant panel is opened (no further action required).
    - **``app_mention``**: ``@BotName`` mentions in public/private channels and
      group DMs.
    - **``message``** (DM only): direct messages (``channel_type=im``), with
      bot-message filtering and a best-effort typing-indicator update via
      ``assistant_threads_setStatus``.

    All heavy processing is dispatched via :func:`_create_safe_task` so that
    Slack's 3-second acknowledgement deadline is always met.

    Args:
        app: Initialised ``AsyncApp`` instance to register listeners on.
        graph: Compiled LangGraph instance forwarded to
            :func:`post_graph_reply` on every incoming message.
        settings: Application settings forwarded to :func:`post_graph_reply`.
    """

    # -- AI Assistant side panel -------------------------------------------
    try:
        assistant = AsyncAssistant()
        app.assistant(assistant)

        @assistant.user_message
        async def handle_assistant_user_message(
            payload: dict,
            ack: Any,
            set_status: Any,
            client: AsyncWebClient,
            context: BoltContext,
        ) -> None:
            """
            Handle user messages posted inside the Slack AI Assistant panel.

            Acknowledges immediately to satisfy Slack's 3-second deadline, then
            spawns a background task for the full graph reply cycle.  The
            injected ``set_status`` callable is forwarded so that typed status
            indicators (e.g. "Generating SQL…") appear in the panel while the
            graph runs.

            Args:
                payload: Raw event payload for the user message.
                ack: Bolt acknowledgement callable; must be awaited promptly.
                set_status: ``AsyncSetStatus`` utility from the Assistant
                    middleware for updating the typing indicator text.
                client: ``AsyncWebClient`` for Web API calls.
                context: ``BoltContext`` providing ``channel_id``.
            """
            logger.info("Assistant user message in channel={}", context.channel_id)
            await ack()
            _create_safe_task(
                post_graph_reply(
                    event=payload,
                    set_status=set_status,
                    client=client,
                    context=context,
                    graph=graph,
                    settings=settings,
                )
            )

        logger.info("Assistant handler registered")
    except Exception as e:
        logger.warning("Could not register Assistant handler: {}", e)

    # -- Assistant thread lifecycle ----------------------------------------
    @app.event("assistant_thread_started")
    async def handle_assistant_thread_started(event: dict, ack: Any) -> None:
        """
        Acknowledge the lifecycle event fired when an Assistant panel opens.

        No further action is required; the actual conversation begins with the
        first ``user_message`` event.

        Args:
            event: Slack ``assistant_thread_started`` payload.
            ack: Bolt acknowledgement callable.
        """
        await ack()
        logger.info("Assistant thread started for channel={}", _get_channel(event))

    # -- @mention in channels ----------------------------------------------
    @app.event("app_mention")
    async def handle_app_mention(event: dict, client: AsyncWebClient, ack: Any, context: BoltContext) -> None:
        """
        Handle ``@BotName`` mention events in channels and group DMs.

        Acknowledges immediately and fires a background task.
        :func:`_noop_set_status` is supplied for ``set_status`` because the
        Slack Assistant utilities are unavailable outside an AI-Assistant thread.

        Args:
            event: Slack ``app_mention`` event payload.
            client: ``AsyncWebClient`` for posting the reply.
            ack: Bolt acknowledgement callable.
            context: ``BoltContext`` providing ``channel_id``.
        """
        logger.info("App mention in channel={}", _get_channel(event, context))
        await ack()
        _create_safe_task(
            post_graph_reply(
                event=event,
                set_status=_noop_set_status,
                client=client,
                context=context,
                graph=graph,
                settings=settings,
            )
        )

    # -- Direct messages ---------------------------------------------------
    @app.event("message")
    async def handle_direct_message(event: dict, client: AsyncWebClient, ack: Any, context: BoltContext) -> None:
        """
        Handle direct messages sent to the bot.

        Filters to human-originated DMs only (``channel_type=im``, no
        ``bot_id``).  A ``_status_updater`` closure attempts a best-effort
        ``assistant_threads_setStatus`` call to surface a typing indicator,
        gracefully swallowing any API errors at DEBUG level.

        Args:
            event: Slack ``message`` event payload.
            client: ``AsyncWebClient`` for status updates and the reply.
            ack: Bolt acknowledgement callable.
            context: ``BoltContext`` providing ``channel_id``.
        """
        if event.get("channel_type") != "im" or event.get("bot_id"):
            await ack()
            return

        channel = _get_channel(event, context)
        thread_ts = event.get("thread_ts") or event.get("ts")
        logger.info("Direct message in channel={}", channel)
        await ack()

        async def _status_updater(status: str, **_kwargs: Any) -> None:
            """
            Best-effort typing-indicator update for DM threads.

            Calls ``assistant_threads_setStatus`` when a thread timestamp is
            available.  Any exception is logged at DEBUG level and suppressed
            so the main reply flow is never interrupted.

            Args:
                status: Human-readable status string (e.g. ``"Thinking…"``).
                **_kwargs: Extra kwargs accepted for ``AsyncSetStatus``
                    interface compatibility.
            """
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

        _create_safe_task(
            post_graph_reply(
                event=event,
                set_status=_status_updater,
                client=client,
                context=context,
                graph=graph,
                settings=settings,
            )
        )

    logger.info("Slack event handlers registered")
