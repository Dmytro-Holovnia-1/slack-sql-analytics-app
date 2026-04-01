from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import HumanMessage

from app.graph.state import GraphState


@pytest.fixture
def mock_llm_client():
    client = MagicMock()
    client.generate_structured_output = AsyncMock()
    return client


@pytest.fixture
def mock_query_service():
    service = MagicMock()
    service.execute_readonly_sql = AsyncMock()
    return service


@pytest.fixture
def base_state() -> GraphState:
    return GraphState(
        messages=[HumanMessage(content="test message")],
        intent="query_database_for_new_analytics_data",
        sql_candidate=None,
        sql_title=None,
        query_results=None,
        row_count=0,
        direct_response=None,
        sql_error=None,
        repair_count=0,
        artifact_format=None,
        artifact_content=None,
        artifact_title=None,
        formatted_response=None,
    )
