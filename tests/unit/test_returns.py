"""
Unit tests for fina.metrics.returns

Covers: validate_prices, simple_returns, log_returns, compute_returns.
No external I/O — all tests use in-memory fixtures from conftest.py.
"""

import numpy as np
import pandas as pd
import pytest

from fina.metrics.returns import (
    ReturnsError,
    compute_returns,
    log_returns,
    simple_returns,
    validate_prices,
)


# ---------------------------------------------------------------------------
# validate_prices
# ---------------------------------------------------------------------------


class TestValidatePrices:
    def test_accepts_valid_series(self, sample_prices: pd.Series) -> None:
        result = validate_prices(sample_prices)
        assert isinstance(result, pd.Series)

    def test_accepts_single_column_dataframe(self, sample_prices: pd.Series) -> None:
        df = sample_prices.to_frame()
        result = validate_prices(df)
        assert isinstance(result, pd.Series)

    def test_rejects_multi_column_dataframe(self, sample_prices: pd.Series) -> None:
        df = pd.concat([sample_prices, sample_prices], axis=1)
        with pytest.raises(ReturnsError, match="exactly one column"):
            validate_prices(df)

    def test_rejects_non_series_input(self) -> None:
        with pytest.raises(ReturnsError, match="pandas Series"):
            validate_prices([100, 101, 102])  # type: ignore[arg-type]

    def test_rejects_single_price(self, single_price: pd.Series) -> None:
        with pytest.raises(ReturnsError, match="At least two"):
            validate_prices(single_price)

    def test_rejects_non_positive_prices(self, prices_with_negatives: pd.Series) -> None:
        with pytest.raises(ReturnsError, match="strictly positive"):
            validate_prices(prices_with_negatives)

    def test_rejects_nan_prices(self, prices_with_nan: pd.Series) -> None:
        with pytest.raises(ReturnsError, match="null"):
            validate_prices(prices_with_nan)

    def test_sorts_index(self, sample_prices: pd.Series) -> None:
        shuffled = sample_prices.sample(frac=1, random_state=0)
        result = validate_prices(shuffled)
        assert result.index.is_monotonic_increasing


# ---------------------------------------------------------------------------
# simple_returns
# ---------------------------------------------------------------------------


class TestSimpleReturns:
    def test_returns_series(self, sample_prices: pd.Series) -> None:
        result = simple_returns(sample_prices)
        assert isinstance(result, pd.Series)

    def test_length_is_n_minus_one(self, sample_prices: pd.Series) -> None:
        result = simple_returns(sample_prices)
        assert len(result) == len(sample_prices) - 1

    def test_no_nan_values(self, sample_prices: pd.Series) -> None:
        result = simple_returns(sample_prices)
        assert not result.isnull().any()

    def test_formula_correctness(self) -> None:
        """r_t = (P_t - P_{t-1}) / P_{t-1}"""
        dates = pd.date_range("2023-01-01", periods=3, freq="B")
        prices = pd.Series([100.0, 110.0, 99.0], index=dates)
        result = simple_returns(prices)
        assert result.iloc[0] == pytest.approx(0.10, rel=1e-9)
        assert result.iloc[1] == pytest.approx(-0.10, rel=1e-6)

    def test_index_aligned_with_prices(self, sample_prices: pd.Series) -> None:
        result = simple_returns(sample_prices)
        assert result.index[0] == sample_prices.index[1]
        assert result.index[-1] == sample_prices.index[-1]

    def test_propagates_validation_error(self, prices_with_nan: pd.Series) -> None:
        with pytest.raises(ReturnsError):
            simple_returns(prices_with_nan)


# ---------------------------------------------------------------------------
# log_returns
# ---------------------------------------------------------------------------


class TestLogReturns:
    def test_returns_series(self, sample_prices: pd.Series) -> None:
        result = log_returns(sample_prices)
        assert isinstance(result, pd.Series)

    def test_length_is_n_minus_one(self, sample_prices: pd.Series) -> None:
        result = log_returns(sample_prices)
        assert len(result) == len(sample_prices) - 1

    def test_no_nan_values(self, sample_prices: pd.Series) -> None:
        result = log_returns(sample_prices)
        assert not result.isnull().any()

    def test_formula_correctness(self) -> None:
        """r_t = ln(P_t / P_{t-1})"""
        dates = pd.date_range("2023-01-01", periods=2, freq="B")
        prices = pd.Series([100.0, np.e * 100], index=dates)
        result = log_returns(prices)
        assert result.iloc[0] == pytest.approx(1.0, rel=1e-9)

    def test_log_returns_smaller_than_simple_for_positive_returns(
        self, sample_prices: pd.Series
    ) -> None:
        """For positive returns: log return < simple return (Jensen's inequality)."""
        sr = simple_returns(sample_prices)
        lr = log_returns(sample_prices)
        positive_mask = sr > 0
        assert (lr[positive_mask] < sr[positive_mask]).all()

    def test_propagates_validation_error(self, prices_with_negatives: pd.Series) -> None:
        with pytest.raises(ReturnsError):
            log_returns(prices_with_negatives)


# ---------------------------------------------------------------------------
# compute_returns
# ---------------------------------------------------------------------------


class TestComputeReturns:
    def test_default_method_is_log(self, sample_prices: pd.Series) -> None:
        result = compute_returns(sample_prices)
        assert result["method"] == "log"

    def test_returns_dict_with_required_keys(self, sample_prices: pd.Series) -> None:
        result = compute_returns(sample_prices)
        assert "returns" in result
        assert "method" in result
        assert "observations" in result

    def test_observations_matches_returns_length(self, sample_prices: pd.Series) -> None:
        result = compute_returns(sample_prices)
        assert result["observations"] == len(result["returns"])

    def test_simple_method(self, sample_prices: pd.Series) -> None:
        result = compute_returns(sample_prices, method="simple")
        assert result["method"] == "simple"
        assert isinstance(result["returns"], pd.Series)

    def test_log_method(self, sample_prices: pd.Series) -> None:
        result = compute_returns(sample_prices, method="log")
        assert result["method"] == "log"

    def test_invalid_method_raises(self, sample_prices: pd.Series) -> None:
        with pytest.raises(ReturnsError, match="Method must be"):
            compute_returns(sample_prices, method="invalid")  # type: ignore[arg-type]

    def test_observations_is_n_minus_one(self, sample_prices: pd.Series) -> None:
        result = compute_returns(sample_prices)
        assert result["observations"] == len(sample_prices) - 1
