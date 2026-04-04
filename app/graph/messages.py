from collections.abc import Iterable

from langchain_core.messages import BaseMessage

_LC_ROLE = {"human": "user", "ai": "assistant"}


def latest_message_text(messages: Iterable[BaseMessage], role: str) -> str | None:
    for message in reversed(list(messages)):
        if _LC_ROLE.get(message.type) != role:
            continue
        content = message.content
        if isinstance(content, list):
            text = "".join(
                block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
            )
        elif isinstance(content, str):
            text = content
        else:
            text = str(content)
        if text.strip():
            return text.strip()
    return None
