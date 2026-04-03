"""
Unit tests for fina.backtest.engine

Covers: date validation, data pipeline, full backtest integration
with mocked fetcher.
"""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from fina.backtest.engine import run_backtest
from fina.core.exceptions import BacktestError


@pytest.fixture
def mock_prices():
    """500-day deterministic price series spanning 2022-2024."""
    dates = pd.date_range("2022-01-03", periods=500, freq="B")
    rng = np.random.default_rng(42)
    prices = pd.Series(
        100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, 500))),
        index=dates, name="AAPL", dtype=float,
    )
    return prices


class TestDateValidation:
    def test_overlapping_dates_raises(self):
        with pytest.raises(BacktestError, match="before test start"):
            run_backtest("AAPL", "2023-01-01", "2024-06-30", "2024-01-01", "2024-12-31")

    def test_inverted_train_dates_raises(self):
        with pytest.raises(BacktestError, match="Train start"):
            run_backtest("AAPL", "2023-12-31", "2023-01-01", "2024-01-01", "2024-06-30")

    def test_inverted_test_dates_raises(self):
        with pytest.raises(BacktestError, match="Test start"):
            run_backtest("AAPL", "2022-01-01", "2023-12-31", "2024-06-30", "2024-01-01")

    def test_invalid_date_format_raises(self):
        with pytest.raises(BacktestError, match="Invalid date"):
            run_backtest("AAPL", "01-01-2022", "2023-12-31", "2024-01-01", "2024-06-30")

    def test_unknown_model_raises(self):
        with pytest.raises(BacktestError, match="Unknown models"):
            run_backtest(
                "AAPL", "2022-01-01", "2023-12-31",
                "2024-01-01", "2024-06-30", models=["lstm"],
            )


class TestFullPipeline:
    @patch("fina.backtest.engine.fetch_close_prices")
    def test_returns_expected_keys(self, mock_fetch, mock_prices):
        mock_fetch.return_value = mock_prices
        result = run_backtest(
            "AAPL", "2022-01-03", "2023-06-30",
            "2023-07-03", "2023-12-29",
            models=["arima"],
        )
        assert "ticker" in result
        assert "train_period" in result
        assert "test_period" in result
        assert "models_used" in result
        assert "signals" in result
        assert "metrics" in result
        assert "equity_curve" in result
        assert "benchmark_curve" in result
        assert "positions" in result
        assert "trades" in result
        assert "warnings" in result

    @patch("fina.backtest.engine.fetch_close_prices")
    def test_equity_curve_is_list_of_dicts(self, mock_fetch, mock_prices):
        mock_fetch.return_value = mock_prices
        result = run_backtest(
            "AAPL", "2022-01-03", "2023-06-30",
            "2023-07-03", "2023-12-29",
            models=["arima"],
        )
        assert len(result["equity_curve"]) > 0
        assert "date" in result["equity_curve"][0]
        assert "value" in result["equity_curve"][0]

    @patch("fina.backtest.engine.fetch_close_prices")
    def test_metrics_has_strategy_and_benchmark(self, mock_fetch, mock_prices):
        mock_fetch.return_value = mock_prices
        result = run_backtest(
            "AAPL", "2022-01-03", "2023-06-30",
            "2023-07-03", "2023-12-29",
            models=["arima"],
        )
        assert "strategy" in result["metrics"]
        assert "benchmark" in result["metrics"]
        assert "relative" in result["metrics"]

    @patch("fina.backtest.engine.fetch_close_prices")
    def test_insufficient_data_raises(self, mock_fetch):
        dates = pd.date_range("2022-01-03", periods=5, freq="B")
        mock_fetch.return_value = pd.Series([100, 101, 102, 103, 104],
                                            index=dates, dtype=float)
        with pytest.raises(BacktestError, match="Insufficient|too short"):
            run_backtest(
                "AAPL", "2022-01-03", "2022-01-05",
                "2022-01-06", "2022-01-07",
            )

    @patch("fina.backtest.engine.fetch_close_prices")
    def test_single_model_arima(self, mock_fetch, mock_prices):
        mock_fetch.return_value = mock_prices
        result = run_backtest(
            "AAPL", "2022-01-03", "2023-06-30",
            "2023-07-03", "2023-12-29",
            models=["arima"],
        )
        assert result["models_used"] == ["arima"]
        assert "arima" in result["signals"]

    @patch("fina.backtest.engine.fetch_close_prices")
    def test_actual_dates_reported(self, mock_fetch, mock_prices):
        mock_fetch.return_value = mock_prices
        result = run_backtest(
            "AAPL", "2022-01-01", "2023-06-30",
            "2023-07-01", "2023-12-31",
            models=["arima"],
        )
        # Actual dates should be trading days, not necessarily the requested ones
        assert result["train_period"]["trading_days"] > 0
        assert result["test_period"]["trading_days"] > 0
