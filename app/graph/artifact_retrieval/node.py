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


class PastQuery(BaseModel):
    """A user question extracted from a previous conversation turn."""

    model_config = ConfigDict(frozen=True)

    question: str
    sql_title: str | None
    index: int


@dataclass(frozen=True)
class ArtifactPayload:
    """Resolved artifact: the matched question with its SQL and query results."""

    question: str
    sql: str | None
    data: list[dict[str, Any]] | None


class ArtifactRetriever:
    """Resolves an artifact payload from completed analytical history snapshots."""

    def __init__(self, snapshots: list[Any], llm_client) -> None:
        self._snapshots = self._filter_completed(snapshots)
        self._llm = llm_client

    async def resolve(self, user_text: str) -> ArtifactPayload | None:
        """Return the most relevant artifact for the current user message, or None."""
        queries = self._extract_past_queries(user_text)
        logger.debug(f"Found {len(queries)} past queries")

        if not queries:
            logger.warning("No past queries found")
            return None

        question = await self._pick_question(queries, user_text)
        logger.info(f"Resolved target question: {question}")

        sql, data = self._lookup_payload(question)
        return ArtifactPayload(question=question, sql=sql, data=data)

    @staticmethod
    def _filter_completed(snapshots: list[Any]) -> list[Any]:
        """Keep only finished analytical snapshots that contain a SQL candidate."""
        return [
            s
            for s in snapshots
            if s.next == ()
            and s.values.get("intent") == "query_database_for_new_analytics_data"
            and s.values.get("sql_candidate")
        ]

    def _extract_past_queries(self, exclude: str) -> list[PastQuery]:
        """Collect unique user questions from snapshots, skipping the current message."""
        seen: set[str] = set()
        queries: list[PastQuery] = []
        for snapshot in self._snapshots:
            question = latest_message_text(snapshot.values.get("messages", []), "user")
            if not question or question == exclude or question in seen:
                continue
            seen.add(question)
            queries.append(PastQuery(question=question, sql_title=snapshot.values.get("sql_title"), index=len(queries)))
        return queries

    async def _pick_question(self, queries: list[PastQuery], user_text: str) -> str:
        """Return the question directly if only one exists, otherwise delegate to LLM."""
        if len(queries) == 1:
            return queries[0].question

        ref: SQLReferenceOutput = await self._llm.generate_structured_output(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=_build_reference_prompt(queries, user_text),
            few_shot_examples=FEW_SHOT_EXAMPLES,
            response_model=SQLReferenceOutput,
        )
        index = max(0, min(ref.matched_question_index, len(queries) - 1))
        logger.debug(f"LLM matched query index: {index}")
        return queries[index].question

    def _lookup_payload(self, question: str) -> tuple[str | None, list[dict] | None]:
        """Find SQL candidate and query results for the matched question."""
        for snapshot in self._snapshots:
            q = latest_message_text(snapshot.values.get("messages", []), "user")
            if q == question:
                return snapshot.values.get("sql_candidate"), snapshot.values.get("query_results")
        return None, None


# --- Node ---


async def artifact_retrieval_node(
    state: GraphState,
    config: RunnableConfig,
    *,
    fetch_history,
    llm_client,
) -> dict:
    """LangGraph node: retrieves a SQL snippet or CSV data from conversation history."""
    intent = state["intent"]
    user_text = latest_message_text(state.get("messages", []), "user") or ""
    logger.info(f"Artifact retrieval: intent={intent}, user_text='{user_text[:100]}'")

    history_config = {"configurable": {"thread_id": config["configurable"]["thread_id"]}}
    snapshots = [s async for s in fetch_history(history_config)]
    logger.debug(f"Retrieved {len(snapshots)} snapshots")

    payload = await ArtifactRetriever(snapshots, llm_client).resolve(user_text)
    if payload is None:
        return _no_query_response()

    if intent == "retrieve_sql_code_from_previous_conversation_turn":
        return _sql_response(payload)
    return _csv_response(payload)


# --- Response builders ---


def _no_query_response() -> dict:
    """Return a fallback response when no matching past query is found."""
    msg = "No previous query found. Ask a data question first."
    return {"formatted_response": msg, "messages": [assistant_message(msg)]}


def _sql_response(payload: ArtifactPayload) -> dict:
    """Build a response dict containing the SQL artifact."""
    if not payload.sql:
        msg = "Could not find the SQL for that query."
        return {"formatted_response": msg, "messages": [assistant_message(msg)]}
    response = f"Here's the SQL for *{payload.question}*:"
    logger.info(f"Returning SQL: {payload.sql[:100]}...")
    return {
        "artifact_format": "sql",
        "artifact_content": payload.sql,
        "artifact_title": artifact_filename("query", payload.question, "sql"),
        "formatted_response": response,
        "messages": [assistant_message(response)],
    }


def _csv_response(payload: ArtifactPayload) -> dict:
    """Build a response dict containing the CSV export."""
    if not payload.data:
        msg = "No data found for that query."
        return {"formatted_response": msg, "messages": [assistant_message(msg)]}
    response = f"Here's your CSV export for *{payload.question}*:"
    logger.info(f"Returning CSV with {len(payload.data)} rows")
    return {
        "artifact_format": "csv",
        "artifact_content": rows_to_csv(payload.data),
        "artifact_title": artifact_filename("export", payload.question, "csv"),
        "formatted_response": response,
        "messages": [assistant_message(response)],
    }


# --- Helpers ---


def _build_reference_prompt(queries: list[PastQuery], user_text: str) -> str:
    """Format past queries into a prompt string for LLM-based selection."""
    lines = []
    for i, q in enumerate(queries):
        label = " (most recent)" if i == 0 else " (oldest)" if i == len(queries) - 1 else ""
        entry = f'[{q.index}]{label} Q: "{q.question}"'
        if q.sql_title:
            entry += f' -> "{q.sql_title}"'
        lines.append(entry)
    return f"Past queries (newest first):\n{'\n'.join(lines)}\nmessage: {user_text}"
