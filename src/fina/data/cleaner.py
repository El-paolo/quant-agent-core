"""
Data cleaning pipeline for raw price series fetched from external sources.

Responsibilities:
  1. NaN handling       — detect, report, and fill or drop missing values.
  2. Timezone normalization — strip or convert tz-aware indices to UTC-naive.
  3. Outlier detection  — flag statistically extreme prices using the
                          modified Z-score (median-based, robust to skew).

Security notes:
  - All parameters are validated before use; no user-supplied strings are
    ever passed to eval(), exec(), or shell commands.
  - The outlier threshold is bounded to a safe numeric range to prevent
    denial-of-service via absurdly small thresholds that would flag every
    point and allocate large intermediate structures.
"""

import numpy as np
import pandas as pd

from fina.core.exceptions import ValidationError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_THRESHOLD = 1.0    # floor: prevents flagging everything as outlier
_MAX_THRESHOLD = 100.0  # ceiling: sanity cap on modified Z-score threshold

_FILL_METHODS = frozenset({"ffill", "bfill", "linear", "drop"})


# ---------------------------------------------------------------------------
# Internal validators
# ---------------------------------------------------------------------------


def _require_series(prices: object, name: str = "prices") -> pd.Series:
    """Raise ValidationError if *prices* is not a pd.Series."""
    if not isinstance(prices, pd.Series):
        raise ValidationError(
            f"'{name}' must be a pandas Series; got {type(prices).__name__}."
        )
    return prices  # type: ignore[return-value]


def _require_fill_method(method: str) -> None:
    if method not in _FILL_METHODS:
        raise ValidationError(
            f"Invalid fill method '{method}'. "
            f"Valid options: {sorted(_FILL_METHODS)}."
        )


def _require_threshold(threshold: float) -> None:
    if not isinstance(threshold, (int, float)) or np.isnan(threshold):
        raise ValidationError("Outlier threshold must be a finite number.")
    if threshold < _MIN_THRESHOLD or threshold > _MAX_THRESHOLD:
        raise ValidationError(
            f"Outlier threshold must be between {_MIN_THRESHOLD} and "
            f"{_MAX_THRESHOLD}; got {threshold}."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def handle_nans(
    prices: pd.Series,
    method: str = "ffill",
) -> pd.Series:
    """
    Handle NaN values in a price series.

    Args:
        prices: Raw price series (may contain NaNs).
        method: How to handle NaNs.

            - ``"ffill"``   — forward-fill (carry last valid price forward).
            - ``"bfill"``   — back-fill (propagate next valid price back).
            - ``"linear"``  — linear interpolation between valid values.
            - ``"drop"``    — drop all NaN rows.

    Returns:
        Cleaned pd.Series with no NaN values.

    Raises:
        ValidationError: On invalid input type or unknown fill method.

    Notes:
        Leading NaNs cannot be forward-filled; they are always dropped to
        ensure the returned series starts with a valid value.
    """
    _require_series(prices)
    _require_fill_method(method)

    if not prices.isnull().any():
        return prices.copy()

    if method == "ffill":
        cleaned = prices.ffill()
    elif method == "bfill":
        cleaned = prices.bfill()
    elif method == "linear":
        cleaned = prices.interpolate(method="linear")
    else:  # "drop"
        cleaned = prices.dropna()

    # Drop any residual leading NaNs (e.g., ffill cannot fill a leading NaN)
    cleaned = cleaned.dropna()

    result: pd.Series = cleaned
    return result


def normalize_timezone(prices: pd.Series) -> pd.Series:
    """
    Normalize the DatetimeIndex of a price series to UTC-naive (no tzinfo).

    yfinance returns tz-aware indices (America/New_York or UTC) depending on
    the asset class.  This function converts everything to UTC then strips the
    timezone so downstream code works with plain dates consistently.

    Args:
        prices: Price series whose index may or may not be tz-aware.

    Returns:
        Price series with a UTC-naive DatetimeIndex.

    Raises:
        ValidationError: If the input is not a pd.Series or its index is not
                         a DatetimeIndex.
    """
    _require_series(prices)

    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValidationError(
            "Price series index must be a DatetimeIndex for timezone normalization."
        )

    if prices.index.tz is not None:
        normalized_index = prices.index.tz_convert("UTC").tz_localize(None)
    else:
        normalized_index = prices.index

    result: pd.Series = prices.copy()
    result.index = normalized_index
    return result


def detect_outliers(
    prices: pd.Series,
    threshold: float = 3.5,
) -> pd.Series:
    """
    Detect statistical outliers using the modified Z-score (Iglewicz & Hoaglin).

    The modified Z-score uses the median and MAD (median absolute deviation)
    instead of mean and standard deviation, making it robust to skewed
    distributions and existing outliers.

        M_i = 0.6745 * (x_i - median) / MAD

    A point is flagged when |M_i| > threshold.

    Args:
        prices:    Price series to inspect.
        threshold: Modified Z-score cutoff.  Values above this are flagged.
                   Must be in [1.0, 100.0].  Recommended: 3.5 (Iglewicz 1993).

    Returns:
        Boolean pd.Series — True where a price is an outlier, False otherwise.
        Same index as the input.

    Raises:
        ValidationError: On invalid input type or out-of-range threshold.

    References:
        Iglewicz, B. & Hoaglin, D. (1993). How to Detect and Handle Outliers.
        ASQC Quality Press, Vol. 16.
    """
    _require_series(prices)
    _require_threshold(threshold)

    if len(prices) < 2:
        return pd.Series(False, index=prices.index, dtype=bool)

    median = prices.median()
    mad = (prices - median).abs().median()

    if mad == 0:
        # MAD is zero when >50% of values are identical (e.g. 99 values at 100,
        # one at 10000).  Fall back to standard Z-score so obvious spikes are
        # still caught.
        std = prices.std()
        if std == 0:
            # Truly constant series — no outliers possible
            return pd.Series(False, index=prices.index, dtype=bool)
        z: pd.Series = (prices - prices.mean()).abs() / std
        outliers_fb: pd.Series = z > threshold
        return outliers_fb

    modified_z: pd.Series = 0.6745 * (prices - median).abs() / mad
    outliers: pd.Series = modified_z > threshold
    return outliers


def _require_dataframe(df: object, name: str = "prices") -> pd.DataFrame:
    """Raise ValidationError if *df* is not a pd.DataFrame."""
    if not isinstance(df, pd.DataFrame):
        raise ValidationError(
            f"'{name}' must be a pandas DataFrame; got {type(df).__name__}."
        )
    return df  # type: ignore[return-value]


def clean_prices(
    prices: pd.Series,
    nan_method: str = "ffill",
    outlier_threshold: float | None = 3.5,
) -> pd.Series:
    """
    Full cleaning pipeline: NaN handling → timezone normalization → outlier report.

    This is the primary entry point for the data cleaning layer.  It runs all
    cleaning steps in order and returns a clean series ready for metrics.

    Outliers are **not** removed automatically — they are logged as a warning
    via the series ``attrs`` metadata so callers can decide how to handle them.
    This is intentional: price spikes in crypto or FX can be real events.

    Args:
        prices:            Raw price series from the fetcher.
        nan_method:        NaN fill strategy (see :func:`handle_nans`).
        outlier_threshold: Modified Z-score threshold for flagging outliers.
                           Pass ``None`` to skip outlier detection.

    Returns:
        Cleaned pd.Series.  ``series.attrs["outlier_count"]`` contains the
        number of flagged outliers (0 if detection was skipped).

    Raises:
        ValidationError: On invalid inputs.
    """
    _require_series(prices)

    # Step 1 — NaN handling
    cleaned = handle_nans(prices, method=nan_method)

    # Step 2 — Timezone normalization
    cleaned = normalize_timezone(cleaned)

    # Step 3 — Outlier detection (advisory only)
    outlier_count = 0
    if outlier_threshold is not None:
        outliers = detect_outliers(cleaned, threshold=outlier_threshold)
        outlier_count = int(outliers.sum())

    result: pd.Series = cleaned
    result.attrs["outlier_count"] = outlier_count
    return result


def clean_dataframe(
    prices: pd.DataFrame,
    nan_method: str = "ffill",
    outlier_threshold: float | None = 3.5,
) -> pd.DataFrame:
    """
    Clean a multi-ticker price DataFrame by applying ``clean_prices`` per column.

    After per-column cleaning, aligns all columns to their intersection index
    (inner join on dates) so the resulting DataFrame has no NaN values.

    Args:
        prices:            DataFrame with one column per ticker, DatetimeIndex.
        nan_method:        NaN fill strategy (see :func:`handle_nans`).
        outlier_threshold: Modified Z-score threshold for outlier flagging.
                           Pass ``None`` to skip.

    Returns:
        Cleaned DataFrame with aligned DatetimeIndex. ``df.attrs["outlier_counts"]``
        contains a dict of per-ticker outlier counts.

    Raises:
        ValidationError: On invalid input type.
    """
    _require_dataframe(prices)

    if prices.empty:
        result = prices.copy()
        result.attrs["outlier_counts"] = {}
        return result

    cleaned_cols: dict[str, pd.Series] = {}
    outlier_counts: dict[str, int] = {}

    for col in prices.columns:
        series = prices[col]
        non_null_count = series.notna().sum()
        if non_null_count < 2:
            continue
        cleaned = clean_prices(
            series, nan_method=nan_method, outlier_threshold=outlier_threshold
        )
        cleaned_cols[col] = cleaned
        outlier_counts[col] = cleaned.attrs.get("outlier_count", 0)

    if not cleaned_cols:
        raise ValidationError(
            "No columns have sufficient data after cleaning."
        )

    result = pd.DataFrame(cleaned_cols)
    # Inner join: keep only dates present in ALL columns
    result = result.dropna()

    result.attrs["outlier_counts"] = outlier_counts
    return result
