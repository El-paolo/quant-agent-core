"""
Application settings loaded from environment variables and .env file.

Uses pydantic-settings so every variable is validated at startup.
Agent-specific keys are optional at import time — call validate_for_agent()
before invoking any agent functionality.

LLM provider selection:
  LLM_PROVIDER=ollama     (default) — local Ollama, no API key required
  LLM_PROVIDER=anthropic  — Anthropic API, requires ANTHROPIC_API_KEY
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from fina.core.exceptions import ConfigError

_VALID_PROVIDERS = frozenset({"ollama", "anthropic"})


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # silently ignore unknown env vars (common in CI)
    )

    # --- LLM provider ---
    llm_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5-coder:latest"

    # --- External API keys (only required for their respective providers) ---
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-6"
    news_api_key: str = ""

    # --- App settings ---
    log_level: str = "INFO"
    cors_origins: list[str] = ["*"]

    def validate_for_agent(self) -> None:
        """
        Raise ConfigError if the configuration required for agent features is missing.

        - NEWS_API_KEY is always required (regardless of LLM provider).
        - ANTHROPIC_API_KEY is only required when llm_provider=anthropic.
        - ollama settings are always present (have defaults).

        Call this at request time, not at startup, so /health and /analysis/
        work without agent credentials.

        Raises:
            ConfigError: On missing keys or unknown provider.
        """
        if self.llm_provider not in _VALID_PROVIDERS:
            raise ConfigError(
                f"Unknown LLM provider '{self.llm_provider}'. "
                f"Valid options: {sorted(_VALID_PROVIDERS)}."
            )
        if not self.news_api_key:
            raise ConfigError(
                "NEWS_API_KEY is required for news fetching. "
                "Set it in your .env file or as an environment variable."
            )
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            raise ConfigError(
                "ANTHROPIC_API_KEY is required when LLM_PROVIDER=anthropic. "
                "Set it in your .env file or as an environment variable."
            )


def get_settings() -> Settings:
    """Return a Settings instance loaded from the environment."""
    return Settings()
