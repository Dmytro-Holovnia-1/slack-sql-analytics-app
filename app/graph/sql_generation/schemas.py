from pydantic import BaseModel, Field


class TextToSQLOutput(BaseModel):
    """Output schema for the SQL expert node."""

    needs_clarification: bool = Field(
        default=False,
        description=(
            "True only if two different SQL interpretations would produce meaningfully different results. "
            "False for missing optional filters."
        ),
    )
    clarification_question: str | None = Field(
        default=None,
        description="Short question with 2-3 concrete options. Null if no clarification is needed.",
    )
    sql_title: str | None = Field(
        default=None,
        description="5-7 word label describing what the query returns. Used for future recall.",
    )
    sql: str | None = Field(
        default=None,
        description=(
            "Valid PostgreSQL SELECT statement. Null if needs_clarification=True. "
            "No INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE. "
            "Must end with semicolon."
        ),
    )


class SQLRepairOutput(BaseModel):
    """Output schema for the SQL repair node."""

    corrected_sql: str = Field(description="The corrected PostgreSQL SELECT statement.")
    diagnosis: str = Field(description="One sentence describing what changed.")
    is_fixable: bool = Field(description="False if the error is non-retryable; true if the SQL logic can be corrected.")
