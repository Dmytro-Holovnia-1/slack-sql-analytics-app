from loguru import logger

from app.config import MULTI_COL_THRESHOLD, MULTI_ROW_THRESHOLD
from app.graph.messages import assistant_message, latest_message_text
from app.graph.state import GraphState
from app.services.csv_service import rows_to_csv
from app.slack.formatting import artifact_filename

from .prompts import FEW_SHOT_EXAMPLES, SYSTEM
from .schemas import InterpreterOutput

# Complexity heuristic - thresholds from config
_MULTI_ROW_THRESHOLD = MULTI_ROW_THRESHOLD
_MULTI_COL_THRESHOLD = MULTI_COL_THRESHOLD


def is_complex_result(rows: list[dict] | None) -> bool:
    """True when the result warrants an automatic CSV attachment."""
    if not rows:
        return False
    return len(rows) > _MULTI_ROW_THRESHOLD or len(rows[0]) > _MULTI_COL_THRESHOLD


def _format_rows_preview(rows: list[dict] | None) -> str:
    if not rows:
        return "no rows"
    headers = list(rows[0].keys())
    lines = ["\t".join(headers)]
    for row in rows[:50]:
        lines.append("\t".join(str(row[h]) for h in headers))
    if len(rows) > 50:
        lines.append(f"... {len(rows) - 50} more rows")
    return "\n".join(lines)


async def result_formatter_node(state: GraphState, llm_client) -> dict:
    if state.get("sql_error") and state.get("repair_count", 0) >= 2:
        logger.warning(f"Formatting error response after {state['repair_count']} failed repairs")
        response = f"Persistent SQL error: {state['sql_error']} — try rephrasing your question."
        return {"formatted_response": response, "messages": [assistant_message(response)]}

    row_count = state.get("row_count", 0)
    query_results = state.get("query_results")
    user_question = latest_message_text(state.get("messages", []), "user") or ""

    logger.info(f"Formatting result for {row_count} rows")
    user_prompt = (
        f"Question: {user_question}\n"
        f"SQL used: {state.get('sql_candidate')}\n"
        f"Rows returned: {row_count}\n"
        f"Data:\n{_format_rows_preview(query_results)}"
    )

    result: InterpreterOutput = await llm_client.generate_structured_output(
        system_prompt=SYSTEM,
        user_prompt=user_prompt,
        few_shot_examples=FEW_SHOT_EXAMPLES,
        response_model=InterpreterOutput,
    )

    response = result.slack_message
    # Unescape literal \n to actual newlines for proper Slack formatting
    response = response.replace("\\n", "\n")

    artifact: dict = {}
    if is_complex_result(query_results):
        title = artifact_filename("export", user_question, "csv")
        artifact = {
            "artifact_format": "csv",
            "artifact_content": rows_to_csv(query_results),  # type: ignore[arg-type]
            "artifact_title": title,
        }
        logger.info(
            f"Auto-attaching CSV: {row_count} rows × " f"{len(query_results[0]) if query_results else 0} cols → {title}"
        )

    logger.info(f"Response formatted: {len(response)} chars, artifact={bool(artifact)}")
    return {
        "formatted_response": response,
        "messages": [assistant_message(response)],
        **artifact,
    }
