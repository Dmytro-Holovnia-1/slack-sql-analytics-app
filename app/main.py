import asyncio
import os

from langgraph.checkpoint.memory import MemorySaver
from loguru import logger
from slack_bolt.adapter.socket_mode.aiohttp import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from app.config import Settings, load_settings
from app.db.checkpointer import postgres_checkpointer
from app.graph.graph import build_graph
from app.llm.gemini_client import GeminiClient
from app.logging_config import setup_logging
from app.services.query_service import DatabaseQueryService
from app.slack.handlers import BotHandlers


def configure_observability(settings: Settings) -> None:
    os.environ["LANGSMITH_TRACING"] = "true" if settings.langsmith_tracing else "false"
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint
    if settings.langsmith_api_key is not None:
        if api_key_value := settings.langsmith_api_key.get_secret_value():
            os.environ["LANGSMITH_API_KEY"] = api_key_value
    logger.info(f"LangSmith tracing enabled: {settings.langsmith_tracing}")


def create_app(settings: Settings, checkpointer=None) -> AsyncApp:
    logger.info("Creating Slack app instance")
    resolved_settings = settings or load_settings()
    configure_observability(resolved_settings)
    app = AsyncApp(
        token=resolved_settings.slack_bot_token.get_secret_value(),
        signing_secret=resolved_settings.slack_signing_secret.get_secret_value(),
    )

    resolved_checkpointer = checkpointer or MemorySaver()
    graph = build_graph(
        GeminiClient(resolved_settings),
        query_service=DatabaseQueryService.from_settings(resolved_settings),
        checkpointer=resolved_checkpointer,
    )
    BotHandlers(graph, settings).register(app)
    logger.info("Slack app instance created successfully")
    return app


def create_socket_mode_handler(app: AsyncApp, settings: Settings | None = None) -> AsyncSocketModeHandler:
    logger.info("Creating Socket Mode handler")
    resolved_settings = settings or load_settings()
    handler = AsyncSocketModeHandler(app, resolved_settings.slack_app_token.get_secret_value())
    logger.info("Socket Mode handler created successfully")
    return handler


async def run() -> None:
    setup_logging()
    logger.info("Starting Rounds Challenge Slack Bot")
    settings = load_settings()

    # Automatic seeding on startup
    if settings.postgres_host != "localhost":
        logger.info(f"Checking/Seeding database at {settings.postgres_host}...")
        try:
            from init_db.seed_data import seed_database

            inserted = await seed_database(settings.write_database_url)
            logger.info(f"Database seeded successfully with {inserted} rows")
        except ImportError:
            logger.warning("init_db.seed_data not found — skipping auto-seed")
        except Exception as e:
            logger.error(f"Seeding failed: {e}")
    else:
        logger.info("Skipping automatic seeding (localhost detected)")

    async with postgres_checkpointer(settings) as checkpointer:
        app = create_app(settings, checkpointer=checkpointer)
        handler = create_socket_mode_handler(app, settings)
        logger.info("Starting Socket Mode handler...")
        await handler.start_async()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
