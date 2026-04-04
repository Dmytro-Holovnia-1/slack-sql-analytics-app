from functools import lru_cache

from loguru import logger
from pydantic import SecretStr, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict


class ConfigError(ValueError):
    """Raised when required environment variables are missing."""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Slack credentials
    slack_bot_token: SecretStr
    slack_app_token: SecretStr
    slack_signing_secret: SecretStr

    # Google/Gemini settings
    google_api_key: SecretStr
    gemini_standard_model: str
    gemini_low_cost_model: str
    gemini_transient_retry_max_retries: int = 3
    fallback_text: str = "Sorry, the assistant encountered an unexpected error. Please try again later."

    # LangSmith settings
    langsmith_tracing: bool = False
    langsmith_project: str = "rounds-slack-agent"
    langsmith_api_key: SecretStr | None = None
    langsmith_endpoint: str = "https://api.smith.langchain.com"

    # PostgreSQL settings
    postgres_db: str
    postgres_host: str
    postgres_port: int
    postgres_user: str
    postgres_password: SecretStr
    chatbot_db_user: str
    chatbot_db_password: SecretStr
    db_statement_timeout_ms: int = 5000

    # Application constants
    multi_row_threshold: int = 10
    multi_col_threshold: int = 3
    max_sql_repair_attempts: int = 3
    off_topic_response: str = (
        "I can only answer questions about the Rounds app portfolio analytics. "
        "Try asking about installs, revenue, UA costs, or app performance."
    )

    @property
    def repair_count_exhausted(self) -> int:
        return self.max_sql_repair_attempts + 1

    @property
    def readonly_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.chatbot_db_user}:{self.chatbot_db_password.get_secret_value()}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def write_database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def checkpointer_database_url(self) -> str:
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password.get_secret_value()}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


def load_settings() -> Settings:
    logger.info("Loading application settings")
    try:
        settings = Settings()
        logger.info(
            f"Settings loaded (standard model: {settings.gemini_standard_model}, low-cost: {settings.gemini_low_cost_model})"
        )
        return settings
    except ValidationError as e:
        logger.error(f"Configuration validation failed: {e}")
        raise ConfigError(f"Missing or invalid required environment variables: {e}") from e


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
