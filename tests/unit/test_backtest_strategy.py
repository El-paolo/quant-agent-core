"""
Unit tests for fina.backtest.strategy

Covers: strategy simulation, equity curve, trade extraction, benchmark,
commission costs, edge cases.
"""

import numpy as np
import pandas as pd
import pytest

from fina.backtest.strategy import simulate_strategy
from fina.core.exceptions import BacktestError


@pytest.fixture
def test_prices() -> pd.Series:
    """10-day deterministic price series."""
    dates = pd.date_range("2024-01-01", periods=10, freq="B")
    # Prices: 100, 102, 101, 103, 105, 104, 106, 108, 107, 110
    return pd.Series(
        [100, 102, 101, 103, 105, 104, 106, 108, 107, 110],
        index=dates, dtype=float, name="price",
    )


class TestSimulateStrategy:
    def test_all_long_matches_benchmark(self, test_prices):
        positions = pd.Series(1.0, index=test_prices.index)
        result = simulate_strategy(positions, test_prices, initial_capital=10_000)
        # All-long should closely match benchmark (slight difference due to shift)
        strat_final = result["equity_curve"].iloc[-1]
        bench_final = result["benchmark_equity"].iloc[-1]
        assert abs(strat_final - bench_final) / bench_final < 0.05

    def test_all_flat_stays_at_capital(self, test_prices):
        positions = pd.Series(0.0, index=test_prices.index)
        result = simulate_strategy(positions, test_prices, initial_capital=10_000)
        # Flat position: equity should stay at initial capital
        assert abs(result["equity_curve"].iloc[-1] - 10_000) < 1.0

    def test_equity_curve_length(self, test_prices):
        positions = pd.Series(1.0, index=test_prices.index)
        result = simulate_strategy(positions, test_prices)
        assert len(result["equity_curve"]) == len(test_prices)

    def test_daily_returns_length(self, test_prices):
        positions = pd.Series(1.0, index=test_prices.index)
        result = simulate_strategy(positions, test_prices)
        assert len(result["daily_returns"]) == len(test_prices)

    def test_benchmark_equity_grows_with_price(self, test_prices):
        positions = pd.Series(0.0, index=test_prices.index)
        result = simulate_strategy(positions, test_prices, initial_capital=10_000)
        # Benchmark should end at 10_000 * (110/100) = 11_000
        assert abs(result["benchmark_equity"].iloc[-1] - 11_000) < 100

    def test_trades_extraction(self, test_prices):
        # Long for first 5 days, flat for last 5
        positions = pd.Series(
            [1, 1, 1, 1, 1, 0, 0, 0, 0, 0],
            index=test_prices.index, dtype=float,
        )
        result = simulate_strategy(positions, test_prices)
        assert len(result["trades"]) >= 1
        assert result["trades"][0]["direction"] == "long"

    def test_commission_reduces_equity(self, test_prices):
        positions = pd.Series([1, -1, 1, -1, 1, -1, 1, -1, 1, -1],
                              index=test_prices.index, dtype=float)
        no_cost = simulate_strategy(positions, test_prices, commission_bps=0)
        with_cost = simulate_strategy(positions, test_prices, commission_bps=50)
        assert with_cost["equity_curve"].iloc[-1] < no_cost["equity_curve"].iloc[-1]

    def test_empty_series_raises(self):
        with pytest.raises(BacktestError):
            simulate_strategy(
                pd.Series([], dtype=float),
                pd.Series([], dtype=float),
            )

    def test_single_point_raises(self):
        idx = pd.date_range("2024-01-01", periods=1, freq="B")
        with pytest.raises(BacktestError, match="at least 2"):
            simulate_strategy(
                pd.Series([1.0], index=idx),
                pd.Series([100.0], index=idx),
            )
