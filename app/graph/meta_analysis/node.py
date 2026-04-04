from langchain_core.messages import AIMessage
from loguru import logger

from app.graph.messages import latest_message_text
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

    logger.debug(f"Meta analyst request: '{user_text[:200]}'")
    logger.debug(f"Conversation history: {len(messages[:-1])} messages")

    result: MetaAnalystOutput = await llm_client.generate_structured_output(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_text,
        history=messages[:-1],
        response_model=MetaAnalystOutput,
    )

    logger.info(f"Meta analyst response generated: {(result.slack_message or '')[:100]}...")

    assistant_msg = AIMessage(content=result.slack_message)

    return {
        "formatted_response": result.slack_message,
        "messages": [assistant_msg],
    }
