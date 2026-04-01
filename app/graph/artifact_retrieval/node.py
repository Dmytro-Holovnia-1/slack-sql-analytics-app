from typing import Any

from langchain_core.runnables import RunnableConfig
from loguru import logger
from pydantic import BaseModel, ConfigDict

from app.graph.messages import assistant_message, latest_message_text
from app.graph.state import GraphState
from app.services.csv_service import rows_to_csv
from app.slack.formatting import artifact_filename

from .prompts import FEW_SHOT_EXAMPLES, SYSTEM_PROMPT
from .schemas import SQLReferenceOutput


class PastQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    sql_title: str | None
    index: int


async def artifact_retrieval_node(
    state: GraphState,
    config: RunnableConfig,
    *,
    fetch_history,
    llm_client,
) -> dict:
    intent = state["intent"]
    user_text = latest_message_text(state.get("messages", []), "user") or ""
    logger.info(f"Artifact retrieval request: intent={intent}, user_text='{user_text[:100]}'")

    history_config = {"configurable": {"thread_id": config["configurable"]["thread_id"]}}
    history_snapshots = [snapshot async for snapshot in fetch_history(history_config)]
    logger.debug(f"Retrieved {len(history_snapshots)} history snapshots")

    if not history_snapshots:
        logger.warning("No history found for artifact retrieval")
        response = "No previous query found. Ask a data question first."
        return {"formatted_response": response, "messages": [assistant_message(response)]}

    completed_snapshots = _completed_analytical_snapshots(history_snapshots)
    past_queries = _collect_past_queries(completed_snapshots, user_text)
    logger.debug(f"Found {len(past_queries)} past queries")

    if not past_queries:
        logger.warning("No past queries found")
        response = "No previous query found. Ask a data question first."
        return {"formatted_response": response, "messages": [assistant_message(response)]}

    target_question = await _resolve_target_question(past_queries, user_text, llm_client)
    logger.info(f"Resolved target question: {target_question}")

    target_sql, target_data = _find_artifact_payload(completed_snapshots, target_question)

    if intent == "retrieve_sql_code_from_previous_conversation_turn":
        if not target_sql:
            logger.warning("SQL not found for sql_request")
            response = "Could not find the SQL for that query."
            return {"formatted_response": response, "messages": [assistant_message(response)]}
        response = f"Here's the SQL for *{target_question}*:"
        logger.info(f"Returning SQL artifact: {target_sql[:100]}...")
        return {
            "artifact_format": "sql",
            "artifact_content": target_sql,
            "artifact_title": artifact_filename("query", target_question, "sql"),
            "formatted_response": response,
            "messages": [assistant_message(response)],
        }

    if not target_data:
        logger.warning("Data not found for csv_export")
        response = "No data found for that query."
        return {"formatted_response": response, "messages": [assistant_message(response)]}

    response = f"Here's your CSV export for *{target_question}*:"
    logger.info(f"Returning CSV artifact with {len(target_data)} rows")
    return {
        "artifact_format": "csv",
        "artifact_content": rows_to_csv(target_data),
        "artifact_title": artifact_filename("export", target_question, "csv"),
        "formatted_response": response,
        "messages": [assistant_message(response)],
    }


def _completed_analytical_snapshots(history_snapshots) -> list[Any]:
    return [
        snapshot
        for snapshot in history_snapshots
        if snapshot.next == ()
        and snapshot.values.get("intent") == "query_database_for_new_analytics_data"
        and snapshot.values.get("sql_candidate")
    ]


def _collect_past_queries(history_snapshots, user_text: str) -> list[PastQuery]:
    past_queries: list[PastQuery] = []
    seen_questions: set[str] = set()
    for snapshot in history_snapshots:
        values = snapshot.values
        messages = values.get("messages", [])
        question = latest_message_text(messages, "user")
        if not question or question == user_text or question in seen_questions:
            continue
        seen_questions.add(question)
        past_queries.append(
            PastQuery(
                question=question,
                sql_title=values.get("sql_title"),
                index=len(past_queries),
            )
        )
    return past_queries


async def _resolve_target_question(past_queries: list[PastQuery], user_text: str, llm_client) -> str:
    if len(past_queries) == 1:
        logger.debug("Single past query found, using it directly")
        return past_queries[0].question

    logger.debug(f"Resolving target from {len(past_queries)} past queries")
    ref: SQLReferenceOutput = await llm_client.generate_structured_output(
        system_prompt=SYSTEM_PROMPT,
        user_prompt=_build_reference_prompt(past_queries, user_text),
        few_shot_examples=FEW_SHOT_EXAMPLES,
        response_model=SQLReferenceOutput,
    )
    index = max(0, min(ref.matched_question_index, len(past_queries) - 1))
    logger.debug(f"Matched query index: {index}")
    return past_queries[index].question


def _build_reference_prompt(past_queries: list[PastQuery], user_text: str) -> str:
    lines = []
    for i, query in enumerate(past_queries):
        label = ""
        if i == 0:
            label = " (most recent)"
        elif i == len(past_queries) - 1:
            label = " (oldest)"

        line = f'[{query.index}]{label} Q: "{query.question}"'
        if query.sql_title:
            line += f' -> "{query.sql_title}"'
        lines.append(line)

    formatted_queries = "\n".join(lines)
    return f"Past queries (newest first):\n{formatted_queries}\nmessage: {user_text}"


def _find_artifact_payload(history_snapshots, target_question: str) -> tuple[str | None, list[dict[str, Any]] | None]:
    for snapshot in history_snapshots:
        messages = snapshot.values.get("messages", [])
        question = latest_message_text(messages, "user")
        if question == target_question:
            return snapshot.values.get("sql_candidate"), snapshot.values.get("query_results")
    return None, None
