from unittest.mock import MagicMock

import pytest
from langchain_core.messages import HumanMessage

from app.graph.artifact_retrieval.node import artifact_retrieval_node


@pytest.mark.asyncio
async def test_artifact_retrieval_csv_export(base_state, mock_llm_client):
    base_state["intent"] = "export_previous_query_results_to_csv_file"
    base_state["messages"] = [HumanMessage(content="export this as csv")]

    # Mock state history (Checkpointer)
    mock_snapshot = MagicMock()
    mock_snapshot.next = ()
    mock_snapshot.values = {
        "intent": "query_database_for_new_analytics_data",
        "messages": [HumanMessage(content="How many apps?")],
        "sql_candidate": "SELECT COUNT(*) FROM app_metrics;",
        "sql_title": "App count",
        "query_results": [{"count": 42}],
    }

    async def mock_fetch_history(config):
        yield mock_snapshot

    config = {"configurable": {"thread_id": "test_thread"}}

    result = await artifact_retrieval_node(
        base_state, config, fetch_history=mock_fetch_history, llm_client=mock_llm_client
    )

    assert result["artifact_format"] == "csv"
    assert "count\r\n42\r\n" in result["artifact_content"]
    assert "export_" in result["artifact_title"]
