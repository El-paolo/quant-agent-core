"""
Unit tests for api/routes/agent.py — POST /agent/summarize/

fetch_news_headlines and summarize_news are always mocked.
Settings are injected via FastAPI dependency_overrides.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fina.api.dependencies import get_settings_dep
from fina.api.main import create_app
from fina.core.config import Settings
from fina.core.exceptions import ConfigError, FetcherError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _agent_settings() -> Settings:
    return Settings(
        llm_provider="ollama",
        news_api_key="test-news-key",
        anthropic_api_key="",
    )


def _empty_settings() -> Settings:
    return Settings(news_api_key="", anthropic_api_key="")


@pytest.fixture
def client() -> TestClient:
    """App with valid agent settings injected via dependency override."""
    app = create_app()
    app.dependency_overrides[get_settings_dep] = _agent_settings
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def client_no_keys() -> TestClient:
    """App with empty settings — agent routes should fail."""
    app = create_app()
    app.dependency_overrides[get_settings_dep] = _empty_settings
    return TestClient(app, raise_server_exceptions=False)


_HEADLINES = [
    {
        "title": "AAPL hits record high",
        "description": "Apple shares surged...",
        "url": "https://example.com/1",
        "publishedAt": "2025-01-01T12:00:00Z",
    }
]

_SUMMARY = "Apple reported strong quarterly earnings driven by iPhone sales."


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestAgentSummarizeHappyPath:
    def test_returns_200(self, client: TestClient) -> None:
        with patch("fina.api.routes.agent.fetch_news_headlines", return_value=_HEADLINES), \
             patch("fina.api.routes.agent.summarize_news", return_value=_SUMMARY):
            r = client.post("/agent/summarize/", json={"ticker": "AAPL"})
        assert r.status_code == 200

    def test_response_has_required_keys(self, client: TestClient) -> None:
        with patch("fina.api.routes.agent.fetch_news_headlines", return_value=_HEADLINES), \
             patch("fina.api.routes.agent.summarize_news", return_value=_SUMMARY):
            r = client.post("/agent/summarize/", json={"ticker": "AAPL"})
        body = r.json()
        assert "ticker" in body
        assert "summary" in body
        assert "headlines" in body

    def test_ticker_normalized_to_uppercase(self, client: TestClient) -> None:
        with patch("fina.api.routes.agent.fetch_news_headlines", return_value=_HEADLINES), \
             patch("fina.api.routes.agent.summarize_news", return_value=_SUMMARY):
            r = client.post("/agent/summarize/", json={"ticker": "aapl"})
        assert r.json()["ticker"] == "AAPL"

    def test_summary_in_response(self, client: TestClient) -> None:
        with patch("fina.api.routes.agent.fetch_news_headlines", return_value=_HEADLINES), \
             patch("fina.api.routes.agent.summarize_news", return_value=_SUMMARY):
            r = client.post("/agent/summarize/", json={"ticker": "AAPL"})
        assert r.json()["summary"] == _SUMMARY

    def test_headlines_titles_in_response(self, client: TestClient) -> None:
        with patch("fina.api.routes.agent.fetch_news_headlines", return_value=_HEADLINES), \
             patch("fina.api.routes.agent.summarize_news", return_value=_SUMMARY):
            r = client.post("/agent/summarize/", json={"ticker": "AAPL"})
        assert "AAPL hits record high" in r.json()["headlines"]

    def test_empty_headlines_handled_gracefully(self, client: TestClient) -> None:
        with patch("fina.api.routes.agent.fetch_news_headlines", return_value=[]), \
             patch("fina.api.routes.agent.summarize_news", return_value="No recent news found for AAPL."):
            r = client.post("/agent/summarize/", json={"ticker": "AAPL"})
        assert r.status_code == 200
        assert r.json()["headlines"] == []

    def test_custom_prompt_accepted(self, client: TestClient) -> None:
        with patch("fina.api.routes.agent.fetch_news_headlines", return_value=_HEADLINES) as mock_news, \
             patch("fina.api.routes.agent.summarize_news", return_value=_SUMMARY) as mock_sum:
            r = client.post(
                "/agent/summarize/",
                json={"ticker": "AAPL", "summary_prompt": "Focus on risks only."},
            )
        assert r.status_code == 200
        # Verify custom prompt was passed to summarize_news
        call_kwargs = mock_sum.call_args
        assert call_kwargs.kwargs.get("prompt") == "Focus on risks only."

    def test_multiple_headlines_all_in_response(self, client: TestClient) -> None:
        many = [
            {"title": f"Headline {i}", "description": "", "url": "", "publishedAt": ""}
            for i in range(5)
        ]
        with patch("fina.api.routes.agent.fetch_news_headlines", return_value=many), \
             patch("fina.api.routes.agent.summarize_news", return_value="Summary"):
            r = client.post("/agent/summarize/", json={"ticker": "AAPL"})
        assert len(r.json()["headlines"]) == 5


# ---------------------------------------------------------------------------
# Input validation (handled by Pydantic before route runs)
# ---------------------------------------------------------------------------


class TestAgentSummarizeInputValidation:
    def test_invalid_ticker_returns_422(self, client: TestClient) -> None:
        r = client.post("/agent/summarize/", json={"ticker": "INVALID TICKER!"})
        assert r.status_code == 422

    def test_missing_ticker_returns_422(self, client: TestClient) -> None:
        r = client.post("/agent/summarize/", json={})
        assert r.status_code == 422

    def test_sql_injection_ticker_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/agent/summarize/",
            json={"ticker": "AAPL; DROP TABLE news"},
        )
        assert r.status_code == 422

    def test_missing_body_returns_422(self, client: TestClient) -> None:
        r = client.post("/agent/summarize/")
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


class TestAgentSummarizeErrorMapping:
    def test_config_error_returns_503(self, client_no_keys: TestClient) -> None:
        with patch(
            "fina.api.routes.agent.fetch_news_headlines",
            side_effect=ConfigError("NEWS_API_KEY missing"),
        ):
            r = client_no_keys.post("/agent/summarize/", json={"ticker": "AAPL"})
        assert r.status_code == 503

    def test_news_fetch_error_returns_502(self, client: TestClient) -> None:
        with patch(
            "fina.api.routes.agent.fetch_news_headlines",
            side_effect=FetcherError("NewsAPI timeout"),
        ):
            r = client.post("/agent/summarize/", json={"ticker": "AAPL"})
        assert r.status_code == 502

    def test_llm_error_returns_502(self, client: TestClient) -> None:
        with patch("fina.api.routes.agent.fetch_news_headlines", return_value=_HEADLINES), \
             patch(
                 "fina.api.routes.agent.summarize_news",
                 side_effect=FetcherError("Ollama not running"),
             ):
            r = client.post("/agent/summarize/", json={"ticker": "AAPL"})
        assert r.status_code == 502

    def test_unexpected_error_returns_500(self, client: TestClient) -> None:
        with patch(
            "fina.api.routes.agent.fetch_news_headlines",
            side_effect=RuntimeError("unexpected crash"),
        ):
            r = client.post("/agent/summarize/", json={"ticker": "AAPL"})
        assert r.status_code == 500

    def test_error_detail_in_response_for_502(self, client: TestClient) -> None:
        with patch(
            "fina.api.routes.agent.fetch_news_headlines",
            side_effect=FetcherError("NewsAPI rate limit"),
        ):
            r = client.post("/agent/summarize/", json={"ticker": "AAPL"})
        assert "NewsAPI rate limit" in r.json()["detail"]


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


class TestAgentRouteRegistration:
    def test_agent_route_registered(self) -> None:
        app = create_app()
        paths = [r.path for r in app.routes]
        assert "/agent/summarize/" in paths

    def test_route_accepts_post_only(self, client: TestClient) -> None:
        r = client.get("/agent/summarize/")
        assert r.status_code == 405  # Method Not Allowed
