"""
Unit tests for fina.agent.providers

Covers: OllamaProvider.chat(), OllamaProvider.is_available(), get_provider().
All HTTP calls are intercepted by pytest-httpx — no real Ollama needed.
"""

import json

import pytest
from pytest_httpx import HTTPXMock

from fina.agent.providers.base import LLMProvider
from fina.agent.providers.ollama import OllamaProvider
from fina.agent.summarizer import get_provider
from fina.core.config import Settings
from fina.core.exceptions import ConfigError, FetcherError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ollama_response(text: str = "Test response") -> dict:
    return {
        "model": "llama3.2:3b",
        "message": {"role": "assistant", "content": text},
        "done": True,
    }


def _ollama_settings() -> Settings:
    return Settings(
        llm_provider="ollama",
        ollama_base_url="http://localhost:11434",
        ollama_model="llama3.2:3b",
        news_api_key="news-key",
    )


# ---------------------------------------------------------------------------
# OllamaProvider — protocol conformance
# ---------------------------------------------------------------------------


class TestOllamaProviderProtocol:
    def test_satisfies_llm_provider_protocol(self) -> None:
        provider = OllamaProvider()
        assert isinstance(provider, LLMProvider)

    def test_has_chat_method(self) -> None:
        provider = OllamaProvider()
        assert callable(provider.chat)

    def test_has_is_available_method(self) -> None:
        provider = OllamaProvider()
        assert callable(provider.is_available)


# ---------------------------------------------------------------------------
# OllamaProvider.chat()
# ---------------------------------------------------------------------------


class TestOllamaProviderChat:
    def test_returns_string(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_ollama_response("Hello"))
        provider = OllamaProvider()
        result = provider.chat("Say hello")
        assert isinstance(result, str)

    def test_returns_model_content(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_ollama_response("Financial summary here"))
        provider = OllamaProvider()
        result = provider.chat("Summarize AAPL news")
        assert result == "Financial summary here"

    def test_strips_whitespace(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_ollama_response("  trimmed  "))
        provider = OllamaProvider()
        result = provider.chat("prompt")
        assert result == "trimmed"

    def test_sends_prompt_in_request(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_ollama_response("ok"))
        provider = OllamaProvider()
        provider.chat("my custom prompt")
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert body["messages"][0]["content"] == "my custom prompt"

    def test_sends_correct_model(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_ollama_response("ok"))
        provider = OllamaProvider(model="llama3.2:3b")
        provider.chat("test")
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert body["model"] == "llama3.2:3b"

    def test_stream_is_false(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_ollama_response("ok"))
        provider = OllamaProvider()
        provider.chat("test")
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert body["stream"] is False

    def test_http_error_raises_fetcher_error(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(status_code=500)
        provider = OllamaProvider()
        with pytest.raises(FetcherError, match="HTTP error"):
            provider.chat("test")

    def test_connection_error_raises_fetcher_error(self, httpx_mock: HTTPXMock) -> None:
        import httpx as _httpx
        httpx_mock.add_exception(_httpx.ConnectError("Connection refused"))
        provider = OllamaProvider(base_url="http://localhost:9999")
        with pytest.raises(FetcherError):
            provider.chat("test")

    def test_malformed_response_raises_fetcher_error(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json={"unexpected": "format"})
        provider = OllamaProvider()
        with pytest.raises(FetcherError, match="Unexpected Ollama response"):
            provider.chat("test")

    def test_custom_base_url_used(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_ollama_response("ok"))
        provider = OllamaProvider(base_url="http://myserver:11434")
        provider.chat("test")
        request = httpx_mock.get_requests()[0]
        assert "myserver:11434" in str(request.url)


# ---------------------------------------------------------------------------
# OllamaProvider.is_available()
# ---------------------------------------------------------------------------


class TestOllamaProviderIsAvailable:
    def test_returns_true_when_server_responds(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(status_code=200, json={"models": []})
        provider = OllamaProvider()
        assert provider.is_available() is True

    def test_returns_false_when_server_down(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_exception(Exception("Connection refused"))
        provider = OllamaProvider()
        assert provider.is_available() is False

    def test_returns_false_on_http_error(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(status_code=503)
        provider = OllamaProvider()
        assert provider.is_available() is False


# ---------------------------------------------------------------------------
# get_provider() factory
# ---------------------------------------------------------------------------


class TestGetProvider:
    def test_ollama_provider_returned_for_ollama(self) -> None:
        s = _ollama_settings()
        provider = get_provider(s)
        assert isinstance(provider, OllamaProvider)

    def test_provider_satisfies_protocol(self) -> None:
        s = _ollama_settings()
        provider = get_provider(s)
        assert isinstance(provider, LLMProvider)

    def test_unknown_provider_raises_config_error(self) -> None:
        s = Settings(llm_provider="openai", news_api_key="key")
        with pytest.raises(ConfigError, match="Unknown LLM provider"):
            get_provider(s)

    def test_anthropic_provider_raises_not_implemented(self) -> None:
        s = Settings(
            llm_provider="anthropic",
            news_api_key="key",
            anthropic_api_key="sk-test",
        )
        with pytest.raises(ConfigError, match="not yet implemented"):
            get_provider(s)
