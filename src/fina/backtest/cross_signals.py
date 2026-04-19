"""
Cross-sectional signal generators for multi-ticker portfolios.

These signals operate across the full ticker universe rather than
on a single asset in isolation:

- **Momentum rank**: long top-N performers, short bottom-N (12-1 month).
- **Pairs mean-reversion**: z-score of cointegrated spread → {-1, 0, +1}.
"""

import numpy as np
import pandas as pd
from statsmodels.tsa.stattools import coint

from fina.core.exceptions import BacktestError


# ---------------------------------------------------------------------------
# Momentum cross-sectional
# ---------------------------------------------------------------------------

def momentum_rank_signal(
    returns_df: pd.DataFrame,
    lookback: int = 252,
    skip: int = 21,
    top_n: int | None = None,
) -> pd.DataFrame:
    """
    Cross-sectional momentum: rank tickers by trailing return, overweight
    top performers, underweight bottom performers.

    For each day *t* the ranking uses cumulative returns from
    ``t - lookback`` to ``t - skip`` (the classic 12-1 month formation
    period that skips the most recent month to avoid short-term reversal).

    Args:
        returns_df: Daily returns, columns = tickers.
        lookback:   Formation window in trading days (default 252 ≈ 1 year).
        skip:       Days to skip at the end of the window (default 21 ≈ 1 month).
        top_n:      How many tickers to go long (and short).
                    Defaults to ``max(1, n_tickers // 3)``.

    Returns:
        DataFrame same shape as ``returns_df`` with weight-override values:
          - ``+1`` for top-N (long)
          - ``-1`` for bottom-N (short)
          - ``0`` for middle tickers

    Raises:
        BacktestError: If inputs are invalid or insufficient.
    """
    if returns_df.empty:
        raise BacktestError("returns_df is empty.")
    n_tickers = returns_df.shape[1]
    if n_tickers < 2:
        raise BacktestError("Momentum ranking requires at least 2 tickers.")
    if lookback <= skip:
        raise BacktestError(
            f"lookback ({lookback}) must be > skip ({skip})."
        )

    if top_n is None:
        top_n = max(1, n_tickers // 3)
    if top_n < 1 or top_n > n_tickers // 2:
        raise BacktestError(
            f"top_n ({top_n}) must be in [1, {n_tickers // 2}]."
        )

    formation = lookback - skip
    if len(returns_df) < lookback:
        raise BacktestError(
            f"Need at least {lookback} rows; got {len(returns_df)}."
        )

    # Cumulative returns over the formation window (skip most recent `skip` days)
    signals = pd.DataFrame(0.0, index=returns_df.index, columns=returns_df.columns)

    for i in range(lookback, len(returns_df)):
        window = returns_df.iloc[i - lookback : i - skip]
        cum_ret = (1.0 + window).prod() - 1.0  # per-ticker cumulative return

        ranked = cum_ret.rank(ascending=False)
        long_tickers = ranked[ranked <= top_n].index
        short_tickers = ranked[ranked > n_tickers - top_n].index

        row_label = signals.index[i]
        signals.loc[row_label, long_tickers] = 1.0
        signals.loc[row_label, short_tickers] = -1.0

    return signals


# ---------------------------------------------------------------------------
# Pairs mean-reversion
# ---------------------------------------------------------------------------

def pairs_signal(
    prices_df: pd.DataFrame,
    pair: tuple[str, str],
    lookback: int = 60,
    entry_z: float = 2.0,
    exit_z: float = 0.5,
    stop_z: float = 3.5,
) -> pd.Series:
    """
    Pairs trading signal based on cointegration and z-score of the spread.

    Steps:
      1. Test for cointegration (Engle-Granger) on the first ``lookback`` days.
      2. Estimate the hedge ratio via OLS on the formation window.
      3. Compute the spread and rolling z-score.
      4. Generate signals: enter at ±entry_z, exit at ±exit_z, stop at ±stop_z.

    Signal semantics (relative to ticker A):
      - ``+1``: long A / short B  (spread is low → expect reversion up)
      - ``-1``: short A / long B  (spread is high → expect reversion down)
      - ``0``:  flat

    Args:
        prices_df:  Price DataFrame (must contain both tickers as columns).
        pair:       Tuple of two ticker names, e.g. ``("AAPL", "MSFT")``.
        lookback:   Formation window for cointegration test and hedge ratio.
        entry_z:    Z-score threshold to enter a position.
        exit_z:     Z-score threshold to exit (reversion target).
        stop_z:     Z-score threshold for stop-loss.

    Returns:
        Series of signals {-1, 0, +1} aligned to ``prices_df.index``.

    Raises:
        BacktestError: If pair not found, not cointegrated, or insufficient data.
    """
    ticker_a, ticker_b = pair
    for t in (ticker_a, ticker_b):
        if t not in prices_df.columns:
            raise BacktestError(f"Ticker '{t}' not found in prices_df.")

    if len(prices_df) < lookback + 10:
        raise BacktestError(
            f"Need at least {lookback + 10} rows; got {len(prices_df)}."
        )

    prices_a = prices_df[ticker_a].values.astype(float)
    prices_b = prices_df[ticker_b].values.astype(float)

    # Cointegration test on formation window
    form_a = prices_a[:lookback]
    form_b = prices_b[:lookback]
    _, p_value, _ = coint(form_a, form_b)

    if p_value > 0.05:
        raise BacktestError(
            f"Pair ({ticker_a}, {ticker_b}) not cointegrated "
            f"(p={p_value:.4f} > 0.05)."
        )

    # Hedge ratio via OLS on formation window
    hedge_ratio = np.polyfit(form_b, form_a, 1)[0]

    # Spread = A - hedge_ratio * B
    spread = prices_a - hedge_ratio * prices_b

    # Rolling z-score (using expanding mean/std from formation window)
    spread_series = pd.Series(spread, index=prices_df.index)
    rolling_mean = spread_series.expanding(min_periods=lookback).mean()
    rolling_std = spread_series.expanding(min_periods=lookback).std()
    rolling_std = rolling_std.replace(0, np.nan)

    z_score = (spread_series - rolling_mean) / rolling_std

    # Generate signals with state machine
    signals = pd.Series(0.0, index=prices_df.index)
    position = 0.0

    for i in range(lookback, len(prices_df)):
        z = z_score.iloc[i]
        if np.isnan(z):
            signals.iloc[i] = position
            continue

        if position == 0.0:
            # Entry
            if z < -entry_z:
                position = 1.0   # spread is low → long A, short B
            elif z > entry_z:
                position = -1.0  # spread is high → short A, long B
        elif position == 1.0:
            # Long spread — exit or stop
            if z >= -exit_z or z < -stop_z:
                position = 0.0
        elif position == -1.0:
            # Short spread — exit or stop
            if z <= exit_z or z > stop_z:
                position = 0.0

        signals.iloc[i] = position

    return signals
