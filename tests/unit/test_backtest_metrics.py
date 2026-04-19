"""
Unit tests for fina.backtest.metrics

Covers: Sharpe, Sortino, max drawdown, Calmar, win rate, benchmark
comparison, relative metrics, edge cases.
"""

import numpy as np
import pandas as pd
import pytest

from fina.backtest.metrics import compute_backtest_metrics


@pytest.fixture
def sample_backtest():
    """Pre-computed backtest data for metrics testing."""
    dates = pd.date_range("2024-01-01", periods=100, freq="B")
    rng = np.random.default_rng(42)

    # Strategy: slight positive drift
    strat_returns = pd.Series(rng.normal(0.001, 0.015, 100), index=dates)
    strat_equity = 10_000 * (1 + strat_returns).cumprod()

    # Benchmark: slightly less drift
    bench_returns = pd.Series(rng.normal(0.0008, 0.012, 100), index=dates)
    bench_equity = 10_000 * (1 + bench_returns).cumprod()

    trades = [
        {"entry_date": "2024-01-01", "exit_date": "2024-02-01", "direction": "long", "pnl_pct": 0.03, "duration_days": 22},
        {"entry_date": "2024-02-05", "exit_date": "2024-03-01", "direction": "short", "pnl_pct": -0.01, "duration_days": 18},
        {"entry_date": "2024-03-04", "exit_date": "2024-04-01", "direction": "long", "pnl_pct": 0.02, "duration_days": 20},
    ]

    return {
        "equity_curve": strat_equity,
        "daily_returns": strat_returns,
        "trades": trades,
        "benchmark_equity": bench_equity,
        "benchmark_returns": bench_returns,
    }


class TestComputeBacktestMetrics:
    def test_returns_all_sections(self, sample_backtest):
        result = compute_backtest_metrics(**sample_backtest)
        assert "strategy" in result
        assert "benchmark" in result
        assert "relative" in result

    def test_strategy_keys(self, sample_backtest):
        result = compute_backtest_metrics(**sample_backtest)
        strat = result["strategy"]
        expected_keys = {
            "total_return", "annualized_return", "volatility",
            "sharpe_ratio", "sortino_ratio", "max_drawdown",
            "max_drawdown_duration_days", "calmar_ratio",
            "win_rate", "avg_trade_return", "avg_trade_duration_days",
            "total_trades", "profit_factor", "avg_win_loss_ratio",
            "kelly_fraction",
        }
        assert expected_keys == set(strat.keys())

    def test_benchmark_keys(self, sample_backtest):
        result = compute_backtest_metrics(**sample_backtest)
        assert "total_return" in result["benchmark"]
        assert "sharpe_ratio" in result["benchmark"]
        assert "max_drawdown" in result["benchmark"]

    def test_total_return_positive(self, sample_backtest):
        result = compute_backtest_metrics(**sample_backtest)
        # With positive drift seed, total return should be positive
        assert result["strategy"]["total_return"] > 0

    def test_max_drawdown_is_negative(self, sample_backtest):
        result = compute_backtest_metrics(**sample_backtest)
        assert result["strategy"]["max_drawdown"] <= 0

    def test_win_rate_correct(self, sample_backtest):
        result = compute_backtest_metrics(**sample_backtest)
        # 2 out of 3 trades are winners
        assert abs(result["strategy"]["win_rate"] - 2 / 3) < 0.01

    def test_total_trades_count(self, sample_backtest):
        result = compute_backtest_metrics(**sample_backtest)
        assert result["strategy"]["total_trades"] == 3

    def test_no_trades_handled(self, sample_backtest):
        sample_backtest["trades"] = []
        result = compute_backtest_metrics(**sample_backtest)
        assert result["strategy"]["win_rate"] == 0
        assert result["strategy"]["total_trades"] == 0

    def test_flat_equity_zero_sharpe(self):
        dates = pd.date_range("2024-01-01", periods=50, freq="B")
        flat_returns = pd.Series(0.0, index=dates)
        flat_equity = pd.Series(10_000.0, index=dates)
        result = compute_backtest_metrics(
            equity_curve=flat_equity,
            daily_returns=flat_returns,
            trades=[],
            benchmark_equity=flat_equity.copy(),
            benchmark_returns=flat_returns.copy(),
        )
        assert result["strategy"]["sharpe_ratio"] == 0
        assert result["strategy"]["max_drawdown"] == 0

    def test_excess_return_sign(self, sample_backtest):
        result = compute_backtest_metrics(**sample_backtest)
        expected = result["strategy"]["total_return"] - result["benchmark"]["total_return"]
        assert abs(result["relative"]["excess_return"] - expected) < 0.001
