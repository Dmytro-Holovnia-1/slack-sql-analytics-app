import re
from typing import TypeVar

from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate, FewShotChatMessagePromptTemplate, MessagesPlaceholder
from langchain_google_genai import ChatGoogleGenerativeAI
from loguru import logger
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import Settings
from app.llm.model_types import ModelType
from app.llm.types import FewShotExample

T = TypeVar("T", bound=BaseModel)

SYSTEM_PROMPT = "You are a minimal Slack smoke-test assistant. Reply briefly and clearly. Do not use markdown tables."


class GeminiClient:
    _RETRY_DELAY_PATTERNS = (
        re.compile(r"Please retry in (?P<seconds>\d+(?:\.\d+)?)s", re.IGNORECASE),
        re.compile(r"'retryDelay':\s*'(?P<seconds>\d+(?:\.\d+)?)s'", re.IGNORECASE),
        re.compile(r'"retryDelay":\s*"(?P<seconds>\d+(?:\.\d+)?)s"', re.IGNORECASE),
    )

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def _get_client(self, model_type: ModelType = ModelType.LOW_COST) -> ChatGoogleGenerativeAI:
        model = (
            self._settings.gemini_standard_model
            if model_type == ModelType.STANDARD
            else self._settings.gemini_low_cost_model
        )
        return ChatGoogleGenerativeAI(
            model=model,
            api_key=self._settings.google_api_key,
            thinking_level="low",
            temperature=0,
            include_thoughts=True,
        )

    async def _generate(self, user_text: str) -> str:
        prompt_template = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_PROMPT),
                ("human", "{input}"),
            ]
        )
        prompt_value = await prompt_template.ainvoke({"input": user_text.strip()})
        return await self._generate_with_prompt(prompt_value, model_type=ModelType.LOW_COST)

    async def _generate_with_prompt(self, prompt, model_type: ModelType = ModelType.LOW_COST) -> str:
        client = self._get_client(model_type=model_type)
        response = await self._ainvoke_with_transient_retry(
            lambda: client.ainvoke(prompt),
            operation_name="generate_text",
            model_type=model_type,
        )
        content = response.content if hasattr(response, "content") else response
        if isinstance(content, list):
            text = "".join(str(block) for block in content)
        else:
            text = str(content)
        normalized = text.strip()
        result = normalized or self._settings.fallback_text
        return result

    async def generate_chat_response(self, user_text: str) -> str:
        try:
            logger.info("Generating chat response for user input")
            result = await self._generate(user_text)
            logger.info("Chat response generated successfully")
            return result
        except Exception as e:
            logger.error(f"Error generating chat response: {e}")
            return self._settings.fallback_text

    async def generate_structured_output(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        history: list[BaseMessage] | None = None,
        few_shot_examples: list[FewShotExample] | None = None,
        response_model: type[T],
        model_type: ModelType = ModelType.LOW_COST,
    ) -> T:
        history = history or []
        prompt_length = len(system_prompt) + len(user_prompt) + sum(len(message.content) for message in history)
        logger.info(
            f"Generating structured output: model={response_model.__name__}, type={model_type.value}, prompt_length={prompt_length}"
        )

        client = self._get_client(model_type=model_type)
        structured_llm = client.with_structured_output(response_model)
        prompt_messages: list = [("system", system_prompt)]
        if few_shot_examples:
            example_prompt = ChatPromptTemplate.from_messages([("human", "{input}"), ("ai", "{output}")])
            prompt_messages.append(
                FewShotChatMessagePromptTemplate(
                    example_prompt=example_prompt,
                    examples=few_shot_examples,
                    input_variables=[],
                )
            )
        prompt_messages.extend(
            [
                MessagesPlaceholder(variable_name="history"),
                ("human", "{input}"),
            ]
        )
        prompt_template = ChatPromptTemplate.from_messages(prompt_messages)
        rendered = prompt_template.invoke({"history": history, "input": user_prompt})
        result = await self._ainvoke_with_transient_retry(
            lambda: structured_llm.ainvoke(rendered.messages),
            operation_name=f"generate_structured_output:{response_model.__name__}",
            model_type=model_type,
        )
        logger.info(f"Structured output generated: model={response_model.__name__}")
        return result

    async def _ainvoke_with_transient_retry(self, invoke, *, operation_name: str, model_type: ModelType):
        """Invoke with tenacity-based retry for transient errors."""

        def is_retryable_error(exc: Exception) -> bool:
            """Check if exception should trigger a retry."""
            return self._is_transient_retryable_error(exc)

        retry_decorator = retry(
            retry=retry_if_exception_type((ResourceExhausted, ServiceUnavailable))
            | retry_if_exception(is_retryable_error),
            stop=stop_after_attempt(self._settings.gemini_transient_retry_max_retries + 1),
            wait=wait_exponential(multiplier=1, min=2, max=60),
            reraise=True,
        )

        @retry_decorator
        async def wrapped_invoke():
            try:
                return await invoke()
            except Exception as exc:
                # Check if it's a retryable transient error
                if self._is_transient_retryable_error(exc):
                    logger.warning(
                        f"Transient error detected, will retry: "
                        f"operation={operation_name}, model_type={model_type.value}, error={exc}"
                    )
                    raise  # Re-raise for tenacity to handle retry
                # Non-retryable error - raise without retry
                raise exc

        return await wrapped_invoke()

    def _is_transient_retryable_error(self, exc: Exception) -> bool:
        """Check if exception is a transient/retryable error using type-checking."""
        if isinstance(exc, (ResourceExhausted, ServiceUnavailable)):
            return True

        # Fallback to message inspection for wrapped exceptions or edge cases
        message = str(exc).lower()
        retry_markers = (
            "resource_exhausted",
            "quota exceeded",
            "rate limit",
            "retrydelay",
            "please retry in",
            "429",
        )
        return any(marker in message for marker in retry_markers)

    def _get_retry_delay_seconds(self, exc: Exception) -> float:
        message = str(exc)
        for pattern in self._RETRY_DELAY_PATTERNS:
            match = pattern.search(message)
            if match:
                parsed = float(match.group("seconds"))
                return min(parsed, self._settings.gemini_transient_retry_max_delay_seconds)

        return self._settings.gemini_transient_retry_default_delay_seconds
