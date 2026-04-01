import datetime as dt
from decimal import Decimal
from typing import Any

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from app.config import Settings


def create_db_engine(settings: Settings) -> AsyncEngine:
    database_url = settings.readonly_database_url
    logger.info(
        f"Creating async database engine (host={settings.postgres_host}, db={settings.postgres_db}, user={settings.postgres_user})"
    )
    logger.debug(
        f"Database URL (masked): {database_url.split('@')[0]}://***@{database_url.split('@')[1] if '@' in database_url else '***'}"
    )

    engine = create_async_engine(
        database_url,
        pool_pre_ping=True,
    )
    return engine


async def apply_statement_timeout(
    connection: AsyncConnection,
    timeout_ms: int,
) -> None:
    logger.debug(f"Applying statement timeout: {timeout_ms}ms")
    await connection.execute(text(f"SET statement_timeout = {int(timeout_ms)}"))


def rows_to_dicts(rows: list[Any]) -> list[dict[str, Any]]:
    return [_json_safe_value(dict(row)) for row in rows]


def _json_safe_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (dt.date, dt.datetime, dt.time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(item) for item in value]
    return str(value)
