"""
Performance metrics for backtesting results.

Computes strategy and benchmark metrics from equity curves and trades.
All metrics use annualization factor of 252 trading days.
"""

import numpy as np
import pandas as pd

_TRADING_DAYS = 252


def compute_backtest_metrics(
    equity_curve: pd.Series,
    daily_returns: pd.Series,
    trades: list[dict],
    benchmark_equity: pd.Series,
    benchmark_returns: pd.Series,
    initial_capital: float = 10_000.0,
    risk_free_rate: float = 0.0,
) -> dict:
    """
    Compute comprehensive performance metrics for a backtest.

    Args:
        equity_curve:      Strategy daily equity values.
        daily_returns:     Strategy daily returns.
        trades:            List of trade dicts from simulate_strategy.
        benchmark_equity:  Buy-and-hold equity curve.
        benchmark_returns: Buy-and-hold daily returns.
        initial_capital:   Starting capital.
        risk_free_rate:    Annual risk-free rate (decimal).

    Returns:
        dict with strategy, benchmark, and relative metrics.
    """
    n_days = len(daily_returns)
    rf_daily = risk_free_rate / _TRADING_DAYS

    # ── Strategy metrics ──
    total_return = float(equity_curve.iloc[-1] / initial_capital - 1) if n_days > 0 else 0.0
    ann_factor = _TRADING_DAYS / n_days if n_days > 0 else 1.0
    annualized_return = float((1 + total_return) ** ann_factor - 1)

    vol = float(daily_returns.std() * np.sqrt(_TRADING_DAYS)) if n_days > 1 else 0.0

    # Sharpe
    excess = daily_returns - rf_daily
    sharpe = float(excess.mean() / excess.std() * np.sqrt(_TRADING_DAYS)) if excess.std() > 0 else 0.0

    # Sortino (downside deviation)
    downside = excess[excess < 0]
    downside_std = float(np.sqrt(np.mean(downside ** 2))) if len(downside) > 0 else 0.0
    sortino = float(excess.mean() / downside_std * np.sqrt(_TRADING_DAYS)) if downside_std > 0 else 0.0

    # Max drawdown
    cummax = equity_curve.cummax()
    drawdown = (equity_curve - cummax) / cummax
    max_dd = float(drawdown.min()) if len(drawdown) > 0 else 0.0

    # Max drawdown duration (in trading days)
    dd_duration = _max_drawdown_duration(equity_curve)

    # Calmar ratio
    calmar = float(annualized_return / abs(max_dd)) if max_dd != 0 else 0.0

    # Trade metrics
    trade_returns = [t["pnl_pct"] for t in trades]
    winning = [r for r in trade_returns if r > 0]
    win_rate = float(len(winning) / len(trade_returns)) if trade_returns else 0.0
    avg_trade_return = float(np.mean(trade_returns)) if trade_returns else 0.0
    avg_trade_duration = (
        float(np.mean([t["duration_days"] for t in trades])) if trades else 0.0
    )

    # ── Benchmark metrics ──
    bm_total = float(benchmark_equity.iloc[-1] / initial_capital - 1) if n_days > 0 else 0.0
    bm_ann = float((1 + bm_total) ** ann_factor - 1)
    bm_excess = benchmark_returns - rf_daily
    bm_sharpe = (
        float(bm_excess.mean() / bm_excess.std() * np.sqrt(_TRADING_DAYS))
        if bm_excess.std() > 0 else 0.0
    )
    bm_cummax = benchmark_equity.cummax()
    bm_dd = (benchmark_equity - bm_cummax) / bm_cummax
    bm_max_dd = float(bm_dd.min()) if len(bm_dd) > 0 else 0.0

    # ── Relative metrics ──
    excess_return = total_return - bm_total
    tracking_error = float((daily_returns - benchmark_returns).std() * np.sqrt(_TRADING_DAYS))
    information_ratio = float(excess_return / tracking_error) if tracking_error > 0 else 0.0

    return {
        "strategy": {
            "total_return": round(total_return, 6),
            "annualized_return": round(annualized_return, 6),
            "volatility": round(vol, 6),
            "sharpe_ratio": round(sharpe, 4),
            "sortino_ratio": round(sortino, 4),
            "max_drawdown": round(max_dd, 6),
            "max_drawdown_duration_days": dd_duration,
            "calmar_ratio": round(calmar, 4),
            "win_rate": round(win_rate, 4),
            "avg_trade_return": round(avg_trade_return, 6),
            "avg_trade_duration_days": round(avg_trade_duration, 1),
            "total_trades": len(trades),
        },
        "benchmark": {
            "total_return": round(bm_total, 6),
            "annualized_return": round(bm_ann, 6),
            "sharpe_ratio": round(bm_sharpe, 4),
            "max_drawdown": round(bm_max_dd, 6),
        },
        "relative": {
            "excess_return": round(excess_return, 6),
            "information_ratio": round(information_ratio, 4),
        },
    }


def _max_drawdown_duration(equity: pd.Series) -> int:
    """Longest streak (in trading days) below the running maximum."""
    cummax = equity.cummax()
    is_dd = equity < cummax
    if not is_dd.any():
        return 0

    # Find contiguous blocks of drawdown
    groups = (~is_dd).cumsum()
    dd_groups = groups[is_dd]
    if len(dd_groups) == 0:
        return 0
    return int(dd_groups.value_counts().max())
