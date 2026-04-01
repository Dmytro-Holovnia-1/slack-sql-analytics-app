from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
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
        gemini_transient_retry_default_delay_seconds=5.0,
        gemini_transient_retry_max_delay_seconds=60.0,
    )


@pytest.mark.asyncio
async def test_generate_with_prompt_retries_retryable_error(monkeypatch):
    client = GeminiClient(build_settings())
    sleep_mock = AsyncMock()

    # Mock asyncio.sleep at the module level
    with patch("asyncio.sleep", sleep_mock):
        fake_model = SimpleNamespace(
            ainvoke=AsyncMock(
                side_effect=[
                    Exception("429 RESOURCE_EXHAUSTED. Please retry in 2.5s."),
                    SimpleNamespace(content="ok"),
                ]
            )
        )
        client._get_client = lambda model_type=ModelType.LOW_COST: fake_model

        result = await client._generate_with_prompt("prompt")

    assert result == "ok"
    assert fake_model.ainvoke.await_count == 2
    sleep_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_with_prompt_does_not_retry_non_retryable_error(monkeypatch):
    client = GeminiClient(build_settings())
    sleep_mock = AsyncMock()

    with patch("asyncio.sleep", sleep_mock):
        fake_model = SimpleNamespace(ainvoke=AsyncMock(side_effect=ValueError("bad request")))
        client._get_client = lambda model_type=ModelType.LOW_COST: fake_model

        with pytest.raises(ValueError, match="bad request"):
            await client._generate_with_prompt("prompt")

    assert fake_model.ainvoke.await_count == 1
    sleep_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_structured_output_retries_with_default_delay(monkeypatch):
    client = GeminiClient(build_settings())
    sleep_mock = AsyncMock()

    with patch("asyncio.sleep", sleep_mock):
        fake_runnable = SimpleNamespace(
            ainvoke=AsyncMock(
                side_effect=[
                    Exception("Quota exceeded for metric generate_content_free_tier_requests"),
                    ExampleResponse(answer="done"),
                ]
            )
        )

        class FakePromptTemplate:
            def invoke(self, values):
                return SimpleNamespace(messages=[SimpleNamespace(type="human", content=values["input"])])

            def __or__(self, other):
                return fake_runnable

        fake_model = SimpleNamespace(with_structured_output=lambda response_model: fake_runnable)
        client._get_client = lambda model_type=ModelType.LOW_COST: fake_model
        monkeypatch.setattr(
            "app.llm.gemini_client.ChatPromptTemplate.from_messages", lambda messages: FakePromptTemplate()
        )

        result = await client.generate_structured_output(
            system_prompt="system",
            user_prompt="user",
            response_model=ExampleResponse,
        )

    assert result == ExampleResponse(answer="done")
    assert fake_runnable.ainvoke.await_count == 2
    sleep_mock.assert_awaited_once()
