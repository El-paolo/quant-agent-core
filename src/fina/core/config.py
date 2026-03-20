"""
Application settings loaded from environment variables and .env file.

Uses pydantic-settings so every variable is validated at startup.
Agent-specific keys (Anthropic, NewsAPI) are optional at import time —
call validate_for_agent() before invoking any agent functionality.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from fina.core.exceptions import ConfigError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # silently ignore unknown env vars (common in CI)
    )

    anthropic_api_key: str = ""
    news_api_key: str = ""
    log_level: str = "INFO"
    cors_origins: list[str] = ["*"]

    def validate_for_agent(self) -> None:
        """
        Raise ConfigError if keys required for agent features are missing.

        Call this at the start of any function that uses the Anthropic API
        or NewsAPI, rather than at application startup. This allows the API
        to serve /health and /analysis/ endpoints without agent credentials.

        Raises:
            ConfigError: If anthropic_api_key or news_api_key is empty.
        """
        if not self.anthropic_api_key:
            raise ConfigError(
                "ANTHROPIC_API_KEY is required for agent routes. "
                "Set it in your .env file or as an environment variable."
            )
        if not self.news_api_key:
            raise ConfigError(
                "NEWS_API_KEY is required for news fetching. "
                "Set it in your .env file or as an environment variable."
            )


def get_settings() -> Settings:
    """Return a Settings instance loaded from the environment."""
    return Settings()
