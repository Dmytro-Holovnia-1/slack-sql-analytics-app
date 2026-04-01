from pydantic import BaseModel, Field


class MetaAnalystOutput(BaseModel):
    """Output schema for the meta analyst node."""

    slack_message: str = Field(
        description=(
            "Direct response explaining SQL logic, database schema, or conversation context. "
            "This message will be posted to Slack and should be clear, concise, and helpful. "
            "Do not include executable SQL queries - focus on explanations and descriptions."
        ),
    )
