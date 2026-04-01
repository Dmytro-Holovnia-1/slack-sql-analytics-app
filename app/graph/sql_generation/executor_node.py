from loguru import logger

from app.config import MAX_SQL_REPAIR_ATTEMPTS
from app.graph.state import GraphState
from app.services.query_service import QueryExecutionError, UnsafeSQL


async def sql_executor_node(state: GraphState, query_service) -> dict:
    sql = state.get("sql_candidate") or ""
    logger.info(f"Executing SQL query: {sql[:300]}...")
    logger.debug(f"Full SQL query:\n{sql}")

    try:
        result = await query_service.execute_readonly_sql(sql)
        rows = result.rows
        row_count = result.row_count
        logger.info(f"SQL execution successful: {row_count} rows returned")
        logger.debug(f"Query result preview: {rows[:5]}")
        return {
            "query_results": rows,
            "row_count": row_count,
            "sql_error": None,
        }
    except (QueryExecutionError, UnsafeSQL) as exc:
        logger.error(f"SQL execution failed: {exc}")
        logger.debug(f"Failed SQL: {sql}")
        return {"sql_error": str(exc), "query_results": None, "row_count": 0}


def route_sql_executor(state: GraphState) -> str:
    has_error = state.get("sql_error") is not None
    repair_count = state.get("repair_count", 0)

    if has_error and repair_count < MAX_SQL_REPAIR_ATTEMPTS:
        logger.debug(f"Routing to sql_repair_node (attempt {repair_count + 1}/{MAX_SQL_REPAIR_ATTEMPTS})")
        return "sql_repair_node"

    if has_error:
        logger.info("Routing to result_formatter_node with error (max repairs reached)")
    else:
        logger.debug("Routing to result_formatter_node")

    return "result_formatter_node"
