"""
Unit tests for fina.core.config

Covers: Settings defaults, env var loading, validate_for_agent with hybrid providers.
"""

import pytest

from fina.core.config import Settings, get_settings
from fina.core.exceptions import ConfigError


class TestSettings:
    def test_default_keys_are_empty(self) -> None:
        s = Settings()
        assert s.anthropic_api_key == ""
        assert s.news_api_key == ""

    def test_default_provider_is_ollama(self) -> None:
        s = Settings()
        assert s.llm_provider == "ollama"

    def test_ollama_defaults(self) -> None:
        s = Settings()
        assert "localhost" in s.ollama_base_url
        assert s.ollama_model != ""

    def test_keys_set_via_constructor(self) -> None:
        s = Settings(anthropic_api_key="sk-test", news_api_key="news-key")
        assert s.anthropic_api_key == "sk-test"
        assert s.news_api_key == "news-key"

    def test_provider_set_via_constructor(self) -> None:
        s = Settings(llm_provider="anthropic")
        assert s.llm_provider == "anthropic"

    def test_log_level_default(self) -> None:
        s = Settings()
        assert s.log_level == "INFO"

    def test_cors_origins_default(self) -> None:
        s = Settings()
        assert s.cors_origins == ["*"]

    def test_env_var_loaded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-test")
        s = Settings()
        assert s.anthropic_api_key == "sk-env-test"

    def test_llm_provider_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        s = Settings()
        assert s.llm_provider == "anthropic"

    def test_ollama_model_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")
        s = Settings()
        assert s.ollama_model == "llama3.2:3b"

    def test_extra_env_vars_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SOME_UNKNOWN_VAR", "value")
        s = Settings()
        assert isinstance(s, Settings)

    def test_get_settings_returns_settings(self) -> None:
        s = get_settings()
        assert isinstance(s, Settings)


class TestValidateForAgent:
    # --- Ollama provider (default) ---

    def test_ollama_passes_with_news_key_only(self) -> None:
        s = Settings(llm_provider="ollama", news_api_key="news-key")
        s.validate_for_agent()  # should not raise

    def test_ollama_raises_when_news_key_missing(self) -> None:
        s = Settings(llm_provider="ollama", news_api_key="")
        with pytest.raises(ConfigError, match="NEWS_API_KEY"):
            s.validate_for_agent()

    def test_ollama_does_not_require_anthropic_key(self) -> None:
        s = Settings(llm_provider="ollama", news_api_key="news-key", anthropic_api_key="")
        s.validate_for_agent()  # no error — anthropic key not needed for ollama

    # --- Anthropic provider ---

    def test_anthropic_passes_with_all_keys(self) -> None:
        s = Settings(
            llm_provider="anthropic",
            news_api_key="news-key",
            anthropic_api_key="sk-test",
        )
        s.validate_for_agent()

    def test_anthropic_raises_when_anthropic_key_missing(self) -> None:
        s = Settings(llm_provider="anthropic", news_api_key="news-key", anthropic_api_key="")
        with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
            s.validate_for_agent()

    def test_anthropic_raises_when_news_key_missing(self) -> None:
        s = Settings(llm_provider="anthropic", news_api_key="", anthropic_api_key="sk-test")
        with pytest.raises(ConfigError, match="NEWS_API_KEY"):
            s.validate_for_agent()

    # --- Unknown provider ---

    def test_unknown_provider_raises(self) -> None:
        s = Settings(llm_provider="openai", news_api_key="news-key")
        with pytest.raises(ConfigError, match="Unknown LLM provider"):
            s.validate_for_agent()

    def test_error_message_names_the_bad_provider(self) -> None:
        s = Settings(llm_provider="gpt5", news_api_key="news-key")
        with pytest.raises(ConfigError) as exc_info:
            s.validate_for_agent()
        assert "gpt5" in str(exc_info.value)
