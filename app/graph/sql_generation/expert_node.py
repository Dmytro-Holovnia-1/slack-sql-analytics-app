from datetime import UTC, datetime

from loguru import logger

from app.db.schema import DB_SCHEMA
from app.graph.messages import latest_message_text, to_langchain_history
from app.graph.state import GraphState
from app.llm.model_types import ModelType

from .prompts import FEW_SHOT_EXAMPLES, SYSTEM_SQL_EXPERT
from .schemas import TextToSQLOutput


async def sql_expert_node(state: GraphState, llm_client) -> dict:
    messages = state.get("messages", [])
    user_text = latest_message_text(messages, "user") or ""
    history = to_langchain_history(messages[:-1])
    # Get current datetime for relative date calculations
    current_datetime = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")

    result: TextToSQLOutput = await llm_client.generate_structured_output(
        system_prompt=SYSTEM_SQL_EXPERT.format(schema=DB_SCHEMA, current_datetime=current_datetime),
        user_prompt=user_text,
        history=history,
        few_shot_examples=FEW_SHOT_EXAMPLES,
        response_model=TextToSQLOutput,
        model_type=ModelType.STANDARD,
    )

    if result.needs_clarification:
        logger.info(f"SQL expert needs clarification: {result.clarification_question}")
        return {
            "direct_response": result.clarification_question,
            "sql_candidate": None,
            "sql_title": None,
        }

    if not result.sql:
        logger.error("LLM returned no SQL without setting clarification/meta flags")
        return {
            "direct_response": "Failed to generate query. Please try rephrasing your question.",
            "sql_candidate": None,
            "sql_title": None,
        }

    logger.info(f"SQL expert generated successfully: {(result.sql or '')[:200]}...")
    logger.debug(f"Full SQL: {result.sql}, title: {result.sql_title}")

    return {
        "sql_candidate": result.sql,
        "sql_title": result.sql_title,
        "direct_response": None,
    }


def route_sql_expert(state: GraphState) -> str:
    if state.get("direct_response"):
        logger.debug("Routing to response_node")
        return "response_node"
    logger.debug("Routing to sql_executor_node")
    return "sql_executor_node"
