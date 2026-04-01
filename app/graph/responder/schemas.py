from pydantic import AliasChoices, BaseModel, Field


class InterpreterOutput(BaseModel):
    slack_message: str = Field(
        validation_alias=AliasChoices("slack_message", "text", "message"),
        description=(
            "Response formatted for Slack markdown. Starts with a one-line direct answer. "
            "If row_count=0, explain which filters were applied and found no data. "
        ),
    )
