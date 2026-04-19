"""
Unit tests for fina.backtest.weights — portfolio weight schemes.
"""

import numpy as np
import pandas as pd
import pytest

from fina.backtest.weights import custom_weight, equal_weight, inverse_vol_weight
from fina.core.exceptions import BacktestError


class TestEqualWeight:
    def test_single_asset(self) -> None:
        assert equal_weight(1) == [1.0]

    def test_three_assets(self) -> None:
        w = equal_weight(3)
        assert len(w) == 3
        assert abs(sum(w) - 1.0) < 1e-10

    def test_sums_to_one(self) -> None:
        for n in [2, 5, 10, 20]:
            assert abs(sum(equal_weight(n)) - 1.0) < 1e-10

    def test_zero_raises(self) -> None:
        with pytest.raises(BacktestError):
            equal_weight(0)


class TestInverseVolWeight:
    def test_low_vol_gets_higher_weight(self) -> None:
        rng = np.random.default_rng(42)
        dates = pd.date_range("2023-01-01", periods=100, freq="B")
        df = pd.DataFrame(
            {
                "LOW_VOL": rng.normal(0.001, 0.005, 100),
                "HIGH_VOL": rng.normal(0.001, 0.03, 100),
            },
            index=dates,
        )
        w = inverse_vol_weight(df)
        assert w[0] > w[1]  # LOW_VOL should get more weight

    def test_sums_to_one(self) -> None:
        rng = np.random.default_rng(42)
        dates = pd.date_range("2023-01-01", periods=100, freq="B")
        df = pd.DataFrame(
            {
                "A": rng.normal(0, 0.01, 100),
                "B": rng.normal(0, 0.02, 100),
                "C": rng.normal(0, 0.015, 100),
            },
            index=dates,
        )
        w = inverse_vol_weight(df)
        assert abs(sum(w) - 1.0) < 1e-4

    def test_empty_raises(self) -> None:
        with pytest.raises(BacktestError):
            inverse_vol_weight(pd.DataFrame())


class TestCustomWeight:
    def test_normalizes(self) -> None:
        w = custom_weight([2.0, 3.0, 5.0])
        assert abs(sum(w) - 1.0) < 1e-10
        assert abs(w[0] - 0.2) < 1e-6

    def test_already_normalized(self) -> None:
        w = custom_weight([0.5, 0.5])
        assert abs(sum(w) - 1.0) < 1e-10

    def test_empty_raises(self) -> None:
        with pytest.raises(BacktestError):
            custom_weight([])

    def test_negative_raises(self) -> None:
        with pytest.raises(BacktestError, match="non-negative"):
            custom_weight([0.5, -0.5])

    def test_all_zeros_raises(self) -> None:
        with pytest.raises(BacktestError, match="positive"):
            custom_weight([0.0, 0.0])
