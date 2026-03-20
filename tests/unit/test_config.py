"""
Unit tests for fina.core.config

Covers: Settings defaults, env var loading, validate_for_agent.
"""

import pytest

from fina.core.config import Settings, get_settings
from fina.core.exceptions import ConfigError


class TestSettings:
    def test_default_keys_are_empty(self) -> None:
        s = Settings()
        assert s.anthropic_api_key == ""
        assert s.news_api_key == ""

    def test_keys_set_via_constructor(self) -> None:
        s = Settings(anthropic_api_key="sk-test", news_api_key="news-key")
        assert s.anthropic_api_key == "sk-test"
        assert s.news_api_key == "news-key"

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

    def test_extra_env_vars_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SOME_UNKNOWN_VAR", "value")
        # Should not raise
        s = Settings()
        assert isinstance(s, Settings)

    def test_get_settings_returns_settings(self) -> None:
        s = get_settings()
        assert isinstance(s, Settings)


class TestValidateForAgent:
    def test_passes_when_both_keys_set(self) -> None:
        s = Settings(anthropic_api_key="sk-test", news_api_key="news-key")
        s.validate_for_agent()  # should not raise

    def test_raises_when_anthropic_key_missing(self) -> None:
        s = Settings(anthropic_api_key="", news_api_key="news-key")
        with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
            s.validate_for_agent()

    def test_raises_when_news_key_missing(self) -> None:
        s = Settings(anthropic_api_key="sk-test", news_api_key="")
        with pytest.raises(ConfigError, match="NEWS_API_KEY"):
            s.validate_for_agent()

    def test_raises_when_both_keys_missing(self) -> None:
        s = Settings()
        with pytest.raises(ConfigError):
            s.validate_for_agent()

    def test_error_message_is_descriptive(self) -> None:
        s = Settings(anthropic_api_key="", news_api_key="x")
        with pytest.raises(ConfigError) as exc_info:
            s.validate_for_agent()
        assert "ANTHROPIC_API_KEY" in str(exc_info.value)
