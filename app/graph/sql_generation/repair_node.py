from loguru import logger

from app.config import get_settings
from app.graph.messages import latest_message_text
from app.graph.state import GraphState
from app.llm.model_types import ModelType

from .prompts import FEW_SHOT_EXAMPLES_SQL_REPAIR, SYSTEM_SQL_REPAIR
from .schemas import SQLRepairOutput


async def sql_repair_node(state: GraphState, llm_client) -> dict:
    error = state.get("sql_error") or "Unknown error"
    sql = state.get("sql_candidate") or "Unknown SQL"
    repair_count = state.get("repair_count", 0)
    settings = get_settings()
    repair_count_exhausted = settings.max_sql_repair_attempts + 1

    logger.info(f"SQL repair attempt {repair_count + 1} for error: {error[:200]}...")
    logger.debug(f"Failed SQL: {sql}")

    user_prompt = (
        f"Original question: {latest_message_text(state.get('messages', []), 'user')}\n"
        f"Failed SQL:\n{sql}\n"
        f"PostgreSQL error:\n{error}"
    )

    result: SQLRepairOutput = await llm_client.generate_structured_output(
        system_prompt=SYSTEM_SQL_REPAIR,
        user_prompt=user_prompt,
        few_shot_examples=FEW_SHOT_EXAMPLES_SQL_REPAIR,
        response_model=SQLRepairOutput,
        model_type=ModelType.STANDARD,
    )

    if not result.is_fixable:
        logger.warning(f"SQL error deemed non-repairable: {result.diagnosis}")
        return {"sql_error": f"Non-retryable: {result.diagnosis}", "repair_count": repair_count_exhausted}

    logger.info(f"SQL repair successful, new SQL: {result.corrected_sql[:200]}...")
    logger.debug(f"Repaired SQL diagnosis: {result.diagnosis}")

    return {
        "sql_candidate": result.corrected_sql,
        "sql_error": None,
        "repair_count": repair_count + 1,
    }
