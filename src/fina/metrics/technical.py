"""
Technical indicators: RSI, MACD, Bollinger Bands.

Implemented directly with pandas/numpy — no external indicator library required.
This avoids the numpy version conflict introduced by pandas-ta's numba dependency.

Formula reference:
  RSI     = 100 - 100 / (1 + RS)
              where RS = avg_gain / avg_loss  (Wilder smoothing)
  MACD    = EMA(fast) - EMA(slow)
  Signal  = EMA(MACD, signal_window)
  Histogram = MACD - Signal
  BB_mid  = SMA(window)
  BB_up   = BB_mid + std_dev * rolling_std(window)
  BB_low  = BB_mid - std_dev * rolling_std(window)
  %B      = (price - BB_low) / (BB_up - BB_low)
  BW      = (BB_up - BB_low) / BB_mid

Security notes:
  - No external data fetched; all inputs are validated before computation.
  - Numeric parameters are bounded to prevent degenerate results.
"""

import numpy as np
import pandas as pd

from fina.core.exceptions import MetricsError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MIN_WINDOW = 2


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_prices(prices: object, min_len: int, name: str = "prices") -> pd.Series:
    if not isinstance(prices, pd.Series):
        raise MetricsError(
            f"'{name}' must be a pandas Series; got {type(prices).__name__}."
        )
    if prices.isnull().any():
        raise MetricsError(
            f"'{name}' contains NaN values. Clean data before computing indicators."
        )
    if len(prices) < min_len:
        raise MetricsError(
            f"At least {min_len} price observations are required; got {len(prices)}."
        )
    result: pd.Series = prices
    return result


def _validate_window(window: int, param_name: str = "window") -> None:
    if not isinstance(window, int) or window < _MIN_WINDOW:
        raise MetricsError(
            f"'{param_name}' must be an integer >= {_MIN_WINDOW}; got {window!r}."
        )


def _validate_positive_float(value: float, name: str) -> None:
    if not isinstance(value, (int, float)) or np.isnan(value) or value <= 0:
        raise MetricsError(
            f"'{name}' must be a positive finite number; got {value!r}."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_rsi(
    prices: pd.Series,
    window: int = 14,
) -> pd.Series:
    """
    Compute the Relative Strength Index (RSI) for a price series.

    Uses Wilder's smoothing (exponential moving average with alpha=1/window),
    which is the standard RSI definition (Wilder, 1978).

    Args:
        prices: Price series (must be sorted chronologically, no NaNs).
        window: Look-back period.  Default: 14 (Wilder's original).

    Returns:
        pd.Series of RSI values on [0, 100], with leading NaNs dropped.
        Named ``"RSI_{window}"``.

    Raises:
        MetricsError: On invalid input type, NaN values, or insufficient data.
    """
    _validate_window(window)
    min_len = window + 1
    prices = _validate_prices(prices, min_len=min_len)

    delta: pd.Series = prices.diff()

    gain: pd.Series = delta.clip(lower=0.0)
    loss: pd.Series = (-delta).clip(lower=0.0)

    # Wilder smoothing = EMA with com = window - 1  (alpha = 1/window)
    avg_gain: pd.Series = gain.ewm(com=window - 1, min_periods=window).mean()
    avg_loss: pd.Series = loss.ewm(com=window - 1, min_periods=window).mean()

    rs: pd.Series = avg_gain / avg_loss.replace(0, np.nan)
    rsi: pd.Series = 100.0 - (100.0 / (1.0 + rs))

    result: pd.Series = rsi.dropna().rename(f"RSI_{window}")
    return result


def compute_macd(
    prices: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """
    Compute the MACD indicator (Moving Average Convergence/Divergence).

    Args:
        prices: Price series (chronological, no NaNs).
        fast:   Fast EMA period.   Default: 12.
        slow:   Slow EMA period.   Default: 26.
        signal: Signal EMA period. Default: 9.

    Returns:
        pd.DataFrame with columns ``["macd", "signal", "histogram"]``.
        Leading NaNs (warm-up period) are dropped.
        ``histogram == macd - signal`` for all rows.

    Raises:
        MetricsError: On invalid inputs, ``fast >= slow``, or insufficient data.
    """
    _validate_window(fast, "fast")
    _validate_window(slow, "slow")
    _validate_window(signal, "signal")

    if fast >= slow:
        raise MetricsError(
            f"'fast' ({fast}) must be strictly less than 'slow' ({slow})."
        )

    min_len = slow + signal
    prices = _validate_prices(prices, min_len=min_len)

    ema_fast: pd.Series = prices.ewm(span=fast, adjust=False).mean()
    ema_slow: pd.Series = prices.ewm(span=slow, adjust=False).mean()

    macd_line: pd.Series = ema_fast - ema_slow
    signal_line: pd.Series = macd_line.ewm(span=signal, adjust=False).mean()
    histogram: pd.Series = macd_line - signal_line

    df = pd.DataFrame(
        {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram,
        }
    )

    result: pd.DataFrame = df.dropna()
    return result


def compute_bollinger_bands(
    prices: pd.Series,
    window: int = 20,
    std_dev: float = 2.0,
) -> pd.DataFrame:
    """
    Compute Bollinger Bands for a price series (Bollinger, 1983).

    Args:
        prices:  Price series (chronological, no NaNs).
        window:  Rolling window for the SMA and standard deviation. Default: 20.
        std_dev: Number of standard deviations for the bands. Default: 2.0.

    Returns:
        pd.DataFrame with columns:

          - ``"upper"``      — upper band  (SMA + std_dev * σ)
          - ``"middle"``     — middle band (SMA)
          - ``"lower"``      — lower band  (SMA - std_dev * σ)
          - ``"bandwidth"``  — (upper - lower) / middle — measures band width
          - ``"percent_b"``  — (price - lower) / (upper - lower)
                               0 = at lower band, 1 = at upper band

        Leading NaN rows (warm-up) are dropped.

    Raises:
        MetricsError: On invalid types, non-positive std_dev, or insufficient data.
    """
    _validate_window(window)
    _validate_positive_float(std_dev, "std_dev")

    prices = _validate_prices(prices, min_len=window)

    sma: pd.Series = prices.rolling(window=window).mean()
    rolling_std: pd.Series = prices.rolling(window=window).std()

    upper: pd.Series = sma + std_dev * rolling_std
    lower: pd.Series = sma - std_dev * rolling_std

    bandwidth: pd.Series = (upper - lower) / sma
    percent_b: pd.Series = (prices - lower) / (upper - lower)

    df = pd.DataFrame(
        {
            "upper": upper,
            "middle": sma,
            "lower": lower,
            "bandwidth": bandwidth,
            "percent_b": percent_b,
        }
    )

    result: pd.DataFrame = df.dropna()
    return result
