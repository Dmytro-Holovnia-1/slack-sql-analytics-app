from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph.message import add_messages


class _GraphStateRequired(TypedDict, total=True):
    """Required fields that must always be present in GraphState."""

    messages: Annotated[list[Any], add_messages]


class GraphState(_GraphStateRequired, total=False):
    """Graph state with optional fields for optional data."""

    intent: Literal[
        "query_database_for_new_analytics_data",
        "retrieve_sql_code_from_previous_conversation_turn",
        "export_previous_query_results_to_csv_file",
        "explain_sql_or_database_schema_without_querying",
        "decline_off_topic_request_unrelated_to_analytics",
    ]
    sql_candidate: str | None
    sql_title: str | None
    query_results: list[dict[str, Any]] | None
    row_count: int
    direct_response: str | None  # any response bypassing SQL pipeline (clarification or meta-question)
    sql_error: str | None
    repair_count: int
    artifact_format: Literal["sql", "csv"] | None
    artifact_content: str | None
    artifact_title: str | None
    formatted_response: str | None
