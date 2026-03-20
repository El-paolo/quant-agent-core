"""
Unit tests for fina.agent.news

All HTTP calls are intercepted by pytest-httpx — no real NewsAPI requests made.
"""

import pytest
from pytest_httpx import HTTPXMock

from fina.agent.news import fetch_news_headlines
from fina.core.config import Settings
from fina.core.exceptions import ConfigError, FetcherError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(news_key: str = "test-key") -> Settings:
    return Settings(llm_provider="ollama", news_api_key=news_key)


def _newsapi_ok(n: int = 3) -> dict:
    return {
        "status": "ok",
        "totalResults": n,
        "articles": [
            {
                "title": f"Headline {i}",
                "description": f"Description {i}",
                "url": f"https://example.com/{i}",
                "publishedAt": f"2025-01-0{i+1}T12:00:00Z",
            }
            for i in range(n)
        ],
    }


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestFetchNewsHeadlinesHappyPath:
    def test_returns_list(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_newsapi_ok())
        result = fetch_news_headlines("AAPL", _settings())
        assert isinstance(result, list)

    def test_each_item_is_dict(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_newsapi_ok())
        result = fetch_news_headlines("AAPL", _settings())
        for item in result:
            assert isinstance(item, dict)

    def test_required_keys_present(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_newsapi_ok(1))
        result = fetch_news_headlines("AAPL", _settings())
        assert "title" in result[0]
        assert "description" in result[0]
        assert "url" in result[0]
        assert "publishedAt" in result[0]

    def test_correct_number_of_articles(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_newsapi_ok(5))
        result = fetch_news_headlines("AAPL", _settings(), max_articles=5)
        assert len(result) == 5

    def test_max_articles_respected(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_newsapi_ok(10))
        result = fetch_news_headlines("AAPL", _settings(), max_articles=3)
        assert len(result) <= 3

    def test_articles_without_title_skipped(self, httpx_mock: HTTPXMock) -> None:
        payload = {
            "status": "ok",
            "articles": [
                {"title": "Real headline", "description": "", "url": "", "publishedAt": ""},
                {"title": None, "description": "no title", "url": "", "publishedAt": ""},
                {"title": "", "description": "empty title", "url": "", "publishedAt": ""},
            ],
        }
        httpx_mock.add_response(json=payload)
        result = fetch_news_headlines("AAPL", _settings())
        assert len(result) == 1
        assert result[0]["title"] == "Real headline"

    def test_empty_articles_returns_empty_list(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json={"status": "ok", "articles": []})
        result = fetch_news_headlines("AAPL", _settings())
        assert result == []

    def test_api_key_sent_in_params(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_newsapi_ok())
        fetch_news_headlines("AAPL", _settings(news_key="my-secret-key"))
        request = httpx_mock.get_requests()[0]
        assert "my-secret-key" in str(request.url)

    def test_query_sent_in_params(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json=_newsapi_ok())
        fetch_news_headlines("BTC-USD", _settings())
        request = httpx_mock.get_requests()[0]
        assert "BTC" in str(request.url)


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestFetchNewsHeadlinesErrors:
    def test_missing_news_key_raises_config_error(self) -> None:
        s = _settings(news_key="")
        with pytest.raises(ConfigError, match="NEWS_API_KEY"):
            fetch_news_headlines("AAPL", s)

    def test_http_401_raises_fetcher_error(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(status_code=401)
        with pytest.raises(FetcherError, match="HTTP error"):
            fetch_news_headlines("AAPL", _settings())

    def test_http_500_raises_fetcher_error(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(status_code=500)
        with pytest.raises(FetcherError, match="HTTP error"):
            fetch_news_headlines("AAPL", _settings())

    def test_newsapi_error_status_raises_fetcher_error(self, httpx_mock: HTTPXMock) -> None:
        httpx_mock.add_response(json={"status": "error", "message": "Invalid API key"})
        with pytest.raises(FetcherError, match="non-ok status"):
            fetch_news_headlines("AAPL", _settings())

    def test_network_error_raises_fetcher_error(self, httpx_mock: HTTPXMock) -> None:
        import httpx as _httpx
        httpx_mock.add_exception(_httpx.ConnectError("DNS failure"))
        with pytest.raises(FetcherError):
            fetch_news_headlines("AAPL", _settings())

    def test_timeout_raises_fetcher_error(self, httpx_mock: HTTPXMock) -> None:
        import httpx as _httpx
        httpx_mock.add_exception(_httpx.TimeoutException("timed out"))
        with pytest.raises(FetcherError, match="timed out"):
            fetch_news_headlines("AAPL", _settings())
