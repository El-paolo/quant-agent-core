"""
Unit tests for fina.backtest.cross_signals — momentum rank and pairs signals.

Uses synthetic data for deterministic, fast tests.
"""

import numpy as np
import pandas as pd
import pytest

from fina.backtest.cross_signals import momentum_rank_signal, pairs_signal
from fina.core.exceptions import BacktestError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_returns(n: int = 300, n_tickers: int = 4, seed: int = 42) -> pd.DataFrame:
    """Generate a multi-ticker returns DataFrame with distinct drift per ticker."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-03", periods=n, freq="B")
    data = {}
    for i in range(n_tickers):
        drift = 0.001 * (i - n_tickers // 2)  # spread drifts around zero
        data[f"T{i}"] = rng.normal(drift, 0.015, n)
    return pd.DataFrame(data, index=dates)


def _make_cointegrated_prices(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate two cointegrated price series."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-03", periods=n, freq="B")
    # Common stochastic trend
    trend = np.cumsum(rng.normal(0.0005, 0.01, n))
    noise_a = rng.normal(0, 0.5, n)
    noise_b = rng.normal(0, 0.5, n)
    prices_a = 100 + trend + noise_a
    prices_b = 50 + 0.5 * trend + noise_b  # cointegrated with A
    return pd.DataFrame({"A": prices_a, "B": prices_b}, index=dates)


def _make_noncointegrated_prices(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """Generate two independent (non-cointegrated) price series."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2022-01-03", periods=n, freq="B")
    prices_a = 100 + np.cumsum(rng.normal(0.001, 0.02, n))
    prices_b = 100 + np.cumsum(rng.normal(-0.001, 0.03, n))
    return pd.DataFrame({"X": prices_a, "Y": prices_b}, index=dates)


# ---------------------------------------------------------------------------
# Momentum rank signal
# ---------------------------------------------------------------------------


class TestMomentumRankSignal:
    def test_output_shape(self) -> None:
        df = _make_returns(n=300, n_tickers=4)
        result = momentum_rank_signal(df, lookback=252, skip=21)
        assert result.shape == df.shape
        assert list(result.columns) == list(df.columns)

    def test_signals_are_valid_values(self) -> None:
        df = _make_returns(n=300, n_tickers=4)
        result = momentum_rank_signal(df, lookback=252, skip=21)
        unique_vals = set(result.values.flatten())
        assert unique_vals <= {-1.0, 0.0, 1.0}

    def test_pre_lookback_rows_are_zero(self) -> None:
        df = _make_returns(n=300, n_tickers=4)
        result = momentum_rank_signal(df, lookback=252, skip=21)
        # All rows before lookback should be zero
        assert (result.iloc[:252] == 0).all().all()

    def test_top_n_defaults_to_third(self) -> None:
        df = _make_returns(n=300, n_tickers=6)
        result = momentum_rank_signal(df, lookback=252, skip=21)
        # top_n = 6 // 3 = 2, so 2 longs and 2 shorts per row after lookback
        active = result.iloc[252:]
        long_counts = (active == 1.0).sum(axis=1)
        short_counts = (active == -1.0).sum(axis=1)
        assert (long_counts == 2).all()
        assert (short_counts == 2).all()

    def test_custom_top_n(self) -> None:
        df = _make_returns(n=300, n_tickers=4)
        result = momentum_rank_signal(df, lookback=252, skip=21, top_n=1)
        active = result.iloc[252:]
        long_counts = (active == 1.0).sum(axis=1)
        short_counts = (active == -1.0).sum(axis=1)
        assert (long_counts == 1).all()
        assert (short_counts == 1).all()

    def test_empty_df_raises(self) -> None:
        with pytest.raises(BacktestError, match="empty"):
            momentum_rank_signal(pd.DataFrame())

    def test_single_ticker_raises(self) -> None:
        df = _make_returns(n=300, n_tickers=1)
        with pytest.raises(BacktestError, match="at least 2"):
            momentum_rank_signal(df)

    def test_insufficient_rows_raises(self) -> None:
        df = _make_returns(n=100, n_tickers=4)
        with pytest.raises(BacktestError, match="Need at least"):
            momentum_rank_signal(df, lookback=252)

    def test_lookback_lte_skip_raises(self) -> None:
        df = _make_returns(n=300, n_tickers=4)
        with pytest.raises(BacktestError, match="lookback"):
            momentum_rank_signal(df, lookback=20, skip=21)


# ---------------------------------------------------------------------------
# Pairs signal
# ---------------------------------------------------------------------------


class TestPairsSignal:
    def test_cointegrated_pair_produces_signals(self) -> None:
        df = _make_cointegrated_prices(n=200)
        result = pairs_signal(df, pair=("A", "B"), lookback=60)
        assert len(result) == len(df)
        unique_vals = set(result.values)
        assert unique_vals <= {-1.0, 0.0, 1.0}

    def test_pre_lookback_is_zero(self) -> None:
        df = _make_cointegrated_prices(n=200)
        result = pairs_signal(df, pair=("A", "B"), lookback=60)
        assert (result.iloc[:60] == 0).all()

    def test_noncointegrated_pair_raises(self) -> None:
        df = _make_noncointegrated_prices(n=200)
        with pytest.raises(BacktestError, match="not cointegrated"):
            pairs_signal(df, pair=("X", "Y"), lookback=60)

    def test_missing_ticker_raises(self) -> None:
        df = _make_cointegrated_prices(n=200)
        with pytest.raises(BacktestError, match="not found"):
            pairs_signal(df, pair=("A", "MISSING"), lookback=60)

    def test_insufficient_data_raises(self) -> None:
        df = _make_cointegrated_prices(n=50)
        with pytest.raises(BacktestError, match="Need at least"):
            pairs_signal(df, pair=("A", "B"), lookback=60)

    def test_custom_z_thresholds(self) -> None:
        df = _make_cointegrated_prices(n=200)
        result = pairs_signal(
            df, pair=("A", "B"), lookback=60,
            entry_z=1.5, exit_z=0.3, stop_z=4.0,
        )
        assert len(result) == len(df)
        unique_vals = set(result.values)
        assert unique_vals <= {-1.0, 0.0, 1.0}
