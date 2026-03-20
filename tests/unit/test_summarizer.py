"""
Unit tests for fina.agent.summarizer

OllamaProvider is mocked via pytest-httpx — no real Ollama needed.
"""

import pytest
from pytest_httpx import HTTPXMock

from fina.agent.summarizer import get_provider, summarize_news
from fina.core.config import Settings
from fina.core.exceptions import ConfigError, FetcherError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ollama_settings(**kwargs) -> Settings:
    defaults = dict(
        llm_provider="ollama",
        ollama_base_url="http://localhost:11434",
        ollama_model="llama3.2:3b",
        news_api_key="news-key",
    )
    defaults.update(kwargs)
    return Settings(**defaults)


def _headlines(n: int = 3) -> list[dict]:
    return [
        {
            "title": f"AAPL headline {i}",
            "description": "",
            "url": "",
            "publishedAt": f"2025-01-0{i+1}T00:00:00Z",
        }
        for i in range(n)
    ]


def _ollama_response(text: str = "Summary text") -> dict:
    return {"message": {"role": "assistant", "content": text}, "done": True}


# ---------------------------------------------------------------------------
# summarize_news
# ---------------------------------------------------------------------------


class TestSummarizeNews:
    def test_returns_string(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_ollama_response("Market summary"))
        result = summarize_news("AAPL", _headlines(), _ollama_settings())
        assert isinstance(result, str)

    def test_returns_provider_response(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_ollama_response("Strong bullish sentiment"))
        result = summarize_news("AAPL", _headlines(), _ollama_settings())
        assert result == "Strong bullish sentiment"

    def test_empty_headlines_returns_graceful_message(self) -> None:
        result = summarize_news("AAPL", [], _ollama_settings())
        assert "AAPL" in result
        assert "No recent news" in result

    def test_empty_headlines_does_not_call_provider(
        self, httpx_mock: HTTPXMock
    ) -> None:
        summarize_news("AAPL", [], _ollama_settings())
        assert len(httpx_mock.get_requests()) == 0

    def test_ticker_appears_in_default_prompt(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_ollama_response("ok"))
        summarize_news("MSFT", _headlines(), _ollama_settings())
        import json
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert "MSFT" in body["messages"][0]["content"]

    def test_custom_prompt_overrides_default(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_ollama_response("ok"))
        summarize_news("AAPL", _headlines(), _ollama_settings(), prompt="Custom prompt here")
        import json
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        assert "Custom prompt here" in body["messages"][0]["content"]

    def test_missing_news_key_raises_config_error(self) -> None:
        s = _ollama_settings(news_api_key="")
        with pytest.raises(ConfigError, match="NEWS_API_KEY"):
            summarize_news("AAPL", _headlines(), s)

    def test_provider_error_raises_fetcher_error(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(status_code=500)
        with pytest.raises(FetcherError):
            summarize_news("AAPL", _headlines(), _ollama_settings())

    def test_headlines_dates_appear_in_prompt(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_ollama_response("ok"))
        summarize_news("AAPL", _headlines(2), _ollama_settings())
        import json
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        assert "2025-01-01" in prompt

    def test_multiple_headlines_all_included(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_ollama_response("ok"))
        headlines = _headlines(5)
        summarize_news("AAPL", headlines, _ollama_settings())
        import json
        request = httpx_mock.get_requests()[0]
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        for h in headlines:
            assert h["title"] in prompt


# ---------------------------------------------------------------------------
# get_provider
# ---------------------------------------------------------------------------


class TestGetProviderFactory:
    def test_ollama_returns_ollama_provider(self) -> None:
        from fina.agent.providers.ollama import OllamaProvider
        s = _ollama_settings()
        provider = get_provider(s)
        assert isinstance(provider, OllamaProvider)

    def test_unknown_provider_raises(self) -> None:
        s = Settings(llm_provider="gemini", news_api_key="key")
        with pytest.raises(ConfigError):
            get_provider(s)

    def test_anthropic_raises_not_implemented(self) -> None:
        s = Settings(
            llm_provider="anthropic",
            anthropic_api_key="sk-test",
            news_api_key="key",
        )
        with pytest.raises(ConfigError, match="not yet implemented"):
            get_provider(s)
