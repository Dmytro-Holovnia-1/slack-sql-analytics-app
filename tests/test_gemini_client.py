from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from google.api_core.exceptions import ResourceExhausted
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from app.config import Settings
from app.llm.gemini_client import GeminiClient, ModelType


class ExampleResponse(BaseModel):
    answer: str


def build_settings() -> Settings:
    return Settings(
        slack_bot_token="x",
        slack_app_token="x",
        slack_signing_secret="x",
        google_api_key="x",
        postgres_db="db",
        postgres_host="localhost",
        postgres_port=5432,
        postgres_user="user",
        postgres_password="pass",
        chatbot_db_user="user",
        chatbot_db_password="pass",
        gemini_transient_retry_max_retries=1,
    )


@pytest.mark.asyncio
async def test_generate_with_prompt_retries_retryable_error():
    client = GeminiClient(build_settings())

    ainvoke_mock = AsyncMock(
        side_effect=[
            ResourceExhausted("quota exhausted"),
            SimpleNamespace(content="ok"),
        ]
    )
    client._get_client = lambda model_type=ModelType.LOW_COST: RunnableLambda(ainvoke_mock)

    with patch("asyncio.sleep", AsyncMock()) as sleep_mock:
        result = await client._generate_with_prompt("prompt")

    assert result == "ok"
    assert ainvoke_mock.await_count == 2
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_with_prompt_does_not_retry_non_retryable_error():
    client = GeminiClient(build_settings())

    ainvoke_mock = AsyncMock(side_effect=ValueError("bad request"))
    client._get_client = lambda model_type=ModelType.LOW_COST: RunnableLambda(ainvoke_mock)

    with patch("asyncio.sleep", AsyncMock()) as sleep_mock:
        with pytest.raises(ValueError, match="bad request"):
            await client._generate_with_prompt("prompt")

    assert ainvoke_mock.await_count == 1
    sleep_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_structured_output_retries_with_default_delay(monkeypatch):
    client = GeminiClient(build_settings())

    ainvoke_mock = AsyncMock(
        side_effect=[
            ResourceExhausted("quota exhausted"),
            ExampleResponse(answer="done"),
        ]
    )
    fake_runnable = RunnableLambda(ainvoke_mock)

    class FakeClient:
        def with_structured_output(self, response_model):
            return fake_runnable

    client._get_client = lambda model_type=ModelType.LOW_COST: FakeClient()
    monkeypatch.setattr(
        "app.llm.gemini_client.ChatPromptTemplate.from_messages",
        lambda messages: _FakePromptTemplate(),
    )

    with patch("asyncio.sleep", AsyncMock()) as sleep_mock:
        result = await client.generate_structured_output(
            system_prompt="system",
            user_prompt="user",
            response_model=ExampleResponse,
        )

    assert result == ExampleResponse(answer="done")
    assert ainvoke_mock.await_count == 2
    sleep_mock.assert_awaited_once()


class _FakePromptTemplate:
    def invoke(self, values):
        return SimpleNamespace(messages=[SimpleNamespace(type="human", content=values["input"])])
