import pytest

from app.graph.sql_generation.executor_node import sql_executor_node
from app.graph.sql_generation.expert_node import sql_expert_node
from app.graph.sql_generation.schemas import TextToSQLOutput
from app.services.query_service import QueryExecutionError, QueryExecutionResult


@pytest.mark.asyncio
async def test_sql_expert_success(base_state, mock_llm_client):
    # Mock successful LLM response
    mock_llm_client.generate_structured_output.return_value = TextToSQLOutput(
        sql="SELECT * FROM app_metrics;", sql_title="All metrics", needs_clarification=False
    )

    result = await sql_expert_node(base_state, mock_llm_client)

    assert result["sql_candidate"] == "SELECT * FROM app_metrics;"
    assert result["sql_title"] == "All metrics"
    assert result["direct_response"] is None


@pytest.mark.asyncio
async def test_sql_expert_needs_clarification(base_state, mock_llm_client):
    mock_llm_client.generate_structured_output.return_value = TextToSQLOutput(
        needs_clarification=True, clarification_question="Do you mean iOS or Android?", sql=None
    )

    result = await sql_expert_node(base_state, mock_llm_client)

    assert result["direct_response"] == "Do you mean iOS or Android?"
    assert result["sql_candidate"] is None


@pytest.mark.asyncio
async def test_sql_executor_success(base_state, mock_query_service):
    base_state["sql_candidate"] = "SELECT 1;"
    mock_query_service.execute_readonly_sql.return_value = QueryExecutionResult(
        rows=[{"col1": 1}], summary="1 rows", row_count=1
    )

    result = await sql_executor_node(base_state, mock_query_service)

    assert result["query_results"] == [{"col1": 1}]
    assert result["row_count"] == 1
    assert result["sql_error"] is None


@pytest.mark.asyncio
async def test_sql_executor_failure(base_state, mock_query_service):
    base_state["sql_candidate"] = "SELECT BAD SQL;"
    mock_query_service.execute_readonly_sql.side_effect = QueryExecutionError("Syntax error")

    result = await sql_executor_node(base_state, mock_query_service)

    assert result["query_results"] is None
    assert result["row_count"] == 0
    assert "Syntax error" in result["sql_error"]
