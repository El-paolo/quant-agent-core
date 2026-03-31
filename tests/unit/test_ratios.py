"""
Unit tests for fina.metrics.ratios

Covers: sharpe_ratio, sortino_ratio.
No external I/O — all tests use in-memory fixtures from conftest.py.
"""

import math

import numpy as np
import pandas as pd
import pytest

from fina.core.exceptions import MetricsError
from fina.metrics.ratios import sharpe_ratio, sortino_ratio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _constant_returns(value: float = 0.001, n: int = 50) -> pd.Series:
    """Series of identical returns — zero volatility, triggers edge cases."""
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.Series([value] * n, index=dates, dtype=float)


def _positive_returns(n: int = 100) -> pd.Series:
    """Series of strictly positive returns — no downside, triggers Sortino edge."""
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(7)
    return pd.Series(rng.uniform(0.001, 0.01, n), index=dates, dtype=float)


# ---------------------------------------------------------------------------
# sharpe_ratio
# ---------------------------------------------------------------------------


class TestSharpeRatio:
    def test_returns_dict(self, sample_returns: pd.Series) -> None:
        result = sharpe_ratio(sample_returns)
        assert isinstance(result, dict)

    def test_required_keys_present(self, sample_returns: pd.Series) -> None:
        result = sharpe_ratio(sample_returns)
        assert "sharpe_ratio" in result
        assert "mean_return" in result
        assert "volatility" in result
        assert "risk_free_rate" in result
        assert "annualized" in result
        assert "trading_days" in result
        assert "observations" in result

    def test_observations_equals_input_length(self, sample_returns: pd.Series) -> None:
        result = sharpe_ratio(sample_returns)
        assert result["observations"] == len(sample_returns)

    def test_annualized_flag(self, sample_returns: pd.Series) -> None:
        assert sharpe_ratio(sample_returns, annualize=True)["annualized"] is True
        assert sharpe_ratio(sample_returns, annualize=False)["annualized"] is False

    def test_trading_days_none_when_not_annualized(self, sample_returns: pd.Series) -> None:
        result = sharpe_ratio(sample_returns, annualize=False)
        assert result["trading_days"] is None

    def test_annualized_larger_in_absolute_value(self, sample_returns: pd.Series) -> None:
        ann = sharpe_ratio(sample_returns, annualize=True)
        non_ann = sharpe_ratio(sample_returns, annualize=False)
        assert abs(ann["sharpe_ratio"]) > abs(non_ann["sharpe_ratio"])

    def test_annualization_scales_by_sqrt_trading_days(
        self, sample_returns: pd.Series
    ) -> None:
        td = 252
        ann = sharpe_ratio(sample_returns, annualize=True, trading_days=td)
        non_ann = sharpe_ratio(sample_returns, annualize=False, trading_days=td)
        ratio = ann["sharpe_ratio"] / non_ann["sharpe_ratio"]
        assert ratio == pytest.approx(math.sqrt(td), rel=1e-9)

    def test_higher_rf_lowers_sharpe(self, sample_returns: pd.Series) -> None:
        low_rf = sharpe_ratio(sample_returns, risk_free_rate=0.0)
        high_rf = sharpe_ratio(sample_returns, risk_free_rate=0.10)
        assert low_rf["sharpe_ratio"] > high_rf["sharpe_ratio"]

    def test_known_value(self) -> None:
        """Manual cross-check against formula."""
        dates = pd.date_range("2023-01-01", periods=5, freq="B")
        returns = pd.Series([0.01, 0.02, -0.01, 0.03, 0.01], index=dates)
        result = sharpe_ratio(returns, risk_free_rate=0.0, annualize=False)
        expected = float(returns.mean()) / float(returns.std())
        assert result["sharpe_ratio"] == pytest.approx(expected, rel=1e-9)

    def test_zero_volatility_raises(self) -> None:
        with pytest.raises(MetricsError, match="zero volatility"):
            sharpe_ratio(_constant_returns())

    def test_non_series_raises(self) -> None:
        with pytest.raises(MetricsError, match="pandas Series"):
            sharpe_ratio([0.01, 0.02, -0.01])  # type: ignore[arg-type]

    def test_too_few_observations_raises(self) -> None:
        dates = pd.date_range("2023-01-01", periods=1, freq="B")
        with pytest.raises(MetricsError, match="At least 2"):
            sharpe_ratio(pd.Series([0.01], index=dates))

    def test_nan_in_returns_raises(self) -> None:
        dates = pd.date_range("2023-01-01", periods=3, freq="B")
        returns = pd.Series([0.01, float("nan"), 0.02], index=dates)
        with pytest.raises(MetricsError, match="NaN"):
            sharpe_ratio(returns)

    def test_invalid_rf_type_raises(self, sample_returns: pd.Series) -> None:
        with pytest.raises(MetricsError, match="risk_free_rate"):
            sharpe_ratio(sample_returns, risk_free_rate="0.05")  # type: ignore[arg-type]

    def test_invalid_trading_days_raises(self, sample_returns: pd.Series) -> None:
        with pytest.raises(MetricsError, match="trading_days"):
            sharpe_ratio(sample_returns, trading_days=0)

    def test_risk_free_rate_stored_in_result(self, sample_returns: pd.Series) -> None:
        result = sharpe_ratio(sample_returns, risk_free_rate=0.05)
        assert result["risk_free_rate"] == pytest.approx(0.05)


# ---------------------------------------------------------------------------
# sortino_ratio
# ---------------------------------------------------------------------------


class TestSortinoRatio:
    def test_returns_dict(self, sample_returns: pd.Series) -> None:
        result = sortino_ratio(sample_returns)
        assert isinstance(result, dict)

    def test_required_keys_present(self, sample_returns: pd.Series) -> None:
        result = sortino_ratio(sample_returns)
        assert "sortino_ratio" in result
        assert "mean_return" in result
        assert "downside_deviation" in result
        assert "minimum_acceptable_return" in result
        assert "annualized" in result
        assert "trading_days" in result
        assert "observations" in result
        assert "downside_observations" in result

    def test_observations_equals_input_length(self, sample_returns: pd.Series) -> None:
        result = sortino_ratio(sample_returns)
        assert result["observations"] == len(sample_returns)

    def test_downside_obs_less_than_total(self, sample_returns: pd.Series) -> None:
        result = sortino_ratio(sample_returns, minimum_acceptable_return=0.0)
        assert result["downside_observations"] < result["observations"]

    def test_annualized_flag(self, sample_returns: pd.Series) -> None:
        assert sortino_ratio(sample_returns, annualize=True)["annualized"] is True
        assert sortino_ratio(sample_returns, annualize=False)["annualized"] is False

    def test_trading_days_none_when_not_annualized(self, sample_returns: pd.Series) -> None:
        result = sortino_ratio(sample_returns, annualize=False)
        assert result["trading_days"] is None

    def test_sortino_higher_than_sharpe_for_positive_skew(self) -> None:
        """For a positively skewed return distribution, Sortino > Sharpe."""
        dates = pd.date_range("2023-01-01", periods=200, freq="B")
        rng = np.random.default_rng(1)
        # Mix mostly small positive returns with rare large positives
        returns = pd.Series(
            np.concatenate([rng.normal(0.002, 0.005, 180), rng.uniform(0.05, 0.1, 20)]),
            index=dates,
        )
        sr = sharpe_ratio(returns, annualize=True)["sharpe_ratio"]
        so = sortino_ratio(returns, annualize=True)["sortino_ratio"]
        assert so > sr

    def test_no_downside_raises(self) -> None:
        with pytest.raises(MetricsError, match="no returns fall below"):
            sortino_ratio(_positive_returns(), minimum_acceptable_return=0.0)

    def test_known_value(self) -> None:
        """Manual cross-check: semi-deviation formula."""
        dates = pd.date_range("2023-01-01", periods=6, freq="B")
        returns = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02, -0.03], index=dates)
        mar = 0.0
        downside = returns[returns < mar] - mar
        expected_dd = float(np.sqrt((downside**2).mean()))
        expected_ratio = float(returns.mean()) / expected_dd
        result = sortino_ratio(returns, minimum_acceptable_return=mar, annualize=False)
        assert result["sortino_ratio"] == pytest.approx(expected_ratio, rel=1e-9)
        assert result["downside_deviation"] == pytest.approx(expected_dd, rel=1e-9)

    def test_mar_stored_in_result(self, sample_returns: pd.Series) -> None:
        result = sortino_ratio(sample_returns, minimum_acceptable_return=0.02)
        assert result["minimum_acceptable_return"] == pytest.approx(0.02)

    def test_non_series_raises(self) -> None:
        with pytest.raises(MetricsError, match="pandas Series"):
            sortino_ratio([0.01, -0.02, 0.03])  # type: ignore[arg-type]

    def test_too_few_observations_raises(self) -> None:
        dates = pd.date_range("2023-01-01", periods=1, freq="B")
        with pytest.raises(MetricsError, match="At least 2"):
            sortino_ratio(pd.Series([0.01], index=dates))

    def test_nan_in_returns_raises(self) -> None:
        dates = pd.date_range("2023-01-01", periods=3, freq="B")
        returns = pd.Series([0.01, float("nan"), -0.01], index=dates)
        with pytest.raises(MetricsError, match="NaN"):
            sortino_ratio(returns)

    def test_invalid_mar_type_raises(self, sample_returns: pd.Series) -> None:
        with pytest.raises(MetricsError, match="minimum_acceptable_return"):
            sortino_ratio(sample_returns, minimum_acceptable_return="0.0")  # type: ignore[arg-type]

    def test_invalid_trading_days_raises(self, sample_returns: pd.Series) -> None:
        with pytest.raises(MetricsError, match="trading_days"):
            sortino_ratio(sample_returns, trading_days=-1)
