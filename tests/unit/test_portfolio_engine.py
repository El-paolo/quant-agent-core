"""
Unit tests for fina.backtest.portfolio_engine.

All data fetching and model fitting is mocked — no real network
or heavy computation.
"""

from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from fina.backtest.portfolio_engine import run_portfolio_backtest
from fina.core.exceptions import BacktestError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_prices(n: int = 500, seed: int = 42, start_price: float = 100.0) -> pd.Series:
    """Generate a deterministic price series."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-03", periods=n, freq="B")
    return pd.Series(
        start_price * np.exp(np.cumsum(rng.normal(0.0005, 0.015, n))),
        index=dates,
    )


def _make_universe_df(tickers: list[str]) -> pd.DataFrame:
    """Build a mock multi-ticker DataFrame."""
    dfs = {}
    for i, t in enumerate(tickers):
        dfs[t] = _make_prices(seed=42 + i, start_price=100 + i * 50)
    df = pd.DataFrame(dfs)
    df.attrs["warnings"] = []
    df.attrs["failed_tickers"] = []
    return df


def _mock_pipeline_result(test_prices: pd.Series, initial_capital: float = 10_000.0) -> dict:
    """Build a mock result from _run_single_ticker_pipeline."""
    n = len(test_prices)
    # Simple equity: just scales with prices
    equity = pd.Series(
        initial_capital * test_prices.values / test_prices.values[0],
        index=test_prices.index,
    )
    benchmark = equity.copy()
    daily_returns = equity.pct_change().fillna(0.0)
    benchmark_returns = daily_returns.copy()
    positions = pd.Series(1.0, index=test_prices.index)

    trades = [
        {"pnl_pct": 0.02, "duration_days": 5},
        {"pnl_pct": -0.01, "duration_days": 3},
    ]

    return {
        "signal_summaries": {"arima": {"order": [1, 0, 0]}},
        "simulation": {
            "equity_curve": equity,
            "daily_returns": daily_returns,
            "benchmark_equity": benchmark,
            "benchmark_returns": benchmark_returns,
            "positions": positions,
            "trades": trades,
        },
        "metrics": {
            "strategy": {"sharpe_ratio": 1.0, "total_return": 0.1},
            "benchmark": {"sharpe_ratio": 0.8},
            "relative": {"excess_return": 0.02},
        },
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPortfolioEngine:
    def test_requires_at_least_2_tickers(self) -> None:
        with pytest.raises(BacktestError, match="at least 2"):
            run_portfolio_backtest(
                tickers=["AAPL"],
                train_start="2022-01-01", train_end="2023-06-30",
                test_start="2023-07-01", test_end="2023-12-31",
            )

    def test_invalid_weight_scheme_raises(self) -> None:
        with pytest.raises(BacktestError, match="weight scheme"):
            run_portfolio_backtest(
                tickers=["AAPL", "MSFT"],
                train_start="2022-01-01", train_end="2023-06-30",
                test_start="2023-07-01", test_end="2023-12-31",
                weight_scheme="magic",
            )

    def test_custom_weights_length_mismatch_raises(self) -> None:
        with pytest.raises(BacktestError, match="length"):
            run_portfolio_backtest(
                tickers=["AAPL", "MSFT"],
                train_start="2022-01-01", train_end="2023-06-30",
                test_start="2023-07-01", test_end="2023-12-31",
                weight_scheme="custom",
                custom_weights=[0.5],  # wrong length
            )

    def test_date_validation(self) -> None:
        with pytest.raises(BacktestError, match="before"):
            run_portfolio_backtest(
                tickers=["AAPL", "MSFT"],
                train_start="2023-07-01", train_end="2023-06-30",
                test_start="2023-07-01", test_end="2023-12-31",
            )

    @patch("fina.backtest.portfolio_engine._run_single_ticker_pipeline")
    @patch("fina.backtest.portfolio_engine.fetch_universe")
    def test_equal_weight_happy_path(self, mock_fetch, mock_pipeline) -> None:
        tickers = ["AAPL", "MSFT", "GOOGL"]
        universe_df = _make_universe_df(tickers)
        mock_fetch.return_value = universe_df

        def pipeline_side_effect(test_prices, **kwargs):
            return _mock_pipeline_result(test_prices)

        mock_pipeline.side_effect = lambda **kw: _mock_pipeline_result(
            kw["test_prices"], kw.get("initial_capital", 10_000.0)
        )

        result = run_portfolio_backtest(
            tickers=tickers,
            train_start="2022-01-01", train_end="2023-06-30",
            test_start="2023-07-01", test_end="2023-12-31",
            models=["arima"],
        )

        assert set(result["tickers"]) == set(tickers)
        assert abs(sum(result["weights"].values()) - 1.0) < 1e-4
        assert "portfolio_metrics" in result
        assert "var_95" in result["portfolio_metrics"]
        assert "cvar_95" in result["portfolio_metrics"]
        assert "dsr" in result["portfolio_metrics"]
        assert "effective_n" in result["portfolio_metrics"]
        assert len(result["portfolio_equity_curve"]) > 0

    @patch("fina.backtest.portfolio_engine._run_single_ticker_pipeline")
    @patch("fina.backtest.portfolio_engine.fetch_universe")
    def test_per_asset_results_included(self, mock_fetch, mock_pipeline) -> None:
        tickers = ["AAPL", "MSFT"]
        mock_fetch.return_value = _make_universe_df(tickers)
        mock_pipeline.side_effect = lambda **kw: _mock_pipeline_result(
            kw["test_prices"]
        )

        result = run_portfolio_backtest(
            tickers=tickers,
            train_start="2022-01-01", train_end="2023-06-30",
            test_start="2023-07-01", test_end="2023-12-31",
        )

        assert "per_asset" in result
        for t in tickers:
            assert t in result["per_asset"]
            assert "metrics" in result["per_asset"][t]

    @patch("fina.backtest.portfolio_engine._run_single_ticker_pipeline")
    @patch("fina.backtest.portfolio_engine.fetch_universe")
    def test_partial_failure_renormalizes_weights(self, mock_fetch, mock_pipeline) -> None:
        tickers = ["AAPL", "MSFT", "BAD"]
        mock_fetch.return_value = _make_universe_df(tickers)

        call_count = {"n": 0}

        def side_effect(**kw):
            call_count["n"] += 1
            if call_count["n"] == 3:  # third ticker fails
                raise BacktestError("model failure")
            return _mock_pipeline_result(kw["test_prices"])

        mock_pipeline.side_effect = side_effect

        result = run_portfolio_backtest(
            tickers=tickers,
            train_start="2022-01-01", train_end="2023-06-30",
            test_start="2023-07-01", test_end="2023-12-31",
        )

        # Should still succeed with 2 tickers
        assert len(result["tickers"]) == 2
        assert abs(sum(result["weights"].values()) - 1.0) < 1e-4
