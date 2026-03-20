"""
Unit tests for fina.metrics.technical

Covers: compute_rsi, compute_macd, compute_bollinger_bands.
No external I/O — all tests use in-memory price series.
"""

import numpy as np
import pandas as pd
import pytest

from fina.core.exceptions import MetricsError
from fina.metrics.technical import (
    compute_bollinger_bands,
    compute_macd,
    compute_rsi,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prices(n: int = 100, seed: int = 0, start: float = 100.0) -> pd.Series:
    """Log-normal random walk with a fixed seed."""
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed)
    prices = pd.Series(
        start * np.exp(np.cumsum(rng.normal(0.0005, 0.01, n))),
        index=dates,
        name="TEST",
        dtype=float,
    )
    return prices


def _trending_up(n: int = 60) -> pd.Series:
    """Trending-up series (positive drift, realistic noise) — RSI should be above 50."""
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(77)
    # drift=0.003, vol=0.008 → ~65% of days positive → avg_loss > 0 → valid RSI
    prices = pd.Series(
        100.0 * np.exp(np.cumsum(rng.normal(0.003, 0.008, n))),
        index=dates,
        name="UP",
        dtype=float,
    )
    return prices


def _trending_down(n: int = 60) -> pd.Series:
    """Strictly decreasing price series — RSI should approach 0."""
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.Series(
        [100.0 - i * 0.5 for i in range(n)], index=dates, name="DOWN", dtype=float
    )


# ---------------------------------------------------------------------------
# compute_rsi
# ---------------------------------------------------------------------------


class TestComputeRSI:
    def test_returns_series(self) -> None:
        result = compute_rsi(_make_prices())
        assert isinstance(result, pd.Series)

    def test_name_contains_window(self) -> None:
        result = compute_rsi(_make_prices(), window=14)
        assert "14" in result.name

    def test_no_nans_in_output(self) -> None:
        result = compute_rsi(_make_prices())
        assert not result.isnull().any()

    def test_values_between_zero_and_hundred(self) -> None:
        result = compute_rsi(_make_prices())
        assert (result >= 0.0).all()
        assert (result <= 100.0).all()

    def test_uptrend_rsi_above_downtrend_rsi(self) -> None:
        """RSI of an uptrend series must be higher than RSI of a downtrend series."""
        up = compute_rsi(_trending_up())
        down = compute_rsi(_trending_down())
        assert up.mean() > down.mean()

    def test_downtrend_rsi_below_50(self) -> None:
        result = compute_rsi(_trending_down())
        assert result.mean() < 30.0

    def test_custom_window_changes_length(self) -> None:
        prices = _make_prices(n=60)
        r14 = compute_rsi(prices, window=14)
        r7 = compute_rsi(prices, window=7)
        # Smaller window → more valid values after warm-up
        assert len(r7) > len(r14)

    def test_non_series_raises(self) -> None:
        with pytest.raises(MetricsError, match="pandas Series"):
            compute_rsi([100.0, 101.0, 102.0])  # type: ignore[arg-type]

    def test_nan_in_prices_raises(self) -> None:
        dates = pd.date_range("2023-01-01", periods=20, freq="B")
        prices = pd.Series(
            [100.0] * 10 + [float("nan")] + [100.0] * 9, index=dates, dtype=float
        )
        with pytest.raises(MetricsError, match="NaN"):
            compute_rsi(prices)

    def test_too_few_prices_raises(self) -> None:
        dates = pd.date_range("2023-01-01", periods=5, freq="B")
        prices = pd.Series([100.0] * 5, index=dates, dtype=float)
        with pytest.raises(MetricsError, match="At least"):
            compute_rsi(prices, window=14)

    def test_window_one_raises(self) -> None:
        with pytest.raises(MetricsError, match="window"):
            compute_rsi(_make_prices(), window=1)

    def test_window_non_integer_raises(self) -> None:
        with pytest.raises(MetricsError, match="window"):
            compute_rsi(_make_prices(), window=14.0)  # type: ignore[arg-type]

    def test_constant_prices_rsi_undefined_handled(self) -> None:
        """Constant prices → zero gains and losses → avg_loss=0 → RS undefined.
        Result should not raise but may contain NaN or be empty after dropna."""
        dates = pd.date_range("2023-01-01", periods=30, freq="B")
        prices = pd.Series([100.0] * 30, index=dates, dtype=float)
        # Should not raise; result may be empty or all-NaN (avg_loss=0)
        result = compute_rsi(prices, window=14)
        # If values are produced they must be in range
        if len(result) > 0:
            assert (result.dropna() >= 0.0).all()


# ---------------------------------------------------------------------------
# compute_macd
# ---------------------------------------------------------------------------


class TestComputeMACD:
    def test_returns_dataframe(self) -> None:
        result = compute_macd(_make_prices(n=100))
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self) -> None:
        result = compute_macd(_make_prices(n=100))
        assert list(result.columns) == ["macd", "signal", "histogram"]

    def test_no_nans_in_output(self) -> None:
        result = compute_macd(_make_prices(n=100))
        assert not result.isnull().any().any()

    def test_histogram_equals_macd_minus_signal(self) -> None:
        result = compute_macd(_make_prices(n=100))
        expected = result["macd"] - result["signal"]
        pd.testing.assert_series_equal(
            result["histogram"], expected, check_names=False, atol=1e-10
        )

    def test_output_not_empty(self) -> None:
        """EWM (adjust=False) produces values from the first observation — no warm-up NaNs."""
        n = 100
        result = compute_macd(_make_prices(n=n))
        assert len(result) > 0
        assert not result.isnull().any().any()

    def test_custom_periods(self) -> None:
        result = compute_macd(_make_prices(n=80), fast=5, slow=10, signal=3)
        assert isinstance(result, pd.DataFrame)
        assert not result.isnull().any().any()

    def test_fast_equals_slow_raises(self) -> None:
        with pytest.raises(MetricsError, match="fast"):
            compute_macd(_make_prices(n=100), fast=12, slow=12)

    def test_fast_greater_than_slow_raises(self) -> None:
        with pytest.raises(MetricsError, match="fast"):
            compute_macd(_make_prices(n=100), fast=26, slow=12)

    def test_non_series_raises(self) -> None:
        with pytest.raises(MetricsError, match="pandas Series"):
            compute_macd([100.0] * 50)  # type: ignore[arg-type]

    def test_nan_in_prices_raises(self) -> None:
        prices = _make_prices(n=50)
        prices.iloc[10] = float("nan")
        with pytest.raises(MetricsError, match="NaN"):
            compute_macd(prices)

    def test_too_few_prices_raises(self) -> None:
        dates = pd.date_range("2023-01-01", periods=10, freq="B")
        prices = pd.Series([100.0] * 10, index=dates, dtype=float)
        with pytest.raises(MetricsError, match="At least"):
            compute_macd(prices, fast=12, slow=26, signal=9)

    def test_window_one_raises(self) -> None:
        with pytest.raises(MetricsError, match="fast"):
            compute_macd(_make_prices(n=100), fast=1, slow=26, signal=9)

    def test_signal_window_one_raises(self) -> None:
        with pytest.raises(MetricsError, match="signal"):
            compute_macd(_make_prices(n=100), fast=12, slow=26, signal=1)


# ---------------------------------------------------------------------------
# compute_bollinger_bands
# ---------------------------------------------------------------------------


class TestComputeBollingerBands:
    def test_returns_dataframe(self) -> None:
        result = compute_bollinger_bands(_make_prices())
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self) -> None:
        result = compute_bollinger_bands(_make_prices())
        assert list(result.columns) == ["upper", "middle", "lower", "bandwidth", "percent_b"]

    def test_no_nans_in_output(self) -> None:
        result = compute_bollinger_bands(_make_prices())
        assert not result.isnull().any().any()

    def test_upper_ge_middle_ge_lower(self) -> None:
        result = compute_bollinger_bands(_make_prices())
        assert (result["upper"] >= result["middle"]).all()
        assert (result["middle"] >= result["lower"]).all()

    def test_bandwidth_positive(self) -> None:
        result = compute_bollinger_bands(_make_prices())
        assert (result["bandwidth"] >= 0.0).all()

    def test_output_shorter_than_input(self) -> None:
        n = 100
        result = compute_bollinger_bands(_make_prices(n=n), window=20)
        assert len(result) == n - 20 + 1

    def test_custom_window(self) -> None:
        result = compute_bollinger_bands(_make_prices(n=50), window=10)
        assert not result.isnull().any().any()

    def test_wider_std_dev_increases_bandwidth(self) -> None:
        prices = _make_prices()
        narrow = compute_bollinger_bands(prices, std_dev=1.0)
        wide = compute_bollinger_bands(prices, std_dev=3.0)
        assert (wide["bandwidth"] > narrow["bandwidth"]).all()

    def test_percent_b_at_middle_is_half(self) -> None:
        """When price == middle band, %B should be 0.5."""
        # Constant price series: upper = lower = middle → %B is undefined
        # Instead verify: price above middle → %B > 0.5
        prices = _make_prices(seed=42)
        result = compute_bollinger_bands(prices)
        above_mid = result[prices.loc[result.index] > result["middle"]]
        if len(above_mid) > 0:
            assert (above_mid["percent_b"] > 0.5).all()

    def test_std_dev_zero_raises(self) -> None:
        with pytest.raises(MetricsError, match="std_dev"):
            compute_bollinger_bands(_make_prices(), std_dev=0.0)

    def test_std_dev_negative_raises(self) -> None:
        with pytest.raises(MetricsError, match="std_dev"):
            compute_bollinger_bands(_make_prices(), std_dev=-1.0)

    def test_non_series_raises(self) -> None:
        with pytest.raises(MetricsError, match="pandas Series"):
            compute_bollinger_bands([100.0] * 30)  # type: ignore[arg-type]

    def test_nan_in_prices_raises(self) -> None:
        prices = _make_prices(n=50)
        prices.iloc[5] = float("nan")
        with pytest.raises(MetricsError, match="NaN"):
            compute_bollinger_bands(prices)

    def test_too_few_prices_raises(self) -> None:
        dates = pd.date_range("2023-01-01", periods=5, freq="B")
        prices = pd.Series([100.0] * 5, index=dates, dtype=float)
        with pytest.raises(MetricsError, match="At least"):
            compute_bollinger_bands(prices, window=20)

    def test_window_one_raises(self) -> None:
        with pytest.raises(MetricsError, match="window"):
            compute_bollinger_bands(_make_prices(), window=1)
