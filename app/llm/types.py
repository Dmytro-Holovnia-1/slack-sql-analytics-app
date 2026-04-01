from typing import Protocol, TypedDict, TypeVar

from langchain_core.messages import BaseMessage
from pydantic import BaseModel

from app.llm.model_types import ModelType


class FewShotExample(TypedDict):
    input: str
    output: str


T = TypeVar("T", bound=BaseModel)


class ChatResponseClient(Protocol):
    async def generate_chat_response(self, user_text: str) -> str: ...

    async def generate_structured_output(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        history: list[BaseMessage] | None = None,
        few_shot_examples: list[FewShotExample] | None = None,
        response_model: type[T],
        model_type: ModelType = ModelType.LOW_COST,
    ) -> T: ...
