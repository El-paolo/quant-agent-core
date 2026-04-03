"""
Unit tests for POST /backtest/ route.

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


_MOCK_RESULT = {
    "ticker": "AAPL",
    "train_period": {"start": "2022-01-03", "end": "2023-12-29", "trading_days": 500},
    "test_period": {"start": "2024-01-02", "end": "2024-06-28", "trading_days": 125},
    "models_used": ["arima", "hmm", "garch"],
    "signals": {
        "arima": {"order": [1, 0, 1], "long_days": 60, "short_days": 30, "hold_days": 35},
    },
    "metrics": {
        "strategy": {"total_return": 0.05, "sharpe_ratio": 1.2, "max_drawdown": -0.08},
        "benchmark": {"total_return": 0.10, "sharpe_ratio": 0.9, "max_drawdown": -0.12},
        "relative": {"excess_return": -0.05, "information_ratio": -0.3},
    },
    "equity_curve": [{"date": "2024-01-02", "value": 10000}],
    "benchmark_curve": [{"date": "2024-01-02", "value": 10000}],
    "positions": [{"date": "2024-01-02", "value": 1.0}],
    "trades": [
        {"entry_date": "2024-01-02", "exit_date": "2024-02-01", "direction": "long", "pnl_pct": 0.03, "duration_days": 22},
    ],
    "warnings": [],
}


class TestBacktestRoute:
    @patch("fina.orchestration.backtest.run_backtest")
    def test_happy_path(self, mock_bt, client):
        mock_bt.return_value = _MOCK_RESULT
        resp = client.post("/backtest/", json={
            "ticker": "AAPL",
            "train_start": "2022-01-01",
            "train_end": "2023-12-31",
            "test_start": "2024-01-01",
            "test_end": "2024-06-30",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["ticker"] == "AAPL"
        assert "metrics" in data
        assert "equity_curve" in data

    @patch("fina.orchestration.backtest.run_backtest")
    def test_custom_models(self, mock_bt, client):
        mock_bt.return_value = _MOCK_RESULT
        resp = client.post("/backtest/", json={
            "ticker": "AAPL",
            "train_start": "2022-01-01",
            "train_end": "2023-12-31",
            "test_start": "2024-01-01",
            "test_end": "2024-06-30",
            "models": ["arima"],
        })
        assert resp.status_code == 200

    def test_invalid_ticker(self, client):
        resp = client.post("/backtest/", json={
            "ticker": "!!!",
            "train_start": "2022-01-01",
            "train_end": "2023-12-31",
            "test_start": "2024-01-01",
            "test_end": "2024-06-30",
        })
        assert resp.status_code == 422

    def test_invalid_date_format(self, client):
        resp = client.post("/backtest/", json={
            "ticker": "AAPL",
            "train_start": "01-01-2022",
            "train_end": "2023-12-31",
            "test_start": "2024-01-01",
            "test_end": "2024-06-30",
        })
        assert resp.status_code == 422

    def test_invalid_model_name(self, client):
        resp = client.post("/backtest/", json={
            "ticker": "AAPL",
            "train_start": "2022-01-01",
            "train_end": "2023-12-31",
            "test_start": "2024-01-01",
            "test_end": "2024-06-30",
            "models": ["lstm"],
        })
        assert resp.status_code == 422

    def test_negative_capital(self, client):
        resp = client.post("/backtest/", json={
            "ticker": "AAPL",
            "train_start": "2022-01-01",
            "train_end": "2023-12-31",
            "test_start": "2024-01-01",
            "test_end": "2024-06-30",
            "initial_capital": -1000,
        })
        assert resp.status_code == 422

    @patch("fina.orchestration.backtest.run_backtest")
    def test_fetcher_error_returns_422(self, mock_bt, client):
        mock_bt.side_effect = FetcherError("Ticker not found")
        resp = client.post("/backtest/", json={
            "ticker": "XXXX",
            "train_start": "2022-01-01",
            "train_end": "2023-12-31",
            "test_start": "2024-01-01",
            "test_end": "2024-06-30",
        })
        assert resp.status_code == 422
        assert "Ticker not found" in resp.json()["detail"]

    @patch("fina.orchestration.backtest.run_backtest")
    def test_backtest_error_returns_422(self, mock_bt, client):
        mock_bt.side_effect = BacktestError("Train end must be before test start")
        resp = client.post("/backtest/", json={
            "ticker": "AAPL",
            "train_start": "2024-01-01",
            "train_end": "2024-06-30",
            "test_start": "2023-01-01",
            "test_end": "2023-12-31",
        })
        assert resp.status_code == 422

    @patch("fina.orchestration.backtest.run_backtest")
    def test_unexpected_error_returns_500(self, mock_bt, client):
        mock_bt.side_effect = RuntimeError("Something exploded")
        resp = client.post("/backtest/", json={
            "ticker": "AAPL",
            "train_start": "2022-01-01",
            "train_end": "2023-12-31",
            "test_start": "2024-01-01",
            "test_end": "2024-06-30",
        })
        assert resp.status_code == 500
