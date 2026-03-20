"""
Unit tests for fina.api.main and route endpoints.

Covers: app factory, health route, analysis route, middleware, schemas.
All business logic is mocked — routes are tested in isolation.
"""

import pytest
from fastapi.testclient import TestClient

from fina.api.main import create_app
from fina.core.config import Settings
from fina.core.exceptions import FetcherError, MetricsError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """TestClient with no real env vars — uses default empty settings."""
    return TestClient(create_app(settings=Settings()))


@pytest.fixture
def client_with_keys() -> TestClient:
    """TestClient with fake agent keys (for agent route tests later)."""
    s = Settings(anthropic_api_key="sk-test", news_api_key="news-key")
    return TestClient(create_app(settings=s))


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


class TestCreateApp:
    def test_returns_fastapi_instance(self) -> None:
        from fastapi import FastAPI
        app = create_app(settings=Settings())
        assert isinstance(app, FastAPI)

    def test_title_is_set(self) -> None:
        app = create_app(settings=Settings())
        assert "FINA" in app.title

    def test_health_route_registered(self) -> None:
        app = create_app(settings=Settings())
        paths = [r.path for r in app.routes]
        assert "/health" in paths

    def test_analysis_route_registered(self) -> None:
        app = create_app(settings=Settings())
        paths = [r.path for r in app.routes]
        assert "/analysis/" in paths

    def test_custom_settings_accepted(self) -> None:
        s = Settings(cors_origins=["https://example.com"])
        app = create_app(settings=s)
        assert isinstance(app, type(create_app()))


# ---------------------------------------------------------------------------
# GET /health
# ---------------------------------------------------------------------------


class TestHealthRoute:
    def test_returns_200(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.status_code == 200

    def test_body_has_status_ok(self, client: TestClient) -> None:
        r = client.get("/health")
        assert r.json()["status"] == "ok"

    def test_body_has_version(self, client: TestClient) -> None:
        r = client.get("/health")
        assert "version" in r.json()

    def test_process_time_header_present(self, client: TestClient) -> None:
        r = client.get("/health")
        assert "X-Process-Time-Ms" in r.headers


# ---------------------------------------------------------------------------
# POST /analysis/
# ---------------------------------------------------------------------------


class TestAnalysisRoute:
    def test_valid_request_returns_200(self, client: TestClient) -> None:
        from unittest.mock import patch
        with patch("fina.api.routes.analysis.run_analysis", return_value={}):
            r = client.post("/analysis/", json={"ticker": "AAPL", "period": "1y"})
        assert r.status_code == 200

    def test_response_has_status_and_data(self, client: TestClient) -> None:
        from unittest.mock import patch
        with patch("fina.api.routes.analysis.run_analysis", return_value={}):
            r = client.post("/analysis/", json={"ticker": "AAPL", "period": "1y"})
        body = r.json()
        assert body["status"] == "ok"
        assert "data" in body

    def test_response_ticker_matches_request(self, client: TestClient) -> None:
        from unittest.mock import patch
        with patch("fina.api.routes.analysis.run_analysis", return_value={}):
            r = client.post("/analysis/", json={"ticker": "msft", "period": "1y"})
        assert r.json()["data"]["ticker"] == "MSFT"  # normalized to uppercase

    def test_invalid_ticker_returns_422(self, client: TestClient) -> None:
        r = client.post("/analysis/", json={"ticker": "INVALID TICKER!", "period": "1y"})
        assert r.status_code == 422

    def test_invalid_period_returns_422(self, client: TestClient) -> None:
        r = client.post("/analysis/", json={"ticker": "AAPL", "period": "999y"})
        assert r.status_code == 422

    def test_unknown_metric_returns_422(self, client: TestClient) -> None:
        r = client.post(
            "/analysis/",
            json={"ticker": "AAPL", "period": "1y", "metrics": ["fake_metric"]},
        )
        assert r.status_code == 422

    def test_fetcher_error_returns_422(self, client: TestClient) -> None:
        from unittest.mock import patch
        with patch(
            "fina.api.routes.analysis.run_analysis",
            side_effect=FetcherError("no data"),
        ):
            r = client.post("/analysis/", json={"ticker": "AAPL", "period": "1y"})
        assert r.status_code == 422

    def test_metrics_error_returns_422(self, client: TestClient) -> None:
        from unittest.mock import patch
        with patch(
            "fina.api.routes.analysis.run_analysis",
            side_effect=MetricsError("bad metric"),
        ):
            r = client.post("/analysis/", json={"ticker": "AAPL", "period": "1y"})
        assert r.status_code == 422

    def test_unexpected_error_returns_500(self, client: TestClient) -> None:
        from unittest.mock import patch
        with patch(
            "fina.api.routes.analysis.run_analysis",
            side_effect=RuntimeError("boom"),
        ):
            r = client.post("/analysis/", json={"ticker": "AAPL", "period": "1y"})
        assert r.status_code == 500

    def test_missing_body_returns_422(self, client: TestClient) -> None:
        r = client.post("/analysis/")
        assert r.status_code == 422

    def test_sql_injection_ticker_rejected(self, client: TestClient) -> None:
        r = client.post(
            "/analysis/",
            json={"ticker": "AAPL; DROP TABLE prices", "period": "1y"},
        )
        assert r.status_code == 422

    def test_computed_dict_in_response(self, client: TestClient) -> None:
        from unittest.mock import patch
        payload = {"returns": {"mean": 0.001}, "sharpe": {"sharpe_ratio": 1.5}}
        with patch("fina.api.routes.analysis.run_analysis", return_value=payload):
            r = client.post("/analysis/", json={"ticker": "AAPL", "period": "1y"})
        assert r.json()["data"]["computed"] == payload


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemas:
    def test_analysis_request_normalizes_ticker(self) -> None:
        from fina.api.schemas import AnalysisRequest
        req = AnalysisRequest(ticker="  aapl  ", period="1y")
        assert req.ticker == "AAPL"

    def test_analysis_request_default_metrics(self) -> None:
        from fina.api.schemas import AnalysisRequest
        req = AnalysisRequest(ticker="AAPL")
        assert len(req.metrics) > 0

    def test_health_response_shape(self) -> None:
        from fina.api.schemas import HealthResponse
        h = HealthResponse(status="ok", version="0.1.0")
        assert h.status == "ok"
        assert h.version == "0.1.0"
