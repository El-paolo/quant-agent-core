"""
Unit tests for fina.metrics.volatility

Covers: validate_returns, realized_volatility, rolling_volatility.
No external I/O — all tests use in-memory fixtures from conftest.py.
"""

import math

import numpy as np
import pandas as pd
import pytest

from fina.metrics.volatility import (
    VolatilityError,
    realized_volatility,
    rolling_volatility,
    validate_returns,
)


# ---------------------------------------------------------------------------
# validate_returns
# ---------------------------------------------------------------------------


class TestValidateReturns:
    def test_accepts_valid_series(self, sample_returns: pd.Series) -> None:
        result = validate_returns(sample_returns)
        assert isinstance(result, pd.Series)

    def test_accepts_single_column_dataframe(self, sample_returns: pd.Series) -> None:
        df = sample_returns.to_frame()
        result = validate_returns(df)
        assert isinstance(result, pd.Series)

    def test_rejects_multi_column_dataframe(self, sample_returns: pd.Series) -> None:
        df = pd.concat([sample_returns, sample_returns], axis=1)
        with pytest.raises(VolatilityError, match="exactly one column"):
            validate_returns(df)

    def test_rejects_non_series_input(self) -> None:
        with pytest.raises(VolatilityError, match="pandas Series"):
            validate_returns([0.01, -0.02, 0.03])  # type: ignore[arg-type]

    def test_sorts_index(self, sample_returns: pd.Series) -> None:
        shuffled = sample_returns.sample(frac=1, random_state=0)
        result = validate_returns(shuffled)
        assert result.index.is_monotonic_increasing


# ---------------------------------------------------------------------------
# realized_volatility
# ---------------------------------------------------------------------------


class TestRealizedVolatility:
    def test_returns_dict(self, sample_returns: pd.Series) -> None:
        result = realized_volatility(sample_returns)
        assert isinstance(result, dict)

    def test_required_keys_present(self, sample_returns: pd.Series) -> None:
        result = realized_volatility(sample_returns)
        assert "volatility(s.d.)" in result
        assert "volatility(variance)" in result
        assert "annualized" in result
        assert "trading_days" in result
        assert "observations" in result

    def test_observations_equals_input_length(self, sample_returns: pd.Series) -> None:
        result = realized_volatility(sample_returns)
        assert result["observations"] == len(sample_returns)

    def test_annualized_is_larger_than_non_annualized(
        self, sample_returns: pd.Series
    ) -> None:
        ann = realized_volatility(sample_returns, annualize=True)
        non_ann = realized_volatility(sample_returns, annualize=False)
        assert ann["volatility(s.d.)"] > non_ann["volatility(s.d.)"]

    def test_annualized_scales_by_sqrt_trading_days(
        self, sample_returns: pd.Series
    ) -> None:
        trading_days = 252
        ann = realized_volatility(sample_returns, annualize=True, trading_days=trading_days)
        non_ann = realized_volatility(sample_returns, annualize=False)
        ratio = ann["volatility(s.d.)"] / non_ann["volatility(s.d.)"]
        assert ratio == pytest.approx(math.sqrt(trading_days), rel=1e-9)

    def test_variance_equals_sd_squared(self, sample_returns: pd.Series) -> None:
        result = realized_volatility(sample_returns)
        assert result["volatility(variance)"] == pytest.approx(
            result["volatility(s.d.)"] ** 2, rel=1e-9
        )

    def test_trading_days_none_when_not_annualized(
        self, sample_returns: pd.Series
    ) -> None:
        result = realized_volatility(sample_returns, annualize=False)
        assert result["trading_days"] is None

    def test_trading_days_set_when_annualized(self, sample_returns: pd.Series) -> None:
        result = realized_volatility(sample_returns, annualize=True, trading_days=365)
        assert result["trading_days"] == 365

    def test_annualized_flag_in_result(self, sample_returns: pd.Series) -> None:
        assert realized_volatility(sample_returns, annualize=True)["annualized"] is True
        assert realized_volatility(sample_returns, annualize=False)["annualized"] is False

    def test_volatility_is_positive(self, sample_returns: pd.Series) -> None:
        result = realized_volatility(sample_returns)
        assert result["volatility(s.d.)"] > 0

    def test_known_value(self) -> None:
        """Cross-check against a manually computed result."""
        dates = pd.date_range("2023-01-01", periods=5, freq="B")
        returns = pd.Series([0.01, -0.02, 0.03, -0.01, 0.02], index=dates)
        result = realized_volatility(returns, annualize=False)
        expected_sd = float(np.std(returns, ddof=1))
        assert result["volatility(s.d.)"] == pytest.approx(expected_sd, rel=1e-9)


# ---------------------------------------------------------------------------
# rolling_volatility
# ---------------------------------------------------------------------------


class TestRollingVolatility:
    def test_returns_dataframe(self, sample_returns: pd.Series) -> None:
        result = rolling_volatility(sample_returns, window=20)
        assert isinstance(result, pd.DataFrame)

    def test_required_columns_present(self, sample_returns: pd.Series) -> None:
        result = rolling_volatility(sample_returns, window=20)
        assert "volatility(s.d.)" in result.columns
        assert "volatility(variance)" in result.columns

    def test_length_matches_input(self, sample_returns: pd.Series) -> None:
        result = rolling_volatility(sample_returns, window=20)
        assert len(result) == len(sample_returns)

    def test_first_window_minus_one_rows_are_nan(
        self, sample_returns: pd.Series
    ) -> None:
        window = 20
        result = rolling_volatility(sample_returns, window=window)
        assert result["volatility(s.d.)"].iloc[: window - 1].isnull().all()

    def test_values_after_window_are_not_nan(self, sample_returns: pd.Series) -> None:
        window = 20
        result = rolling_volatility(sample_returns, window=window)
        assert not result["volatility(s.d.)"].iloc[window:].isnull().any()

    def test_window_too_large_raises(self, sample_returns: pd.Series) -> None:
        with pytest.raises(VolatilityError, match="Window must be smaller"):
            rolling_volatility(sample_returns, window=9999)

    def test_window_equal_to_length_raises(self, sample_returns: pd.Series) -> None:
        with pytest.raises(VolatilityError):
            rolling_volatility(sample_returns, window=len(sample_returns))

    def test_annualized_larger_than_non_annualized(
        self, sample_returns: pd.Series
    ) -> None:
        ann = rolling_volatility(sample_returns, window=20, annualize=True)
        non_ann = rolling_volatility(sample_returns, window=20, annualize=False)
        # Compare only rows where both have values
        valid = ann["volatility(s.d.)"].notna() & non_ann["volatility(s.d.)"].notna()
        assert (ann["volatility(s.d.)"][valid] > non_ann["volatility(s.d.)"][valid]).all()

    def test_attrs_metadata(self, sample_returns: pd.Series) -> None:
        window = 20
        result = rolling_volatility(sample_returns, window=window, annualize=True)
        assert result.attrs["window"] == window
        assert result.attrs["annualized"] is True
        assert result.attrs["trading_days"] == 252

    def test_attrs_trading_days_none_when_not_annualized(
        self, sample_returns: pd.Series
    ) -> None:
        result = rolling_volatility(sample_returns, window=20, annualize=False)
        assert result.attrs["trading_days"] is None

    def test_variance_equals_sd_squared_for_valid_rows(
        self, sample_returns: pd.Series
    ) -> None:
        result = rolling_volatility(sample_returns, window=20, annualize=False)
        valid = result["volatility(s.d.)"].notna()
        sd = result["volatility(s.d.)"][valid]
        var = result["volatility(variance)"][valid]
        pd.testing.assert_series_equal(var, sd**2, check_names=False)
