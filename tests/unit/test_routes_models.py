"""
Unit tests for /models/ and /models/timeseries/ API routes.

Business logic is mocked — routes are tested in isolation.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fina.api.main import create_app
from fina.core.config import Settings
from fina.core.exceptions import FetcherError


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(settings=Settings()))


# Realistic mock return values
_MOCK_MODELS_RESULT = {
    "garch": {
        "forecast": [
            {"day": 1, "volatility": 0.015, "upper": 0.020, "lower": 0.010},
        ],
        "diagnostics": {
            "omega": 1e-5, "alpha": 0.05, "beta": 0.90,
            "persistence": 0.95, "aic": 100.0, "bic": 110.0,
            "long_run_vol": 0.014,
        },
        "horizon": 5,
        "observations": 200,
        "confidence": 0.95,
    },
    "hmm": {
        "current_regime": {
            "label": "low_vol", "label_es": "Baja volatilidad",
            "since_date": "2024-12-01", "duration_days": 10,
        },
        "state_params": [
            {"label": "low_vol", "label_es": "Baja volatilidad",
             "mean_return": 0.001, "std": 0.01, "annualized_vol": 0.16,
             "stationary_prob": 0.5},
        ],
        "distributions": [
            {"label": "low_vol", "label_es": "Baja volatilidad",
             "mean": 0.001, "std": 0.01, "x": [0.0, 0.1], "pdf": [10.0, 5.0]},
        ],
        "transition_matrix": [[0.95, 0.05], [0.10, 0.90]],
        "split": {"train_size": 160, "test_size": 40, "train_ratio": 0.80},
        "train_score": 2.5,
        "test_score": 2.4,
        "n_states": 3,
        "observations": 200,
        "aic": 50.0,
        "bic": 60.0,
    },
    "warnings": [],
}

_MOCK_TIMESERIES_RESULT = {
    "garch_vol": [{"date": "2024-01-01", "value": 0.015}],
    "garch_forecast": [{"day": 1, "volatility": 0.015, "upper": 0.020, "lower": 0.010}],
    "hmm_states": [{"date": "2024-01-01", "state": 0, "label": "low_vol"}],
    "warnings": [],
}


class TestModelsRoute:
    @patch("fina.api.routes.models.run_models", return_value=_MOCK_MODELS_RESULT)
    def test_success(self, mock_run, client: TestClient) -> None:
        r = client.post("/models/", json={"ticker": "AAPL", "period": "1y"})
        assert r.status_code == 200
        data = r.json()
        assert data["ticker"] == "AAPL"
        assert data["period"] == "1y"
        assert data["garch"] is not None
        assert data["hmm"] is not None
        assert isinstance(data["warnings"], list)

    @patch("fina.api.routes.models.run_models", return_value=_MOCK_MODELS_RESULT)
    def test_hmm_has_distributions(self, mock_run, client: TestClient) -> None:
        r = client.post("/models/", json={"ticker": "AAPL"})
        hmm = r.json()["hmm"]
        assert "distributions" in hmm
        assert "split" in hmm
        assert "train_score" in hmm
        assert "test_score" in hmm

    @patch("fina.api.routes.models.run_models", side_effect=FetcherError("bad ticker"))
    def test_fetcher_error_returns_422(self, mock_run, client: TestClient) -> None:
        r = client.post("/models/", json={"ticker": "AAPL"})
        assert r.status_code == 422

    def test_invalid_ticker_returns_422(self, client: TestClient) -> None:
        r = client.post("/models/", json={"ticker": "!!!"})
        assert r.status_code == 422

    def test_invalid_period_returns_422(self, client: TestClient) -> None:
        r = client.post("/models/", json={"ticker": "AAPL", "period": "99x"})
        assert r.status_code == 422

    def test_invalid_hmm_states_returns_422(self, client: TestClient) -> None:
        r = client.post("/models/", json={"ticker": "AAPL", "hmm_states": 5})
        assert r.status_code == 422

    @patch("fina.api.routes.models.run_models", side_effect=RuntimeError("boom"))
    def test_unexpected_error_returns_500(self, mock_run, client: TestClient) -> None:
        r = client.post("/models/", json={"ticker": "AAPL"})
        assert r.status_code == 500


class TestModelsTimeseriesRoute:
    @patch("fina.api.routes.models.run_models_timeseries", return_value=_MOCK_TIMESERIES_RESULT)
    def test_success(self, mock_run, client: TestClient) -> None:
        r = client.post("/models/timeseries/", json={"ticker": "AAPL", "period": "1y"})
        assert r.status_code == 200
        data = r.json()
        assert data["ticker"] == "AAPL"
        assert isinstance(data["garch_vol"], list)
        assert isinstance(data["garch_forecast"], list)
        assert isinstance(data["hmm_states"], list)

    @patch("fina.api.routes.models.run_models_timeseries", side_effect=FetcherError("not found"))
    def test_fetcher_error_returns_422(self, mock_run, client: TestClient) -> None:
        r = client.post("/models/timeseries/", json={"ticker": "AAPL"})
        assert r.status_code == 422

    @patch("fina.api.routes.models.run_models_timeseries", side_effect=RuntimeError("boom"))
    def test_unexpected_error_returns_500(self, mock_run, client: TestClient) -> None:
        r = client.post("/models/timeseries/", json={"ticker": "AAPL"})
        assert r.status_code == 500
