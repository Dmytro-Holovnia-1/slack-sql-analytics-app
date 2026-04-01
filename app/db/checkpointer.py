from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from loguru import logger

from app.config import Settings


@asynccontextmanager
async def postgres_checkpointer(settings: Settings) -> AsyncIterator[Any]:
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Postgres checkpointer dependency is missing. Install `langgraph-checkpoint-postgres`."
        ) from exc

    logger.info(f"Opening Postgres checkpointer at {settings.postgres_host}:{settings.postgres_port}")
    async with AsyncPostgresSaver.from_conn_string(settings.checkpointer_database_url) as checkpointer:
        await checkpointer.setup()
        yield checkpointer
