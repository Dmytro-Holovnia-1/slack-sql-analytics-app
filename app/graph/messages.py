from collections.abc import Iterable
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage


def user_message(content: str) -> HumanMessage:
    return HumanMessage(content=content)


def assistant_message(content: str) -> AIMessage:
    return AIMessage(content=content)


def message_role(message: Any) -> str | None:
    if isinstance(message, HumanMessage):
        return "user"
    if isinstance(message, AIMessage):
        return "assistant"
    if isinstance(message, BaseMessage):
        return {
            "human": "user",
            "ai": "assistant",
        }.get(message.type)
    if isinstance(message, dict):
        role = message.get("role")
        if role in {"user", "assistant"}:
            return role
    return None


def message_text(message: Any) -> str:
    if isinstance(message, BaseMessage):
        content = message.content
    elif isinstance(message, dict):
        content = message.get("content", "")
    else:
        content = ""

    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
        )
    return str(content)


def latest_message_text(messages: Iterable[Any], role: str) -> str | None:
    for message in reversed(list(messages)):
        if message_role(message) == role:
            text = message_text(message).strip()
            if text:
                return text
    return None


def to_langchain_history(messages: Iterable[Any]) -> list[BaseMessage]:
    history: list[BaseMessage] = []
    for message in messages:
        role = message_role(message)
        content = message_text(message).strip()
        if not content:
            continue
        if role == "user":
            history.append(HumanMessage(content=content))
        elif role == "assistant":
            history.append(AIMessage(content=content))
    return history
