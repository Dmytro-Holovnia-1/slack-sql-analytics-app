from typing import Literal

from pydantic import BaseModel, Field


class IntentRouterOutput(BaseModel):
    reasoning: str = Field(
        default="Normalized from structured classifier output.",
        description=(
            "Internal step-by-step analysis before answering. "
            "Think through all relevant factors, edge cases, and constraints here. "
            "This field is for scratchpad reasoning only — not shown to the user."
        ),
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    intent: Literal[
        "query_database_for_new_analytics_data",
        "retrieve_sql_code_from_previous_conversation_turn",
        "export_previous_query_results_to_csv_file",
        "explain_sql_or_database_schema_without_querying",
        "decline_off_topic_request_unrelated_to_analytics",
    ] = Field(
        description=(
            "'query_database_for_new_analytics_data': data question about the app portfolio requiring new SQL query execution. "
            "'retrieve_sql_code_from_previous_conversation_turn': wants to see the SQL behind a previous query result. "
            "'export_previous_query_results_to_csv_file': wants to download previous query results as a CSV file. "
            "'explain_sql_or_database_schema_without_querying': asks for explanation of SQL logic or database structure without executing a new query. "
            "'decline_off_topic_request_unrelated_to_analytics': unrelated to app analytics or SQL."
        )
    )
