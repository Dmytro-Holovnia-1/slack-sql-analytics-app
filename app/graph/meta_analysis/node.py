from loguru import logger

from app.graph.messages import assistant_message, latest_message_text, to_langchain_history
from app.graph.state import GraphState

from .prompts import SYSTEM_PROMPT
from .schemas import MetaAnalystOutput


async def meta_analyst_node(state: GraphState, llm_client) -> dict:
    """
    Handle meta-questions about SQL logic, database schema, or conversation context.

    This node explains SQL queries, describes database structure, or analyzes conversation history WITHOUT executing any
    new database queries.
    """
    messages = state.get("messages", [])
    user_text = latest_message_text(messages, "user") or ""
    history = to_langchain_history(messages[:-1])

    logger.debug(f"Meta analyst request: '{user_text[:200]}'")
    logger.debug(f"Conversation history: {len(history)} messages")

    result: MetaAnalystOutput = await llm_client.generate_structured_output(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_text,
        history=history,
        response_model=MetaAnalystOutput,
    )

    logger.info(f"Meta analyst response generated: {(result.slack_message or '')[:100]}...")

    assistant_msg = assistant_message(result.slack_message)

    return {
        "formatted_response": result.slack_message,
        "messages": [assistant_msg],
    }
