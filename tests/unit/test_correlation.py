"""
Unit tests for fina.metrics.correlation

Covers: correlation_matrix, rolling_correlation, compute_beta.
No external I/O — all tests use in-memory fixtures.
"""

import numpy as np
import pandas as pd
import pytest

from fina.core.exceptions import MetricsError
from fina.metrics.correlation import (
    compute_beta,
    correlation_matrix,
    rolling_correlation,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_returns(
    n: int = 100,
    seed: int = 0,
    drift: float = 0.0005,
    vol: float = 0.01,
    name: str = "A",
) -> pd.Series:
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed)
    values = rng.normal(drift, vol, n)
    return pd.Series(values, index=dates, name=name, dtype=float)


def _make_returns_df(n: int = 100) -> pd.DataFrame:
    """DataFrame with three correlated return series."""
    rng = np.random.default_rng(99)
    common = rng.normal(0.0, 0.01, n)
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "A": common + rng.normal(0.0, 0.005, n),
            "B": common + rng.normal(0.0, 0.005, n),
            "C": rng.normal(0.0, 0.01, n),  # independent
        },
        index=dates,
    )


def _perfect_correlation_pair(n: int = 50) -> tuple[pd.Series, pd.Series]:
    """Two series with correlation = 1.0."""
    a = _make_returns(n=n, seed=7, name="X")
    b = a * 2 + 0.001  # linear transform → perfect correlation
    b.name = "Y"
    return a, b


def _anti_correlated_pair(n: int = 50) -> tuple[pd.Series, pd.Series]:
    """Two series with correlation ≈ -1.0."""
    a = _make_returns(n=n, seed=7, name="X")
    b = -a
    b.name = "Y"
    return a, b


# ---------------------------------------------------------------------------
# correlation_matrix
# ---------------------------------------------------------------------------


class TestCorrelationMatrix:
    def test_returns_dataframe(self) -> None:
        result = correlation_matrix(_make_returns_df())
        assert isinstance(result, pd.DataFrame)

    def test_shape_is_square(self) -> None:
        df = _make_returns_df()
        result = correlation_matrix(df)
        assert result.shape == (df.shape[1], df.shape[1])

    def test_diagonal_is_one(self) -> None:
        result = correlation_matrix(_make_returns_df())
        for i in range(len(result)):
            assert result.iloc[i, i] == pytest.approx(1.0)

    def test_symmetric(self) -> None:
        result = correlation_matrix(_make_returns_df())
        pd.testing.assert_frame_equal(result, result.T)

    def test_values_between_minus_one_and_one(self) -> None:
        result = correlation_matrix(_make_returns_df())
        assert (result.values >= -1.0 - 1e-9).all()
        assert (result.values <= 1.0 + 1e-9).all()

    def test_correlated_assets_have_high_correlation(self) -> None:
        result = correlation_matrix(_make_returns_df())
        # A and B share a common factor — should be positively correlated
        assert result.loc["A", "B"] > 0.5

    def test_pearson_method(self) -> None:
        result = correlation_matrix(_make_returns_df(), method="pearson")
        assert isinstance(result, pd.DataFrame)

    def test_spearman_method(self) -> None:
        result = correlation_matrix(_make_returns_df(), method="spearman")
        assert isinstance(result, pd.DataFrame)

    def test_kendall_method(self) -> None:
        result = correlation_matrix(_make_returns_df(), method="kendall")
        assert isinstance(result, pd.DataFrame)

    def test_invalid_method_raises(self) -> None:
        with pytest.raises(MetricsError, match="Invalid method"):
            correlation_matrix(_make_returns_df(), method="cosine")

    def test_non_dataframe_raises(self) -> None:
        with pytest.raises(MetricsError, match="DataFrame"):
            correlation_matrix(_make_returns(name="A"))  # type: ignore[arg-type]

    def test_single_column_raises(self) -> None:
        df = pd.DataFrame({"A": _make_returns().values})
        with pytest.raises(MetricsError, match="at least 2 columns"):
            correlation_matrix(df)

    def test_too_few_rows_raises(self) -> None:
        df = pd.DataFrame({"A": [0.01], "B": [0.02]})
        with pytest.raises(MetricsError, match="at least 2 rows"):
            correlation_matrix(df)

    def test_nan_in_dataframe_raises(self) -> None:
        df = _make_returns_df()
        df.iloc[0, 0] = float("nan")
        with pytest.raises(MetricsError, match="NaN"):
            correlation_matrix(df)

    def test_columns_preserved(self) -> None:
        df = _make_returns_df()
        result = correlation_matrix(df)
        assert list(result.columns) == list(df.columns)
        assert list(result.index) == list(df.columns)


# ---------------------------------------------------------------------------
# rolling_correlation
# ---------------------------------------------------------------------------


class TestRollingCorrelation:
    def test_returns_series(self) -> None:
        a = _make_returns(seed=1, name="A")
        b = _make_returns(seed=2, name="B")
        result = rolling_correlation(a, b)
        assert isinstance(result, pd.Series)

    def test_length_matches_input(self) -> None:
        a = _make_returns(n=100, seed=1)
        b = _make_returns(n=100, seed=2)
        result = rolling_correlation(a, b, window=20)
        assert len(result) == 100

    def test_first_window_minus_one_are_nan(self) -> None:
        a = _make_returns(n=50, seed=1)
        b = _make_returns(n=50, seed=2)
        window = 10
        result = rolling_correlation(a, b, window=window)
        assert result.iloc[: window - 1].isnull().all()

    def test_values_after_warmup_are_not_nan(self) -> None:
        a = _make_returns(n=50, seed=1)
        b = _make_returns(n=50, seed=2)
        window = 10
        result = rolling_correlation(a, b, window=window)
        assert not result.iloc[window - 1 :].isnull().any()

    def test_perfect_correlation_approaches_one(self) -> None:
        a, b = _perfect_correlation_pair(n=50)
        result = rolling_correlation(a, b, window=5)
        # After warmup all values should be ≈ 1
        valid = result.dropna()
        assert (valid > 0.999).all()

    def test_anti_correlated_approaches_minus_one(self) -> None:
        a, b = _anti_correlated_pair(n=50)
        result = rolling_correlation(a, b, window=5)
        valid = result.dropna()
        assert (valid < -0.999).all()

    def test_values_in_valid_range(self) -> None:
        a = _make_returns(n=100, seed=3)
        b = _make_returns(n=100, seed=4)
        result = rolling_correlation(a, b, window=20)
        valid = result.dropna()
        assert (valid >= -1.0 - 1e-9).all()
        assert (valid <= 1.0 + 1e-9).all()

    def test_default_window_is_20(self) -> None:
        a = _make_returns(n=100, seed=1)
        b = _make_returns(n=100, seed=2)
        result = rolling_correlation(a, b)
        # First 19 should be NaN (window=20 default)
        assert result.iloc[:19].isnull().all()
        assert not result.iloc[19:].isnull().any()

    def test_mismatched_index_aligns(self) -> None:
        """Series with different lengths align on their shared index."""
        a = _make_returns(n=100, seed=1)
        b = _make_returns(n=80, seed=2)  # shorter → shared index has 80 obs
        result = rolling_correlation(a, b, window=10)
        assert len(result) == 80

    def test_window_too_large_raises(self) -> None:
        a = _make_returns(n=30, seed=1)
        b = _make_returns(n=30, seed=2)
        with pytest.raises(MetricsError, match="window"):
            rolling_correlation(a, b, window=31)

    def test_window_less_than_two_raises(self) -> None:
        a = _make_returns(seed=1)
        b = _make_returns(seed=2)
        with pytest.raises(MetricsError, match="window"):
            rolling_correlation(a, b, window=1)

    def test_non_series_a_raises(self) -> None:
        b = _make_returns(seed=2)
        with pytest.raises(MetricsError, match="returns_a"):
            rolling_correlation([0.01, 0.02], b)  # type: ignore[arg-type]

    def test_non_series_b_raises(self) -> None:
        a = _make_returns(seed=1)
        with pytest.raises(MetricsError, match="returns_b"):
            rolling_correlation(a, [0.01, 0.02])  # type: ignore[arg-type]

    def test_nan_in_a_raises(self) -> None:
        a = _make_returns(n=50, seed=1)
        a.iloc[5] = float("nan")
        b = _make_returns(n=50, seed=2)
        with pytest.raises(MetricsError, match="NaN"):
            rolling_correlation(a, b)

    def test_nan_in_b_raises(self) -> None:
        a = _make_returns(n=50, seed=1)
        b = _make_returns(n=50, seed=2)
        b.iloc[5] = float("nan")
        with pytest.raises(MetricsError, match="NaN"):
            rolling_correlation(a, b)


# ---------------------------------------------------------------------------
# compute_beta
# ---------------------------------------------------------------------------


class TestComputeBeta:
    def test_returns_dict(self) -> None:
        asset = _make_returns(seed=1)
        market = _make_returns(seed=99)
        result = compute_beta(asset, market)
        assert isinstance(result, dict)

    def test_required_keys_present(self) -> None:
        asset = _make_returns(seed=1)
        market = _make_returns(seed=99)
        result = compute_beta(asset, market)
        assert "beta" in result
        assert "alpha" in result
        assert "correlation" in result
        assert "r_squared" in result
        assert "market_variance" in result
        assert "observations" in result

    def test_observations_equals_aligned_length(self) -> None:
        asset = _make_returns(n=100, seed=1)
        market = _make_returns(n=100, seed=99)
        result = compute_beta(asset, market)
        assert result["observations"] == 100

    def test_observations_reflects_shorter_series(self) -> None:
        asset = _make_returns(n=80, seed=1)
        market = _make_returns(n=100, seed=99)
        result = compute_beta(asset, market)
        assert result["observations"] == 80

    def test_beta_of_market_with_itself_is_one(self) -> None:
        market = _make_returns(n=100, seed=99)
        result = compute_beta(market, market)
        assert result["beta"] == pytest.approx(1.0, rel=1e-9)

    def test_beta_of_anti_asset_is_minus_one(self) -> None:
        market = _make_returns(n=100, seed=99)
        anti = -market
        anti.name = "ANTI"
        result = compute_beta(anti, market)
        assert result["beta"] == pytest.approx(-1.0, rel=1e-9)

    def test_r_squared_equals_correlation_squared(self) -> None:
        asset = _make_returns(seed=1)
        market = _make_returns(seed=99)
        result = compute_beta(asset, market)
        assert result["r_squared"] == pytest.approx(result["correlation"] ** 2, rel=1e-9)

    def test_r_squared_between_zero_and_one(self) -> None:
        asset = _make_returns(seed=1)
        market = _make_returns(seed=99)
        result = compute_beta(asset, market)
        assert 0.0 <= result["r_squared"] <= 1.0 + 1e-9

    def test_market_variance_is_positive(self) -> None:
        asset = _make_returns(seed=1)
        market = _make_returns(seed=99)
        result = compute_beta(asset, market)
        assert result["market_variance"] > 0

    def test_known_beta_value(self) -> None:
        """Manual cross-check: beta = cov(a, m) / var(m)."""
        dates = pd.date_range("2023-01-01", periods=6, freq="B")
        asset = pd.Series([0.01, 0.02, -0.01, 0.03, 0.01, -0.02], index=dates, name="A")
        market = pd.Series([0.005, 0.01, -0.005, 0.015, 0.005, -0.01], index=dates, name="M")
        expected_beta = float(np.cov(asset.values, market.values, ddof=1)[0, 1] / market.var())
        result = compute_beta(asset, market)
        assert result["beta"] == pytest.approx(expected_beta, rel=1e-9)

    def test_zero_market_variance_raises(self) -> None:
        dates = pd.date_range("2023-01-01", periods=5, freq="B")
        asset = pd.Series([0.01, 0.02, -0.01, 0.03, 0.01], index=dates, name="A")
        market = pd.Series([0.0, 0.0, 0.0, 0.0, 0.0], index=dates, name="M")
        with pytest.raises(MetricsError, match="zero variance"):
            compute_beta(asset, market)

    def test_non_series_asset_raises(self) -> None:
        market = _make_returns(seed=99)
        with pytest.raises(MetricsError, match="asset_returns"):
            compute_beta([0.01, 0.02], market)  # type: ignore[arg-type]

    def test_non_series_market_raises(self) -> None:
        asset = _make_returns(seed=1)
        with pytest.raises(MetricsError, match="market_returns"):
            compute_beta(asset, [0.01, 0.02])  # type: ignore[arg-type]

    def test_nan_in_asset_raises(self) -> None:
        asset = _make_returns(n=50, seed=1)
        asset.iloc[0] = float("nan")
        market = _make_returns(n=50, seed=99)
        with pytest.raises(MetricsError, match="NaN"):
            compute_beta(asset, market)

    def test_nan_in_market_raises(self) -> None:
        asset = _make_returns(n=50, seed=1)
        market = _make_returns(n=50, seed=99)
        market.iloc[0] = float("nan")
        with pytest.raises(MetricsError, match="NaN"):
            compute_beta(asset, market)

    def test_high_beta_asset(self) -> None:
        """Asset = 2 * market + noise → beta close to 2."""
        rng = np.random.default_rng(55)
        n = 200
        dates = pd.date_range("2023-01-01", periods=n, freq="B")
        market = pd.Series(rng.normal(0.001, 0.01, n), index=dates, name="M")
        asset = pd.Series(2.0 * market.values + rng.normal(0, 0.002, n), index=dates, name="A")
        result = compute_beta(asset, market)
        assert result["beta"] == pytest.approx(2.0, abs=0.1)

    def test_low_beta_asset(self) -> None:
        """Asset = 0.5 * market + noise → beta close to 0.5."""
        rng = np.random.default_rng(66)
        n = 200
        dates = pd.date_range("2023-01-01", periods=n, freq="B")
        market = pd.Series(rng.normal(0.001, 0.01, n), index=dates, name="M")
        asset = pd.Series(0.5 * market.values + rng.normal(0, 0.002, n), index=dates, name="A")
        result = compute_beta(asset, market)
        assert result["beta"] == pytest.approx(0.5, abs=0.1)
