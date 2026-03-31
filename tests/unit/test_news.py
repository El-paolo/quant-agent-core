"""
Unit tests for fina.agent.news

yfinance calls are mocked via unittest.mock — no real network requests made.
"""

from unittest.mock import MagicMock, patch

import pytest

from fina.agent.news import fetch_news_headlines
from fina.core.config import Settings
from fina.core.exceptions import FetcherError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings() -> Settings:
    return Settings(llm_provider="ollama")


def _yf_article(i: int) -> dict:
    """Simulate a yfinance news article structure."""
    return {
        "id": f"id-{i}",
        "content": {
            "title": f"Headline {i}",
            "summary": f"Description {i}",
            "pubDate": f"2025-01-0{i + 1}T12:00:00Z",
            "canonicalUrl": {"url": f"https://example.com/{i}"},
        },
    }


def _yf_articles(n: int = 3) -> list[dict]:
    return [_yf_article(i) for i in range(n)]


def _mock_ticker(articles: list[dict]) -> MagicMock:
    ticker = MagicMock()
    ticker.news = articles
    return ticker


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestFetchNewsHeadlinesHappyPath:
    def test_returns_list(self) -> None:
        with patch("fina.agent.news.yf.Ticker", return_value=_mock_ticker(_yf_articles())):
            result = fetch_news_headlines("AAPL", _settings())
        assert isinstance(result, list)

    def test_each_item_is_dict(self) -> None:
        with patch("fina.agent.news.yf.Ticker", return_value=_mock_ticker(_yf_articles())):
            result = fetch_news_headlines("AAPL", _settings())
        for item in result:
            assert isinstance(item, dict)

    def test_required_keys_present(self) -> None:
        with patch("fina.agent.news.yf.Ticker", return_value=_mock_ticker(_yf_articles(1))):
            result = fetch_news_headlines("AAPL", _settings())
        assert "title" in result[0]
        assert "description" in result[0]
        assert "url" in result[0]
        assert "publishedAt" in result[0]

    def test_correct_number_of_articles(self) -> None:
        with patch("fina.agent.news.yf.Ticker", return_value=_mock_ticker(_yf_articles(5))):
            result = fetch_news_headlines("AAPL", _settings(), max_articles=5)
        assert len(result) == 5

    def test_max_articles_respected(self) -> None:
        with patch("fina.agent.news.yf.Ticker", return_value=_mock_ticker(_yf_articles(10))):
            result = fetch_news_headlines("AAPL", _settings(), max_articles=3)
        assert len(result) <= 3

    def test_articles_without_title_skipped(self) -> None:
        articles = [
            {"content": {"title": "Real headline", "summary": "", "pubDate": "", "canonicalUrl": {"url": ""}}},
            {"content": {"title": None, "summary": "no title", "pubDate": "", "canonicalUrl": None}},
            {"content": {"title": "", "summary": "empty title", "pubDate": "", "canonicalUrl": None}},
        ]
        with patch("fina.agent.news.yf.Ticker", return_value=_mock_ticker(articles)):
            result = fetch_news_headlines("AAPL", _settings())
        assert len(result) == 1
        assert result[0]["title"] == "Real headline"

    def test_empty_articles_returns_empty_list(self) -> None:
        with patch("fina.agent.news.yf.Ticker", return_value=_mock_ticker([])):
            result = fetch_news_headlines("AAPL", _settings())
        assert result == []

    def test_publishedAt_mapped_from_pubDate(self) -> None:
        with patch("fina.agent.news.yf.Ticker", return_value=_mock_ticker(_yf_articles(1))):
            result = fetch_news_headlines("AAPL", _settings())
        assert result[0]["publishedAt"] == "2025-01-01T12:00:00Z"

    def test_url_mapped_from_canonicalUrl(self) -> None:
        with patch("fina.agent.news.yf.Ticker", return_value=_mock_ticker(_yf_articles(1))):
            result = fetch_news_headlines("AAPL", _settings())
        assert result[0]["url"] == "https://example.com/0"

    def test_description_mapped_from_summary(self) -> None:
        with patch("fina.agent.news.yf.Ticker", return_value=_mock_ticker(_yf_articles(1))):
            result = fetch_news_headlines("AAPL", _settings())
        assert result[0]["description"] == "Description 0"


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------


class TestFetchNewsHeadlinesErrors:
    def test_yfinance_exception_raises_fetcher_error(self) -> None:
        with patch("fina.agent.news.yf.Ticker", side_effect=Exception("network error")):
            with pytest.raises(FetcherError, match="Yahoo Finance"):
                fetch_news_headlines("AAPL", _settings())

    def test_missing_canonicalUrl_does_not_crash(self) -> None:
        articles = [{"content": {"title": "Title", "summary": "", "pubDate": "", "canonicalUrl": None}}]
        with patch("fina.agent.news.yf.Ticker", return_value=_mock_ticker(articles)):
            result = fetch_news_headlines("AAPL", _settings())
        assert result[0]["url"] == ""
