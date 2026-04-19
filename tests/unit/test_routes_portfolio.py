"""
Unit tests for POST /backtest/portfolio/ route.

All tests mock the orchestration layer — no real data fetching or model fitting.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from fina.api.main import create_app
from fina.core.config import Settings
from fina.core.exceptions import BacktestError, FetcherError


@pytest.fixture
def client():
    settings = Settings(llm_provider="ollama")
    app = create_app(settings)
    return TestClient(app)


_MOCK_PORTFOLIO_RESULT = {
    "tickers": ["AAPL", "MSFT", "GOOGL"],
    "weights": {"AAPL": 0.3333, "MSFT": 0.3333, "GOOGL": 0.3334},
    "weight_scheme": "equal",
    "train_period": {"start": "2022-01-01", "end": "2023-06-30"},
    "test_period": {"start": "2023-07-01", "end": "2023-12-31"},
    "models_used": ["arima", "hmm", "garch"],
    "portfolio_metrics": {
        "var_95": -0.02,
        "cvar_95": -0.03,
        "portfolio_sharpe": 1.1,
        "effective_n": 2.5,
        "dsr": {"dsr": 0.85, "sr_benchmark": 0.5, "se": 0.06, "n_trials": 1, "n_obs": 126, "is_significant": False},
        "correlation_matrix": {"AAPL": {"MSFT": 0.6, "GOOGL": 0.5}, "MSFT": {"AAPL": 0.6, "GOOGL": 0.7}},
    },
    "per_asset": {
        "AAPL": {"metrics": {"strategy": {"sharpe_ratio": 1.0}}, "signal_summaries": {}},
        "MSFT": {"metrics": {"strategy": {"sharpe_ratio": 0.8}}, "signal_summaries": {}},
        "GOOGL": {"metrics": {"strategy": {"sharpe_ratio": 1.2}}, "signal_summaries": {}},
    },
    "portfolio_equity_curve": [{"date": "2023-07-03", "value": 10000.0}],
    "warnings": [],
}


class TestPortfolioRoute:
    @patch("fina.orchestration.backtest.run_portfolio_backtest")
    def test_happy_path(self, mock_pbt, client):
        mock_pbt.return_value = _MOCK_PORTFOLIO_RESULT
        resp = client.post("/backtest/portfolio/", json={
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "train_start": "2022-01-01",
            "train_end": "2023-06-30",
            "test_start": "2023-07-01",
            "test_end": "2023-12-31",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["tickers"] == ["AAPL", "MSFT", "GOOGL"]
        assert "portfolio_metrics" in data
        assert "per_asset" in data

    @patch("fina.orchestration.backtest.run_portfolio_backtest")
    def test_custom_weights(self, mock_pbt, client):
        mock_pbt.return_value = _MOCK_PORTFOLIO_RESULT
        resp = client.post("/backtest/portfolio/", json={
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "train_start": "2022-01-01",
            "train_end": "2023-06-30",
            "test_start": "2023-07-01",
            "test_end": "2023-12-31",
            "weight_scheme": "custom",
            "custom_weights": [0.5, 0.3, 0.2],
        })
        assert resp.status_code == 200

    def test_single_ticker_rejected(self, client):
        resp = client.post("/backtest/portfolio/", json={
            "tickers": ["AAPL"],
            "train_start": "2022-01-01",
            "train_end": "2023-06-30",
            "test_start": "2023-07-01",
            "test_end": "2023-12-31",
        })
        # BacktestError from engine: "at least 2 tickers"
        assert resp.status_code == 422

    def test_invalid_weight_scheme_rejected(self, client):
        resp = client.post("/backtest/portfolio/", json={
            "tickers": ["AAPL", "MSFT"],
            "train_start": "2022-01-01",
            "train_end": "2023-06-30",
            "test_start": "2023-07-01",
            "test_end": "2023-12-31",
            "weight_scheme": "magic",
        })
        assert resp.status_code == 422

    def test_custom_weights_length_mismatch_rejected(self, client):
        resp = client.post("/backtest/portfolio/", json={
            "tickers": ["AAPL", "MSFT"],
            "train_start": "2022-01-01",
            "train_end": "2023-06-30",
            "test_start": "2023-07-01",
            "test_end": "2023-12-31",
            "weight_scheme": "custom",
            "custom_weights": [0.5],
        })
        assert resp.status_code == 422

    def test_invalid_date_rejected(self, client):
        resp = client.post("/backtest/portfolio/", json={
            "tickers": ["AAPL", "MSFT"],
            "train_start": "not-a-date",
            "train_end": "2023-06-30",
            "test_start": "2023-07-01",
            "test_end": "2023-12-31",
        })
        assert resp.status_code == 422

    def test_invalid_cross_signal_rejected(self, client):
        resp = client.post("/backtest/portfolio/", json={
            "tickers": ["AAPL", "MSFT"],
            "train_start": "2022-01-01",
            "train_end": "2023-06-30",
            "test_start": "2023-07-01",
            "test_end": "2023-12-31",
            "cross_signal": "invalid",
        })
        assert resp.status_code == 422

    def test_pairs_requires_exactly_2_tickers(self, client):
        resp = client.post("/backtest/portfolio/", json={
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "train_start": "2022-01-01",
            "train_end": "2023-06-30",
            "test_start": "2023-07-01",
            "test_end": "2023-12-31",
            "cross_signal": "pairs",
        })
        assert resp.status_code == 422

    @patch("fina.orchestration.backtest.run_portfolio_backtest")
    def test_with_cross_signal(self, mock_pbt, client):
        result_with_cross = {**_MOCK_PORTFOLIO_RESULT, "cross_signal": {"type": "momentum"}}
        mock_pbt.return_value = result_with_cross
        resp = client.post("/backtest/portfolio/", json={
            "tickers": ["AAPL", "MSFT", "GOOGL"],
            "train_start": "2022-01-01",
            "train_end": "2023-06-30",
            "test_start": "2023-07-01",
            "test_end": "2023-12-31",
            "cross_signal": "momentum",
        })
        assert resp.status_code == 200
        assert resp.json()["cross_signal"]["type"] == "momentum"

    @patch("fina.orchestration.backtest.run_portfolio_backtest")
    def test_backtest_error_returns_422(self, mock_pbt, client):
        mock_pbt.side_effect = BacktestError("boom")
        resp = client.post("/backtest/portfolio/", json={
            "tickers": ["AAPL", "MSFT"],
            "train_start": "2022-01-01",
            "train_end": "2023-06-30",
            "test_start": "2023-07-01",
            "test_end": "2023-12-31",
        })
        assert resp.status_code == 422
        assert "boom" in resp.json()["detail"]

    @patch("fina.orchestration.backtest.run_portfolio_backtest")
    def test_fetcher_error_returns_422(self, mock_pbt, client):
        mock_pbt.side_effect = FetcherError("no data")
        resp = client.post("/backtest/portfolio/", json={
            "tickers": ["AAPL", "MSFT"],
            "train_start": "2022-01-01",
            "train_end": "2023-06-30",
            "test_start": "2023-07-01",
            "test_end": "2023-12-31",
        })
        assert resp.status_code == 422
