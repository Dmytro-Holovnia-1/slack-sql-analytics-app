from typing import Any, Protocol

from langsmith import traceable
from loguru import logger
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings
from app.db.engine import apply_statement_timeout, create_db_engine, rows_to_dicts


class UnsafeSQL(ValueError):
    """Raised when a query is not allowed on the analytics path."""


class QueryExecutionError(RuntimeError):
    """Raised when readonly query execution fails."""


class QueryExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    rows: list[dict[str, Any]]
    summary: str
    row_count: int


class ReadonlyQueryService(Protocol):
    async def execute_readonly_sql(self, sql: str) -> QueryExecutionResult: ...


class DatabaseQueryService:
    def __init__(self, engine: AsyncEngine, statement_timeout_ms: int) -> None:
        self._engine = engine
        self._statement_timeout_ms = statement_timeout_ms
        logger.debug(f"DatabaseQueryService initialized (timeout={statement_timeout_ms}ms)")

    @classmethod
    def from_settings(cls, settings: Settings) -> "DatabaseQueryService":
        logger.info(
            f"Creating DatabaseQueryService from settings (host={settings.postgres_host}, db={settings.postgres_db})"
        )
        return cls(create_db_engine(settings), settings.db_statement_timeout_ms)

    @traceable(run_type="tool", name="Execute Postgres SQL")
    async def execute_readonly_sql(self, sql: str) -> QueryExecutionResult:
        normalized = _normalize_sql(sql)
        logger.debug(f"Validating SQL query (normalized length={len(normalized)})")

        if not normalized.startswith(("select", "with")):
            logger.warning(f"Blocked non-SELECT query: {normalized[:100]}")
            raise UnsafeSQL("Only SELECT queries are allowed on the analytics path.")

        try:
            logger.info(f"Executing readonly SQL query (timeout={self._statement_timeout_ms}ms)")
            logger.debug(f"SQL:\n{sql}")

            async with self._engine.connect() as connection:
                await apply_statement_timeout(connection, self._statement_timeout_ms)
                result = await connection.execute(text(sql))
                rows = rows_to_dicts(list(result.mappings().all()))

            logger.info(f"Query executed successfully: {len(rows)} rows returned")
            logger.debug(f"Query result preview: {rows[:3]}")

        except SQLAlchemyError as exc:
            logger.error(f"Database execution error: {exc}")
            logger.debug(f"Failed SQL: {sql}")
            raise QueryExecutionError(str(exc)) from exc

        return QueryExecutionResult(rows=rows, summary=_build_data_summary(rows), row_count=len(rows))

    async def dispose(self) -> None:
        logger.debug("Disposing database engine")
        await self._engine.dispose()


def _build_data_summary(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "Query returned no rows."
    preview = rows[:3]
    return f"Query returned {len(rows)} rows. Top rows: {preview}"


def _normalize_sql(sql: str) -> str:
    return " ".join(sql.strip().lower().split())
