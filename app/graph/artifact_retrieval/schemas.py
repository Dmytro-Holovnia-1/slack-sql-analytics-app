from pydantic import BaseModel, Field


class SQLReferenceOutput(BaseModel):
    reasoning: str = Field(
        description=(
            "Internal step-by-step analysis before answering. "
            "Think through all relevant factors, edge cases, and constraints here. "
            "This field is for scratchpad reasoning only — not shown to the user."
        )
    )
    matched_question_index: int = Field(
        ge=0,
        description=(
            "Zero-based index into the past query list identifying which previous query the user is referring to."
        ),
    )
    match_confidence: float = Field(ge=0.0, le=1.0)
