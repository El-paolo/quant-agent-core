"""
Unit tests for fina.backtest.signals

Covers: ARIMA signal generation, HMM signal generation, GARCH sizing,
signal combination logic.
"""

import numpy as np
import pandas as pd
import pytest

from fina.core.exceptions import BacktestError


# ── Fixtures ──

@pytest.fixture
def train_returns() -> pd.Series:
    """300 deterministic log-return observations with regime structure for HMM."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2022-01-01", periods=300, freq="B")
    # Simulate 3 regimes: low vol, mid vol, high vol blocks
    low = rng.normal(0.001, 0.008, 100)
    mid = rng.normal(0.0, 0.015, 100)
    high = rng.normal(-0.001, 0.030, 100)
    returns = np.concatenate([low, mid, high])
    return pd.Series(returns, index=dates, name="returns")


@pytest.fixture
def test_returns() -> pd.Series:
    """60 deterministic log-return observations for testing."""
    rng = np.random.default_rng(99)
    dates = pd.date_range("2023-04-01", periods=60, freq="B")
    return pd.Series(rng.normal(0.0003, 0.018, 60), index=dates, name="returns")


@pytest.fixture
def short_returns() -> pd.Series:
    """Too-short series for triggering minimum obs errors."""
    dates = pd.date_range("2022-01-01", periods=20, freq="B")
    return pd.Series(np.random.default_rng(1).normal(0, 0.01, 20), index=dates)


# ── ARIMA Signals ──

class TestArimaSignals:
    def test_returns_expected_keys(self, train_returns, test_returns):
        from fina.backtest.signals import generate_arima_signals
        result = generate_arima_signals(train_returns, test_returns)
        assert "signals" in result
        assert "predictions" in result
        assert "order" in result
        assert "warnings" in result

    def test_signals_are_int_series(self, train_returns, test_returns):
        from fina.backtest.signals import generate_arima_signals
        result = generate_arima_signals(train_returns, test_returns)
        sig = result["signals"]
        assert isinstance(sig, pd.Series)
        assert len(sig) == len(test_returns)
        assert set(sig.unique()).issubset({-1, 0, 1})

    def test_predictions_aligned_with_test(self, train_returns, test_returns):
        from fina.backtest.signals import generate_arima_signals
        result = generate_arima_signals(train_returns, test_returns)
        assert list(result["predictions"].index) == list(test_returns.index)

    def test_insufficient_train_raises(self, short_returns, test_returns):
        from fina.backtest.signals import generate_arima_signals
        with pytest.raises(BacktestError, match="train obs"):
            generate_arima_signals(short_returns, test_returns)

    def test_empty_test_raises(self, train_returns):
        from fina.backtest.signals import generate_arima_signals
        empty = pd.Series([], dtype=float)
        with pytest.raises(BacktestError, match="empty"):
            generate_arima_signals(train_returns, empty)

    def test_threshold_filters_weak_signals(self, train_returns, test_returns):
        from fina.backtest.signals import generate_arima_signals
        result = generate_arima_signals(train_returns, test_returns, threshold=0.1)
        # With a very high threshold, most signals should be 0 (hold)
        assert (result["signals"] == 0).sum() >= len(test_returns) * 0.5


# ── HMM Signals ──

class TestHmmSignals:
    def test_returns_expected_keys(self, train_returns, test_returns):
        from fina.backtest.signals import generate_hmm_signals
        result = generate_hmm_signals(train_returns, test_returns)
        assert "signals" in result
        assert "regimes" in result
        assert "warnings" in result

    def test_signals_in_valid_range(self, train_returns, test_returns):
        from fina.backtest.signals import generate_hmm_signals
        result = generate_hmm_signals(train_returns, test_returns)
        assert set(result["signals"].unique()).issubset({-1, 0, 1})

    def test_regimes_are_labeled(self, train_returns, test_returns):
        from fina.backtest.signals import generate_hmm_signals
        result = generate_hmm_signals(train_returns, test_returns)
        valid_labels = {"low_vol", "mid_vol", "high_vol"}
        assert set(result["regimes"].unique()).issubset(valid_labels)

    def test_two_state_hmm(self, train_returns, test_returns):
        from fina.backtest.signals import generate_hmm_signals
        result = generate_hmm_signals(train_returns, test_returns, n_states=2)
        assert set(result["signals"].unique()).issubset({-1, 1})

    def test_insufficient_train_raises(self, short_returns, test_returns):
        from fina.backtest.signals import generate_hmm_signals
        with pytest.raises(BacktestError, match="train obs"):
            generate_hmm_signals(short_returns, test_returns)


# ── GARCH Sizing ──

class TestGarchSizing:
    def test_returns_expected_keys(self, train_returns, test_returns):
        from fina.backtest.signals import generate_garch_sizing
        result = generate_garch_sizing(train_returns, test_returns)
        assert "sizing" in result
        assert "cond_vol" in result
        assert "target_vol" in result
        assert "warnings" in result

    def test_sizing_within_bounds(self, train_returns, test_returns):
        from fina.backtest.signals import generate_garch_sizing
        result = generate_garch_sizing(train_returns, test_returns)
        sizing = result["sizing"]
        assert sizing.min() >= 0.5
        assert sizing.max() <= 2.0

    def test_custom_target_vol(self, train_returns, test_returns):
        from fina.backtest.signals import generate_garch_sizing
        result = generate_garch_sizing(train_returns, test_returns, target_vol=0.02)
        assert result["target_vol"] == 0.02

    def test_insufficient_train_raises(self, short_returns, test_returns):
        from fina.backtest.signals import generate_garch_sizing
        with pytest.raises(BacktestError, match="train obs"):
            generate_garch_sizing(short_returns, test_returns)


# ── Combine Signals ──

class TestCombineSignals:
    def test_arima_only(self, test_returns):
        from fina.backtest.signals import combine_signals
        arima = pd.Series([1, -1, 0, 1, 0], index=test_returns.index[:5], dtype=int)
        result = combine_signals(arima_signals=arima)
        # ARIMA signals with no HMM: ARIMA non-zero values used, zeros stay zero
        assert result.iloc[0] == 1.0
        assert result.iloc[1] == -1.0
        assert result.iloc[2] == 0.0  # ARIMA 0, no HMM base → stays 0
        assert result.iloc[3] == 1.0
        assert result.iloc[4] == 0.0

    def test_hmm_base_direction(self, test_returns):
        """HMM provides base direction; ARIMA overrides when non-zero."""
        from fina.backtest.signals import combine_signals
        idx = test_returns.index[:5]
        hmm = pd.Series([1, 1, 0, 1, -1], index=idx, dtype=int)
        result = combine_signals(hmm_signals=hmm)
        # HMM high_vol (-1) is filtered to 0
        assert result.iloc[4] == 0.0
        # HMM low_vol (+1) stays
        assert result.iloc[0] == 1.0

    def test_arima_overrides_hmm_when_nonzero(self, test_returns):
        """ARIMA non-zero opinion overrides HMM direction."""
        from fina.backtest.signals import combine_signals
        idx = test_returns.index[:5]
        # HMM says long all days, ARIMA says short on day 1, flat on day 2
        hmm = pd.Series([1, 1, 1, 1, 1], index=idx, dtype=int)
        arima = pd.Series([-1, 0, 1, 0, -1], index=idx, dtype=int)
        result = combine_signals(arima_signals=arima, hmm_signals=hmm)
        assert result.iloc[0] == -1.0   # ARIMA overrides HMM
        assert result.iloc[1] == 1.0    # ARIMA flat → HMM direction
        assert result.iloc[2] == 1.0    # ARIMA +1 agrees with HMM
        assert result.iloc[3] == 1.0    # ARIMA flat → HMM direction

    def test_hmm_risk_off_overrides_arima(self, test_returns):
        """HMM -1 (high_vol) always overrides ARIMA to hold."""
        from fina.backtest.signals import combine_signals
        idx = test_returns.index[:5]
        arima = pd.Series([1, 1, 1, 1, 1], index=idx, dtype=int)
        hmm = pd.Series([1, -1, 0, -1, 1], index=idx, dtype=int)
        result = combine_signals(arima_signals=arima, hmm_signals=hmm)
        assert result.iloc[1] == 0.0   # HMM -1 overrides ARIMA +1
        assert result.iloc[3] == 0.0   # HMM -1 overrides ARIMA +1
        assert result.iloc[0] == 1.0   # HMM non-negative, ARIMA wins

    def test_garch_scales_position(self, test_returns):
        from fina.backtest.signals import combine_signals
        idx = test_returns.index[:3]
        arima = pd.Series([1, -1, 1], index=idx, dtype=int)
        garch = pd.Series([1.5, 0.8, 2.0], index=idx)
        result = combine_signals(arima_signals=arima, garch_sizing=garch)
        assert abs(result.iloc[0] - 1.5) < 0.01
        assert abs(result.iloc[1] - (-0.8)) < 0.01

    def test_no_signals_raises(self):
        from fina.backtest.signals import combine_signals
        with pytest.raises(BacktestError, match="At least one"):
            combine_signals()

    def test_arima_000_none_falls_back_to_hmm(self, test_returns):
        """When ARIMA signals are None (0,0,0), HMM provides direction."""
        from fina.backtest.signals import combine_signals
        idx = test_returns.index[:3]
        hmm = pd.Series([1, 0, 1], index=idx, dtype=int)
        # Pass None for arima_signals simulating ARIMA(0,0,0) case
        result = combine_signals(arima_signals=None, hmm_signals=hmm)
        assert result.iloc[0] == 1.0
        assert result.iloc[1] == 0.0
        assert result.iloc[2] == 1.0
