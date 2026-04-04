"""Stateless Slack utility helpers shared across the slack package."""

import re
from typing import Any

from slack_bolt import BoltContext

MENTION_RE = re.compile(r"<@[^>]+>")

_TRANSIENT_ERROR_TOKENS: tuple[str, ...] = ("503", "unavailable", "resource_exhausted")


def build_thread_context_key(event: dict[str, Any]) -> str:
    """Return a stable ``"<channel>-<ts>"`` key used as the LangGraph thread ID."""
    channel = event.get("channel_id") or event.get("channel") or "unknown-channel"
    thread_ts = event.get("thread_ts") or event.get("ts") or "unknown-ts"
    return f"{channel}-{thread_ts}"


def extract_user_text(event: dict[str, Any] | str | None) -> str:
    """Strip ``<@USERID>`` mentions and return trimmed text from an event or string."""
    raw = event if isinstance(event, str) else (event or {}).get("text")
    return MENTION_RE.sub("", (raw or "").strip()).strip()


def get_channel(event: dict[str, Any], context: BoltContext | None = None) -> str:
    """Resolve channel ID from BoltContext or event fields; falls back to ``"unknown"``."""
    return (context.channel_id if context else None) or event.get("channel_id") or event.get("channel") or "unknown"


def is_transient_error(message: str) -> bool:
    """Return True if *message* signals a transient upstream failure (503 / UNAVAILABLE / resource_exhausted)."""
    return any(token in message.lower() for token in _TRANSIENT_ERROR_TOKENS)
