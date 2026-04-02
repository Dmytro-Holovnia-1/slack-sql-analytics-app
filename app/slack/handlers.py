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

MENTION_RE = re.compile(r"<@[^>]+>")


def build_thread_context_key(event: dict[str, Any]) -> str:
    channel = event.get("channel_id") or event.get("channel") or "unknown-channel"
    thread_ts = event.get("thread_ts") or event.get("ts") or "unknown-ts"
    return f"{channel}-{thread_ts}"


def extract_user_text(event: dict[str, Any] | str | None) -> str:
    raw_text = event if isinstance(event, str) else (event or {}).get("text")
    raw_text = (raw_text or "").strip()
    without_mentions = MENTION_RE.sub("", raw_text)
    return without_mentions.strip()


async def _update_status_for_chain_start(name: str, set_status) -> None:
    """Update status based on chain name during on_chain_start event."""
    if name == "intent_router_node":
        await set_status("Thinking...")
    elif name == "sql_expert_node":
        await set_status(
            status="Generating SQL...",
            loading_messages=[
                "Analyzing your question...",
                "Planning the query...",
            ],
        )
    elif name == "sql_executor_node":
        await set_status(
            status="Querying database...",
            loading_messages=[
                "Running your SQL query...",
                "Crunching the numbers...",
                "Almost there...",
            ],
        )
    elif name == "sql_repair_node":
        await set_status("Fixing query...")
    elif name == "result_formatter_node":
        await set_status(
            status="Generating answer...",
            loading_messages=[
                "Formatting the results...",
                "Preparing your answer...",
            ],
        )
    elif name == "meta_analyst_node":
        await set_status("Analyzing context and schema...")


async def _post_graph_reply_with_streaming(
    graph,
    user_text: str,
    thread_id: str,
    channel: str,
    set_status,
) -> tuple[dict | None, str]:
    """Stream graph events with status updates and return result and intent."""
    result: dict | None = None

    try:
        # Stream events without tracing context first
        async for ev in graph.astream_events(
            {"messages": [user_message(user_text)]},
            config={"configurable": {"thread_id": thread_id}},
            version="v2",
        ):
            name = ev.get("name", "")
            etype = ev["event"]
            logger.debug(f"Graph event: name={name}, event={etype}")

            if etype == "on_chain_start":
                await _update_status_for_chain_start(name, set_status)
            elif etype == "on_chain_end" and ev.get("data", {}).get("output"):
                output = ev["data"]["output"]
                if isinstance(output, dict) and "formatted_response" in output:
                    result = output
    except Exception as e:
        logger.error("Graph streaming failed for channel={}: {}", channel, str(e))
        # Re-raise to let post_graph_reply handle the error response
        raise

    resolved_intent = result.get("intent", "unknown") if result else "unknown"

    return result, resolved_intent


async def post_graph_reply(
    event: dict[str, Any],
    set_status,
    say,
    client: AsyncWebClient,
    context: BoltContext,
    graph,
    settings: Settings,
) -> None:
    channel = context.channel_id or event.get("channel_id") or event.get("channel") or "unknown"

    thread_ts = event.get("thread_ts") or event.get("ts")
    logger.info(f"Processing message from channel={channel}, thread_ts={thread_ts}")

    result: dict | None = None
    resolved_intent = "unknown"

    try:
        cleaned_user_text = extract_user_text(event)
        thread_id = build_thread_context_key(event)
        logger.debug(f"Graph invocation: thread_id={thread_id}, user_text='{cleaned_user_text}'")

        result, resolved_intent = await _post_graph_reply_with_streaming(
            graph=graph,
            user_text=cleaned_user_text,
            thread_id=thread_id,
            channel=channel,
            set_status=set_status,
        )

        reply_text = settings.fallback_text
        if result:
            formatted_response = result.get("formatted_response")
            if formatted_response:
                reply_text = formatted_response.strip() or settings.fallback_text

        logger.info(f"Graph completed: channel={channel}, intent={resolved_intent}, response_length={len(reply_text)}")
        logger.debug(f"Graph result: {result}")
    except Exception as e:
        error_msg = str(e)
        logger.error(
            "Error processing graph reply for channel={}: {}",
            channel,
            error_msg,
            exc_info=True,
        )
        result = None
        # Provide user-friendly message for API errors
        if "503" in error_msg or "UNAVAILABLE" in error_msg or "resource_exhausted" in error_msg.lower():
            reply_text = "The AI service is temporarily unavailable. Please try again in a moment."
        else:
            reply_text = settings.fallback_text
        resolved_intent = "unknown"

    artifact_format = result.get("artifact_format") if result else None
    reply_kwargs = {"channel": event["channel"]}
    if thread_ts:
        reply_kwargs["thread_ts"] = thread_ts

    if artifact_format in {"sql", "csv"} and result:
        logger.info(f"Uploading artifact: format={artifact_format}, title={result.get('artifact_title')}")
        await client.files_upload_v2(
            **reply_kwargs,
            content=result["artifact_content"],
            title=result["artifact_title"],
            filename=result["artifact_title"],
            initial_comment=reply_text,
        )
    else:
        logger.debug(f"Posting text reply to channel={channel}")
        await client.chat_postMessage(
            **reply_kwargs,
            text=reply_text,
        )
    logger.info(f"Reply posted to channel={channel}")


def register_handlers(
    app: AsyncApp,
    graph,
    settings: Settings,
) -> None:
    # Handler for Slack AI Assistant threads (side panel)
    try:
        assistant = AsyncAssistant()
        app.assistant(assistant)

        @assistant.user_message
        async def handle_assistant_user_message(
            payload: dict,
            ack,
            set_status,
            say,
            client: AsyncWebClient,
            context: BoltContext,
        ):
            logger.info(f"Assistant user message received in channel={context.channel_id}")

            await ack()

            asyncio.create_task(
                post_graph_reply(
                    event=payload,
                    set_status=set_status,
                    say=say,
                    client=client,
                    context=context,
                    graph=graph,
                    settings=settings,
                )
            )

        logger.info("Assistant handler registered")
    except Exception as e:
        logger.warning(f"Could not register Assistant handler: {e}")

    @app.event("assistant_thread_started")
    async def handle_assistant_thread_started(event, ack):
        await ack()
        channel = event.get("channel_id") or event.get("channel") or "unknown"
        logger.info(f"Assistant thread started for channel={channel}")

    @app.event("app_mention")
    async def handle_app_mention(event, client, ack, context: BoltContext):
        channel = context.channel_id or event.get("channel", "unknown")
        logger.info(f"App mention detected in channel={channel}")

        await ack()

        asyncio.create_task(
            post_graph_reply(
                event=event,
                set_status=lambda _status: None,
                say=lambda _text: None,
                client=client,
                context=context,
                graph=graph,
                settings=settings,
            )
        )

    # Primary handler for DMs (message events with channel_type=im)
    @app.event("message")
    async def handle_direct_message(event, client, ack, context: BoltContext):
        # Filter: only handle DMs (not channel messages, not bot messages)
        if event.get("channel_type") != "im" or event.get("bot_id"):
            await ack()
            return

        channel = context.channel_id or event.get("channel", "unknown")
        logger.info(f"Direct message detected in channel={channel}")

        await ack()

        # Create a noop status updater for non-Assistant DMs
        thread_ts = event.get("thread_ts") or event.get("ts")

        async def noop_status_updater(status: str, **_kwargs):
            if thread_ts:
                try:
                    await client.assistant_threads_setStatus(
                        channel_id=channel,
                        thread_ts=thread_ts,
                        status=status,
                    )
                except Exception:
                    pass

        asyncio.create_task(
            post_graph_reply(
                event=event,
                set_status=noop_status_updater,
                say=lambda _text: None,
                client=client,
                context=context,
                graph=graph,
                settings=settings,
            )
        )

    logger.info("Slack event handlers registered")
