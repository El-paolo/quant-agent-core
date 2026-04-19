"""
Unit tests for fina.data.cleaner

Covers: handle_nans, normalize_timezone, detect_outliers, clean_prices.
No external I/O — all tests use in-memory data.
"""

import numpy as np
import pandas as pd
import pytest

from fina.core.exceptions import ValidationError
from fina.data.cleaner import (
    clean_dataframe,
    clean_prices,
    detect_outliers,
    handle_nans,
    normalize_timezone,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prices(values: list[float], tz: str | None = None) -> pd.Series:
    idx = pd.date_range("2023-01-01", periods=len(values), freq="B")
    if tz:
        idx = idx.tz_localize(tz)
    return pd.Series(values, index=idx, name="TEST", dtype=float)


# ---------------------------------------------------------------------------
# handle_nans
# ---------------------------------------------------------------------------


class TestHandleNans:
    def test_returns_copy_when_no_nans(self) -> None:
        prices = _make_prices([100.0, 101.0, 102.0])
        result = handle_nans(prices)
        assert not result.isnull().any()
        assert len(result) == 3

    def test_ffill_fills_interior_nans(self) -> None:
        prices = _make_prices([100.0, float("nan"), 102.0])
        result = handle_nans(prices, method="ffill")
        assert result.iloc[1] == pytest.approx(100.0)

    def test_bfill_fills_interior_nans(self) -> None:
        prices = _make_prices([100.0, float("nan"), 102.0])
        result = handle_nans(prices, method="bfill")
        assert result.iloc[1] == pytest.approx(102.0)

    def test_linear_interpolates(self) -> None:
        prices = _make_prices([100.0, float("nan"), 102.0])
        result = handle_nans(prices, method="linear")
        assert result.iloc[1] == pytest.approx(101.0)

    def test_drop_removes_nan_rows(self) -> None:
        prices = _make_prices([100.0, float("nan"), 102.0])
        result = handle_nans(prices, method="drop")
        assert len(result) == 2
        assert not result.isnull().any()

    def test_leading_nans_dropped_after_ffill(self) -> None:
        prices = _make_prices([float("nan"), float("nan"), 102.0, 103.0])
        result = handle_nans(prices, method="ffill")
        assert not result.isnull().any()
        assert result.iloc[0] == pytest.approx(102.0)

    def test_result_has_no_nans(self, sample_prices: pd.Series) -> None:
        # Inject some NaNs into the fixture
        noisy = sample_prices.copy()
        noisy.iloc[5] = float("nan")
        noisy.iloc[20] = float("nan")
        result = handle_nans(noisy)
        assert not result.isnull().any()

    def test_invalid_method_raises(self) -> None:
        prices = _make_prices([100.0, 101.0])
        with pytest.raises(ValidationError, match="Invalid fill method"):
            handle_nans(prices, method="cubic")

    def test_non_series_raises(self) -> None:
        with pytest.raises(ValidationError, match="pandas Series"):
            handle_nans([100.0, 101.0])  # type: ignore[arg-type]

    def test_multiple_consecutive_nans_ffill(self) -> None:
        prices = _make_prices([100.0, float("nan"), float("nan"), float("nan"), 105.0])
        result = handle_nans(prices, method="ffill")
        for val in result.iloc[1:4]:
            assert val == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# normalize_timezone
# ---------------------------------------------------------------------------


class TestNormalizeTimezone:
    def test_tz_naive_index_unchanged(self) -> None:
        prices = _make_prices([100.0, 101.0])
        result = normalize_timezone(prices)
        assert result.index.tz is None

    def test_tz_aware_utc_stripped(self) -> None:
        prices = _make_prices([100.0, 101.0], tz="UTC")
        result = normalize_timezone(prices)
        assert result.index.tz is None

    def test_tz_aware_new_york_converted_to_utc_naive(self) -> None:
        prices = _make_prices([100.0, 101.0], tz="America/New_York")
        result = normalize_timezone(prices)
        assert result.index.tz is None

    def test_values_preserved(self) -> None:
        prices = _make_prices([100.0, 101.0, 102.0], tz="UTC")
        result = normalize_timezone(prices)
        pd.testing.assert_series_equal(
            result.reset_index(drop=True),
            prices.reset_index(drop=True),
        )

    def test_non_datetime_index_raises(self) -> None:
        prices = pd.Series([100.0, 101.0], index=[0, 1], name="TEST")
        with pytest.raises(ValidationError, match="DatetimeIndex"):
            normalize_timezone(prices)

    def test_non_series_raises(self) -> None:
        with pytest.raises(ValidationError, match="pandas Series"):
            normalize_timezone([100.0, 101.0])  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# detect_outliers
# ---------------------------------------------------------------------------


class TestDetectOutliers:
    def test_returns_boolean_series(self, sample_prices: pd.Series) -> None:
        result = detect_outliers(sample_prices)
        assert result.dtype == bool

    def test_same_index_as_input(self, sample_prices: pd.Series) -> None:
        result = detect_outliers(sample_prices)
        pd.testing.assert_index_equal(result.index, sample_prices.index)

    def test_obvious_outlier_flagged(self) -> None:
        prices = _make_prices([100.0] * 50 + [10000.0] + [100.0] * 49)
        result = detect_outliers(prices, threshold=3.5)
        assert result.iloc[50] == True  # noqa: E712

    def test_normal_prices_not_flagged(self) -> None:
        # Tightly clustered prices — no outliers expected
        prices = _make_prices(list(range(100, 200)))
        result = detect_outliers(prices, threshold=3.5)
        assert not result.any()

    def test_constant_series_no_outliers(self) -> None:
        prices = _make_prices([100.0] * 20)
        result = detect_outliers(prices)
        assert not result.any()

    def test_single_element_no_outliers(self) -> None:
        prices = _make_prices([100.0])
        result = detect_outliers(prices)
        assert not result.any()

    def test_threshold_too_low_raises(self) -> None:
        prices = _make_prices([100.0, 101.0])
        with pytest.raises(ValidationError, match="threshold"):
            detect_outliers(prices, threshold=0.5)

    def test_threshold_too_high_raises(self) -> None:
        prices = _make_prices([100.0, 101.0])
        with pytest.raises(ValidationError, match="threshold"):
            detect_outliers(prices, threshold=200.0)

    def test_non_series_raises(self) -> None:
        with pytest.raises(ValidationError, match="pandas Series"):
            detect_outliers([100.0, 101.0])  # type: ignore[arg-type]

    def test_lower_threshold_flags_more_points(self, sample_prices: pd.Series) -> None:
        strict = detect_outliers(sample_prices, threshold=2.0)
        lenient = detect_outliers(sample_prices, threshold=5.0)
        assert strict.sum() >= lenient.sum()


# ---------------------------------------------------------------------------
# clean_prices
# ---------------------------------------------------------------------------


class TestCleanPrices:
    def test_returns_series(self, sample_prices: pd.Series) -> None:
        result = clean_prices(sample_prices)
        assert isinstance(result, pd.Series)

    def test_no_nans_in_output(self, sample_prices: pd.Series) -> None:
        noisy = sample_prices.copy()
        noisy.iloc[3] = float("nan")
        result = clean_prices(noisy)
        assert not result.isnull().any()

    def test_tz_stripped(self) -> None:
        prices = _make_prices([100.0, 101.0, 102.0], tz="UTC")
        result = clean_prices(prices)
        assert result.index.tz is None

    def test_outlier_count_in_attrs(self) -> None:
        prices = _make_prices([100.0] * 50 + [10000.0] + [100.0] * 49)
        result = clean_prices(prices, outlier_threshold=3.5)
        assert "outlier_count" in result.attrs
        assert result.attrs["outlier_count"] >= 1

    def test_outlier_count_zero_when_no_outliers(self, sample_prices: pd.Series) -> None:
        # Use a very lenient threshold so no outliers are flagged
        result = clean_prices(sample_prices, outlier_threshold=50.0)
        assert result.attrs["outlier_count"] == 0

    def test_outlier_detection_skipped_when_none(self, sample_prices: pd.Series) -> None:
        result = clean_prices(sample_prices, outlier_threshold=None)
        assert result.attrs["outlier_count"] == 0

    def test_non_series_raises(self) -> None:
        with pytest.raises(ValidationError, match="pandas Series"):
            clean_prices([100.0, 101.0])  # type: ignore[arg-type]

    def test_full_pipeline_clean_prices(self, sample_prices: pd.Series) -> None:
        tz_prices = sample_prices.copy()
        tz_prices.index = tz_prices.index.tz_localize("America/New_York")
        tz_prices.iloc[10] = float("nan")
        result = clean_prices(tz_prices)
        assert not result.isnull().any()
        assert result.index.tz is None
        assert "outlier_count" in result.attrs


# ---------------------------------------------------------------------------
# clean_dataframe (multi-ticker)
# ---------------------------------------------------------------------------


class TestCleanDataframe:
    def test_returns_dataframe(self, sample_prices_multi: pd.DataFrame) -> None:
        result = clean_dataframe(sample_prices_multi)
        assert isinstance(result, pd.DataFrame)

    def test_preserves_columns(self, sample_prices_multi: pd.DataFrame) -> None:
        result = clean_dataframe(sample_prices_multi)
        assert list(result.columns) == ["AAPL", "MSFT", "GOOGL"]

    def test_no_nans_in_output(self, sample_prices_multi: pd.DataFrame) -> None:
        result = clean_dataframe(sample_prices_multi)
        assert not result.isnull().any().any()

    def test_handles_nan_per_column(self) -> None:
        dates = pd.date_range("2023-01-01", periods=10, freq="B")
        df = pd.DataFrame(
            {
                "A": [100, 101, float("nan"), 103, 104, 105, 106, 107, 108, 109],
                "B": [200, 201, 202, 203, 204, 205, 206, 207, 208, 209],
            },
            index=dates,
            dtype=float,
        )
        result = clean_dataframe(df)
        assert not result.isnull().any().any()
        assert len(result) == 10

    def test_aligns_to_common_dates(self) -> None:
        dates_a = pd.date_range("2023-01-02", periods=5, freq="B")
        dates_b = pd.date_range("2023-01-03", periods=5, freq="B")
        df = pd.DataFrame(
            {"A": pd.Series([100, 101, 102, 103, 104], index=dates_a, dtype=float),
             "B": pd.Series([200, 201, 202, 203, 204], index=dates_b, dtype=float)},
        )
        result = clean_dataframe(df)
        # Inner join: only overlapping dates should remain
        assert not result.isnull().any().any()
        assert len(result) <= min(len(dates_a), len(dates_b))

    def test_outlier_counts_in_attrs(self, sample_prices_multi: pd.DataFrame) -> None:
        result = clean_dataframe(sample_prices_multi)
        assert "outlier_counts" in result.attrs
        assert isinstance(result.attrs["outlier_counts"], dict)

    def test_empty_dataframe(self) -> None:
        df = pd.DataFrame()
        result = clean_dataframe(df)
        assert result.empty

    def test_non_dataframe_raises(self) -> None:
        with pytest.raises(ValidationError, match="DataFrame"):
            clean_dataframe([100, 200])  # type: ignore[arg-type]

    def test_all_nan_column_excluded(self) -> None:
        dates = pd.date_range("2023-01-01", periods=5, freq="B")
        df = pd.DataFrame(
            {
                "A": [100, 101, 102, 103, 104],
                "B": [float("nan")] * 5,
            },
            index=dates,
            dtype=float,
        )
        result = clean_dataframe(df)
        assert "A" in result.columns
        assert "B" not in result.columns

    def test_mixed_timezones(self) -> None:
        dates_utc = pd.date_range("2023-01-01", periods=5, freq="B", tz="UTC")
        dates_ny = pd.date_range("2023-01-01", periods=5, freq="B", tz="America/New_York")
        df = pd.DataFrame(
            {"A": pd.Series([100, 101, 102, 103, 104], index=dates_utc, dtype=float),
             "B": pd.Series([200, 201, 202, 203, 204], index=dates_ny, dtype=float)},
        )
        result = clean_dataframe(df)
        assert result.index.tz is None
