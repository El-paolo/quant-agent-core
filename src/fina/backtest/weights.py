"""
Portfolio weight schemes for multi-ticker backtesting.

All functions return normalized weight arrays that sum to 1.0.
"""

import numpy as np
import pandas as pd

from fina.core.exceptions import BacktestError

_TRADING_DAYS = 252


def equal_weight(n: int) -> list[float]:
    """Equal weight allocation across *n* assets."""
    if n < 1:
        raise BacktestError("Need at least 1 asset for weighting.")
    w = 1.0 / n
    return [w] * n


def inverse_vol_weight(
    returns_df: pd.DataFrame,
    lookback: int = 63,
) -> list[float]:
    """
    Inverse-volatility weighting: assets with lower vol get higher weight.

    Args:
        returns_df: DataFrame of daily returns, one column per asset.
        lookback:   Number of trailing days to estimate volatility.
                    Uses all data if fewer rows are available.

    Returns:
        List of normalized weights in column order.
    """
    if returns_df.empty or returns_df.shape[1] < 1:
        raise BacktestError("returns_df must have at least 1 column.")

    tail = returns_df.tail(lookback)
    vols = tail.std()

    # Replace zero-vol assets with a small value to avoid inf weights
    vols = vols.replace(0.0, np.nan).fillna(vols[vols > 0].min() * 0.1)

    if (vols <= 0).all():
        return equal_weight(len(vols))

    inv_vol = 1.0 / vols
    normalized = inv_vol / inv_vol.sum()
    return [round(float(w), 6) for w in normalized]


def custom_weight(weights: list[float]) -> list[float]:
    """
    Normalize custom user-provided weights to sum to 1.0.

    Args:
        weights: Raw weight values (any positive scale).

    Returns:
        Normalized weights summing to 1.0.
    """
    if not weights:
        raise BacktestError("Weights list must not be empty.")

    arr = np.array(weights, dtype=float)

    if (arr < 0).any():
        raise BacktestError("Weights must be non-negative.")

    total = arr.sum()
    if total <= 0:
        raise BacktestError("Weights must sum to a positive value.")

    normalized = arr / total
    return [round(float(w), 6) for w in normalized]
