"""
Strategy simulation for backtesting.

Takes a position series (from signal combination) and a price series,
simulates daily execution, and produces an equity curve + trade log.

Execution model: positions are taken at close of day t based on
signal generated at close of day t. This is the standard convention
for daily backtesting (no look-ahead bias if signals use only data ≤ t).
"""

import numpy as np
import pandas as pd

from fina.core.exceptions import BacktestError


def simulate_strategy(
    positions: pd.Series,
    test_prices: pd.Series,
    initial_capital: float = 10_000.0,
    commission_bps: float = 0.0,
    slippage_bps: float = 0.0,
) -> dict:
    """
    Simulate a trading strategy from position signals and prices.

    Args:
        positions:       Daily position sizes (float, signed). +1 = full long,
                         -1 = full short, 0 = flat. Can be fractional (GARCH sizing).
        test_prices:     Close prices over the test period (same index as positions).
        initial_capital: Starting capital in currency units.
        commission_bps:  Round-trip commission in basis points (0 = no cost).
        slippage_bps:    Slippage per trade in basis points.

    Returns:
        dict with:
          - equity_curve: pd.Series (daily portfolio value)
          - daily_returns: pd.Series (strategy daily returns)
          - positions: pd.Series (position held each day)
          - trades: list of dicts (entry_date, exit_date, direction, pnl_pct, duration_days)
          - benchmark_equity: pd.Series (buy-and-hold equity curve)
          - benchmark_returns: pd.Series (buy-and-hold daily returns)
    """
    if len(positions) == 0 or len(test_prices) == 0:
        raise BacktestError("Empty positions or prices series")

    # Align to common index
    common = positions.index.intersection(test_prices.index)
    if len(common) < 2:
        raise BacktestError("Need at least 2 common dates between positions and prices")

    pos = positions.reindex(common).fillna(0.0)
    prices = test_prices.reindex(common)

    # Daily asset returns
    asset_returns = prices.pct_change().fillna(0.0)

    # Strategy returns: position[t-1] * asset_return[t]
    # (position decided at close t-1, earns return from t-1 to t)
    shifted_pos = pos.shift(1).fillna(0.0)
    strategy_returns = shifted_pos * asset_returns

    # Transaction costs on position changes
    cost_rate = (commission_bps + slippage_bps) / 10_000
    pos_changes = pos.diff().fillna(pos.iloc[0]).abs()
    costs = pos_changes * cost_rate
    strategy_returns = strategy_returns - costs

    # Equity curve
    equity = initial_capital * (1 + strategy_returns).cumprod()
    equity.name = "strategy_equity"

    # Benchmark: buy-and-hold
    benchmark_returns = asset_returns.copy()
    benchmark_equity = initial_capital * (1 + benchmark_returns).cumprod()
    benchmark_equity.name = "benchmark_equity"

    # Extract trades (contiguous non-zero position blocks)
    trades = _extract_trades(pos, prices)

    return {
        "equity_curve": equity,
        "daily_returns": strategy_returns,
        "positions": pos,
        "trades": trades,
        "benchmark_equity": benchmark_equity,
        "benchmark_returns": benchmark_returns,
    }


def _extract_trades(positions: pd.Series, prices: pd.Series) -> list[dict]:
    """Identify individual trades from position changes."""
    trades: list[dict] = []
    in_trade = False
    entry_date = None
    entry_price = None
    direction = 0.0

    for i, (date, pos) in enumerate(positions.items()):
        price = prices.loc[date]

        if not in_trade and pos != 0:
            # Enter trade
            in_trade = True
            entry_date = date
            entry_price = price
            direction = float(np.sign(pos))

        elif in_trade and (pos == 0 or np.sign(pos) != direction):
            # Exit trade (position goes flat or reverses)
            exit_price = price
            pnl_pct = direction * (exit_price - entry_price) / entry_price
            duration = (date - entry_date).days if hasattr(date, '__sub__') else i

            trades.append({
                "entry_date": str(entry_date.date() if hasattr(entry_date, "date") else entry_date),
                "exit_date": str(date.date() if hasattr(date, "date") else date),
                "direction": "long" if direction > 0 else "short",
                "pnl_pct": round(float(pnl_pct), 6),
                "duration_days": int(duration),
            })

            # If reversing (not going flat), start a new trade immediately
            if pos != 0 and np.sign(pos) != direction:
                entry_date = date
                entry_price = price
                direction = float(np.sign(pos))
            else:
                in_trade = False
                entry_date = None
                direction = 0.0

    # Close open trade at end of period
    if in_trade and entry_date is not None:
        last_date = positions.index[-1]
        last_price = prices.iloc[-1]
        pnl_pct = direction * (last_price - entry_price) / entry_price
        duration = (last_date - entry_date).days if hasattr(last_date, '__sub__') else len(positions)
        trades.append({
            "entry_date": str(entry_date.date() if hasattr(entry_date, "date") else entry_date),
            "exit_date": str(last_date.date() if hasattr(last_date, "date") else last_date),
            "direction": "long" if direction > 0 else "short",
            "pnl_pct": round(float(pnl_pct), 6),
            "duration_days": int(duration),
        })

    return trades
