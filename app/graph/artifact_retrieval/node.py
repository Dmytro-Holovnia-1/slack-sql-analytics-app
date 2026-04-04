from __future__ import annotations

from dataclasses import dataclass
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

# --- Models & DTOs ---


class PastQuery(BaseModel):
    model_config = ConfigDict(frozen=True)

    question: str
    sql_title: str | None
    index: int


@dataclass(frozen=True)
class ArtifactContext:
    target_question: str
    sql: str | None
    data: list[dict[str, Any]] | None


# --- Retriever ---


class ArtifactRetriever:
    """Resolves an artifact (SQL or CSV data) from conversation history snapshots."""

    def __init__(self, snapshots: list[Any], llm_client) -> None:
        self._snapshots = self._filter_completed(snapshots)
        self._llm = llm_client

    @staticmethod
    def _filter_completed(snapshots: list[Any]) -> list[Any]:
        return [
            s
            for s in snapshots
            if s.next == ()
            and s.values.get("intent") == "query_database_for_new_analytics_data"
            and s.values.get("sql_candidate")
        ]

    def _collect_queries(self, exclude_text: str) -> list[PastQuery]:
        seen: set[str] = set()
        queries: list[PastQuery] = []
        for snapshot in self._snapshots:
            question = latest_message_text(snapshot.values.get("messages", []), "user")
            if not question or question == exclude_text or question in seen:
                continue
            seen.add(question)
            queries.append(PastQuery(question=question, sql_title=snapshot.values.get("sql_title"), index=len(queries)))
        return queries

    async def _resolve_question(self, queries: list[PastQuery], user_text: str) -> str:
        if len(queries) == 1:
            logger.debug("Single past query — using directly")
            return queries[0].question

        ref: SQLReferenceOutput = await self._llm.generate_structured_output(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_build_reference_prompt(queries, user_text),
            few_shot_examples=FEW_SHOT_EXAMPLES,
            response_model=SQLReferenceOutput,
        )
        index = max(0, min(ref.matched_question_index, len(queries) - 1))
        logger.debug(f"Matched query index: {index}")
        return queries[index].question

    def _find_payload(self, target_question: str) -> tuple[str | None, list[dict[str, Any]] | None]:
        for snapshot in self._snapshots:
            question = latest_message_text(snapshot.values.get("messages", []), "user")
            if question == target_question:
                return snapshot.values.get("sql_candidate"), snapshot.values.get("query_results")
        return None, None

    async def resolve(self, user_text: str) -> ArtifactContext | None:
        queries = self._collect_queries(user_text)
        logger.debug(f"Found {len(queries)} past queries")
        if not queries:
            return None

        target_question = await self._resolve_question(queries, user_text)
        logger.info(f"Resolved target question: {target_question}")

        sql, data = self._find_payload(target_question)
        return ArtifactContext(target_question=target_question, sql=sql, data=data)


# --- Node (thin orchestrator) ---


async def artifact_retrieval_node(
    state: GraphState,
    config: RunnableConfig,
    *,
    fetch_history,
    llm_client,
) -> dict:
    intent = state["intent"]
    user_text = latest_message_text(state.get("messages", []), "user") or ""
    logger.info(f"Artifact retrieval: intent={intent}, user_text='{user_text[:100]}'")

    history_config = {"configurable": {"thread_id": config["configurable"]["thread_id"]}}
    snapshots = [s async for s in fetch_history(history_config)]
    logger.debug(f"Retrieved {len(snapshots)} history snapshots")

    if not snapshots:
        logger.warning("No history found for artifact retrieval")
        return _no_query_response()

    ctx = await ArtifactRetriever(snapshots, llm_client).resolve(user_text)

    if ctx is None:
        logger.warning("No past queries found")
        return _no_query_response()

    if intent == "retrieve_sql_code_from_previous_conversation_turn":
        return _build_sql_response(ctx)
    return _build_csv_response(ctx)


# --- Response builders ---


def _no_query_response() -> dict:
    msg = "No previous query found. Ask a data question first."
    return {"formatted_response": msg, "messages": [assistant_message(msg)]}


def _build_sql_response(ctx: ArtifactContext) -> dict:
    if not ctx.sql:
        logger.warning("SQL not found")
        msg = "Could not find the SQL for that query."
        return {"formatted_response": msg, "messages": [assistant_message(msg)]}

    response = f"Here's the SQL for *{ctx.target_question}*:"
    logger.info(f"Returning SQL artifact: {ctx.sql[:100]}...")
    return {
        "artifact_format": "sql",
        "artifact_content": ctx.sql,
        "artifact_title": artifact_filename("query", ctx.target_question, "sql"),
        "formatted_response": response,
        "messages": [assistant_message(response)],
    }


def _build_csv_response(ctx: ArtifactContext) -> dict:
    if not ctx.data:
        logger.warning("Data not found for csv_export")
        msg = "No data found for that query."
        return {"formatted_response": msg, "messages": [assistant_message(msg)]}

    response = f"Here's your CSV export for *{ctx.target_question}*:"
    logger.info(f"Returning CSV artifact with {len(ctx.data)} rows")
    return {
        "artifact_format": "csv",
        "artifact_content": rows_to_csv(ctx.data),
        "artifact_title": artifact_filename("export", ctx.target_question, "csv"),
        "formatted_response": response,
        "messages": [assistant_message(response)],
    }


# --- Prompt builder ---


def _build_reference_prompt(past_queries: list[PastQuery], user_text: str) -> str:
    def label(i: int) -> str:
        if i == 0:
            return " (most recent)"
        if i == len(past_queries) - 1:
            return " (oldest)"
        return ""

    lines = [
        f'[{q.index}]{label(i)} Q: "{q.question}"' + (f' -> "{q.sql_title}"' if q.sql_title else "")
        for i, q in enumerate(past_queries)
    ]
    return f"Past queries (newest first):\n{'\n'.join(lines)}\nmessage: {user_text}"
