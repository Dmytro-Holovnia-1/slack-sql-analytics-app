from typing import TypeVar

from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from langchain_core.messages import BaseMessage
from langchain_core.prompts import (
    ChatPromptTemplate,
    FewShotChatMessagePromptTemplate,
    MessagesPlaceholder,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from loguru import logger
from pydantic import BaseModel

from app.config import Settings
from app.llm.model_types import ModelType
from app.llm.types import FewShotExample

T = TypeVar("T", bound=BaseModel)

_TRANSIENT_EXCEPTIONS = (ResourceExhausted, ServiceUnavailable)


class GeminiClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    @property
    def _retry_config(self) -> dict:
        return {
            "retry_if_exception_type": _TRANSIENT_EXCEPTIONS,
            "stop_after_attempt": self._settings.gemini_transient_retry_max_retries + 1,
            "wait_exponential_jitter": True,
        }

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

    @staticmethod
    def _extract_text(response) -> str:
        content = response.content if hasattr(response, "content") else response
        text = "".join(str(b) for b in content) if isinstance(content, list) else str(content)
        return text.strip()

    # ------------------------------------------------------------------ #
    # Private generation                                                   #
    # ------------------------------------------------------------------ #

    async def _generate_with_prompt(self, prompt, model_type: ModelType = ModelType.LOW_COST) -> str:
        client = self._get_client(model_type)
        response = await client.with_retry(**self._retry_config).ainvoke(prompt)
        return self._extract_text(response) or self._settings.fallback_text

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
        logger.info(
            f"Generating structured output: model={response_model.__name__}, type={model_type.value}, "
            f"prompt_length={len(system_prompt) + len(user_prompt) + sum(len(m.content) for m in history)}"
        )

        messages: list = [("system", system_prompt)]
        if few_shot_examples:
            example_prompt = ChatPromptTemplate.from_messages([("human", "{input}"), ("ai", "{output}")])
            messages.append(
                FewShotChatMessagePromptTemplate(
                    example_prompt=example_prompt,
                    examples=few_shot_examples,
                    input_variables=[],
                )
            )
        messages += [MessagesPlaceholder(variable_name="history"), ("human", "{input}")]

        rendered = ChatPromptTemplate.from_messages(messages).invoke({"history": history, "input": user_prompt})

        structured_llm = (
            self._get_client(model_type).with_structured_output(response_model).with_retry(**self._retry_config)
        )
        result = await structured_llm.ainvoke(rendered.messages)
        logger.info(f"Structured output generated: model={response_model.__name__}")
        return result
