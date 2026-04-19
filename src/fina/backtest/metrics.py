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
    losing = [r for r in trade_returns if r < 0]
    win_rate = float(len(winning) / len(trade_returns)) if trade_returns else 0.0
    avg_trade_return = float(np.mean(trade_returns)) if trade_returns else 0.0
    avg_trade_duration = (
        float(np.mean([t["duration_days"] for t in trades])) if trades else 0.0
    )

    # Profit factor: gross profit / gross loss
    gross_profit = sum(winning) if winning else 0.0
    gross_loss = abs(sum(losing)) if losing else 0.0
    profit_factor = (
        float(gross_profit / gross_loss) if gross_loss > 0
        else (float("inf") if gross_profit > 0 else 0.0)
    )

    # Average win/loss ratio
    avg_win = float(np.mean(winning)) if winning else 0.0
    avg_loss = float(abs(np.mean(losing))) if losing else 0.0
    avg_win_loss_ratio = float(avg_win / avg_loss) if avg_loss > 0 else 0.0

    # Kelly fraction (simplified): f* = W - (1-W)/R, clamped [0, 1]
    if avg_win_loss_ratio > 0 and win_rate > 0:
        kelly = win_rate - (1.0 - win_rate) / avg_win_loss_ratio
        kelly_fraction = float(max(0.0, min(1.0, kelly)))
    else:
        kelly_fraction = 0.0

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
            "profit_factor": round(profit_factor, 4) if profit_factor != float("inf") else "inf",
            "avg_win_loss_ratio": round(avg_win_loss_ratio, 4),
            "kelly_fraction": round(kelly_fraction, 4),
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


def compute_portfolio_metrics(
    portfolio_returns: pd.Series,
    per_asset_returns: pd.DataFrame,
    weights: list[float],
    n_trials: int = 1,
) -> dict:
    """
    Compute portfolio-level risk metrics.

    Args:
        portfolio_returns: Daily returns of the combined portfolio.
        per_asset_returns:  DataFrame of per-asset daily returns.
        weights:            Portfolio weights (same order as DataFrame columns).
        n_trials:           Number of strategy configurations tested (for DSR).

    Returns:
        dict with VaR, CVaR, effective N, DSR, and correlation matrix.
    """
    from fina.backtest.dsr import deflated_sharpe_ratio
    from scipy.stats import skew, kurtosis as kurt_func

    n = len(portfolio_returns)

    # VaR / CVaR at 95%
    sorted_rets = np.sort(portfolio_returns.values)
    cutoff_idx = max(1, int(0.05 * n))
    var_95 = float(-sorted_rets[cutoff_idx - 1])
    cvar_95 = float(-sorted_rets[:cutoff_idx].mean()) if cutoff_idx > 0 else var_95

    # Annualized portfolio Sharpe
    mean_r = float(portfolio_returns.mean())
    vol = float(portfolio_returns.std())
    port_sharpe = float(mean_r / vol * np.sqrt(_TRADING_DAYS)) if vol > 0 else 0.0

    # DSR
    sk = float(skew(portfolio_returns.values)) if n > 2 else 0.0
    kt = float(kurt_func(portfolio_returns.values, fisher=False)) if n > 2 else 3.0
    dsr_result = deflated_sharpe_ratio(
        observed_sr=port_sharpe,
        n_trials=n_trials,
        n_obs=n,
        skewness=sk,
        kurtosis=kt,
    )

    # Effective N (diversification metric)
    # effective_n = 1 / sum(w_i^2) — measures how many independent bets
    w = np.array(weights)
    effective_n = float(1.0 / (w ** 2).sum()) if (w ** 2).sum() > 0 else 0.0

    # Correlation matrix
    corr = per_asset_returns.corr()
    corr_dict = {
        col: {row: round(corr.loc[row, col], 4) for row in corr.index}
        for col in corr.columns
    }

    return {
        "var_95": round(var_95, 6),
        "cvar_95": round(cvar_95, 6),
        "portfolio_sharpe": round(port_sharpe, 4),
        "effective_n": round(effective_n, 2),
        "dsr": dsr_result,
        "correlation_matrix": corr_dict,
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
