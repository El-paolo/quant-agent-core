"""
Backtest engine — top-level orchestrator.

Ties together data fetching, signal generation, strategy simulation,
and performance metrics into a single pipeline.

Usage:
    result = run_backtest("AAPL", "2022-01-01", "2023-12-31", "2024-01-01", "2024-06-30")
"""

from datetime import date

import pandas as pd

from fina.core.exceptions import BacktestError, FetcherError
from fina.data.cleaner import clean_prices
from fina.data.fetcher import fetch_close_prices
from fina.metrics.returns import compute_returns

from fina.backtest.metrics import compute_backtest_metrics
from fina.backtest.signals import (
    combine_signals,
    generate_arima_signals,
    generate_garch_sizing,
    generate_hmm_signals,
)
from fina.backtest.strategy import simulate_strategy

_VALID_MODELS = {"arima", "hmm", "garch"}


def run_backtest(
    ticker: str,
    train_start: str,
    train_end: str,
    test_start: str,
    test_end: str,
    models: list[str] | None = None,
    initial_capital: float = 10_000.0,
    arima_threshold: float = 0.0,
    hmm_states: int = 3,
    garch_target_vol: float | None = None,
    commission_bps: float = 0.0,
) -> dict:
    """
    Run a complete backtest pipeline.

    1. Fetch prices for full range (train_start → test_end)
    2. Split into train/test by dates
    3. Generate signals per model
    4. Combine signals → positions
    5. Simulate strategy
    6. Compute metrics vs buy-and-hold

    Args:
        ticker:          Stock ticker symbol.
        train_start:     Training period start (YYYY-MM-DD).
        train_end:       Training period end (YYYY-MM-DD).
        test_start:      Test period start (YYYY-MM-DD).
        test_end:        Test period end (YYYY-MM-DD).
        models:          Which models to use (subset of {arima, hmm, garch}).
        initial_capital: Starting capital.
        arima_threshold: Min absolute prediction to trigger ARIMA signal.
        hmm_states:      Number of HMM states (2 or 3).
        garch_target_vol: Target vol for GARCH sizing (None = auto).
        commission_bps:  Round-trip commission in basis points.

    Returns:
        dict with train/test periods, signal summaries, strategy results,
        equity curves, trades, metrics, and warnings.

    Raises:
        BacktestError: On invalid inputs or insufficient data.
        FetcherError: On data fetching failures.
    """
    if models is None:
        models = ["arima", "hmm", "garch"]

    unknown = set(models) - _VALID_MODELS
    if unknown:
        raise BacktestError(f"Unknown models: {unknown}")

    # ── Validate dates ──
    try:
        d_train_start = date.fromisoformat(train_start)
        d_train_end = date.fromisoformat(train_end)
        d_test_start = date.fromisoformat(test_start)
        d_test_end = date.fromisoformat(test_end)
    except ValueError as exc:
        raise BacktestError(f"Invalid date format (use YYYY-MM-DD): {exc}") from exc

    if d_train_end >= d_test_start:
        raise BacktestError(
            f"Train end ({train_end}) must be before test start ({test_start})"
        )
    if d_train_start >= d_train_end:
        raise BacktestError("Train start must be before train end")
    if d_test_start >= d_test_end:
        raise BacktestError("Test start must be before test end")

    # ── Fetch & prepare data ──
    prices = fetch_close_prices(ticker, start=train_start, end=test_end)
    prices = clean_prices(prices)

    if len(prices) < 10:
        raise BacktestError(f"Insufficient price data: {len(prices)} points")

    returns_result = compute_returns(prices, method="log")
    returns_series = returns_result["returns"]

    # ── Split by dates ──
    train_returns = returns_series[returns_series.index <= str(d_train_end)]
    test_returns = returns_series[returns_series.index >= str(d_test_start)]
    train_prices = prices[prices.index <= str(d_train_end)]
    test_prices = prices[prices.index >= str(d_test_start)]

    if len(train_returns) < 30:
        raise BacktestError(
            f"Train period too short: {len(train_returns)} trading days"
        )
    if len(test_returns) < 2:
        raise BacktestError(
            f"Test period too short: {len(test_returns)} trading days"
        )

    # Actual date ranges (may differ from requested due to trading days)
    actual_train = {
        "start": _date_str(train_returns.index[0]),
        "end": _date_str(train_returns.index[-1]),
        "trading_days": len(train_returns),
    }
    actual_test = {
        "start": _date_str(test_returns.index[0]),
        "end": _date_str(test_returns.index[-1]),
        "trading_days": len(test_returns),
    }

    # ── Run pipeline ──
    pipeline = _run_single_ticker_pipeline(
        train_returns=train_returns,
        test_returns=test_returns,
        test_prices=test_prices,
        models=models,
        initial_capital=initial_capital,
        arima_threshold=arima_threshold,
        hmm_states=hmm_states,
        garch_target_vol=garch_target_vol,
        commission_bps=commission_bps,
    )

    # ── Serialize timeseries for JSON response ──
    sim = pipeline["simulation"]
    equity_list = [
        {"date": _date_str(idx), "value": round(float(v), 2)}
        for idx, v in sim["equity_curve"].items()
    ]
    benchmark_list = [
        {"date": _date_str(idx), "value": round(float(v), 2)}
        for idx, v in sim["benchmark_equity"].items()
    ]
    positions_list = [
        {"date": _date_str(idx), "value": round(float(v), 4)}
        for idx, v in sim["positions"].items()
    ]

    return {
        "ticker": ticker,
        "train_period": actual_train,
        "test_period": actual_test,
        "models_used": models,
        "signals": pipeline["signal_summaries"],
        "metrics": pipeline["metrics"],
        "equity_curve": equity_list,
        "benchmark_curve": benchmark_list,
        "positions": positions_list,
        "trades": sim["trades"],
        "warnings": pipeline["warnings"],
    }


def _run_single_ticker_pipeline(
    train_returns: pd.Series,
    test_returns: pd.Series,
    test_prices: pd.Series,
    models: list[str],
    initial_capital: float = 10_000.0,
    arima_threshold: float = 0.0,
    hmm_states: int = 3,
    garch_target_vol: float | None = None,
    commission_bps: float = 0.0,
) -> dict:
    """
    Core single-ticker backtest pipeline: signals → combine → simulate → metrics.

    This is the reusable inner loop extracted from ``run_backtest``.
    The portfolio engine calls this per ticker.

    Args:
        train_returns: Return series for the training period.
        test_returns:  Return series for the test period.
        test_prices:   Price series for the test period.
        models:        Which models to use.
        initial_capital: Starting capital for simulation.
        arima_threshold: ARIMA signal threshold.
        hmm_states:    HMM state count.
        garch_target_vol: GARCH vol target.
        commission_bps: Commission in basis points.

    Returns:
        dict with keys: signal_summaries, simulation, metrics, warnings.

    Raises:
        BacktestError: If all models fail.
    """
    warnings_list: list[str] = []
    signal_summaries: dict = {}
    arima_sig = None
    hmm_sig = None
    garch_siz = None

    if "arima" in models:
        try:
            arima_result = generate_arima_signals(
                train_returns, test_returns,
                threshold=arima_threshold,
            )
            arima_sig = arima_result["signals"]
            warnings_list.extend(arima_result["warnings"])
            if arima_sig is not None:
                signal_summaries["arima"] = {
                    "order": list(arima_result["order"]),
                    "long_days": int((arima_sig == 1).sum()),
                    "short_days": int((arima_sig == -1).sum()),
                    "hold_days": int((arima_sig == 0).sum()),
                }
            else:
                signal_summaries["arima"] = {
                    "order": list(arima_result["order"]),
                    "long_days": 0,
                    "short_days": 0,
                    "hold_days": len(test_returns),
                    "note": "ARIMA(0,0,0): sin señal direccional",
                }
        except BacktestError as exc:
            warnings_list.append(f"ARIMA: {exc}")
            signal_summaries["arima"] = None

    if "hmm" in models:
        try:
            hmm_result = generate_hmm_signals(
                train_returns, test_returns,
                n_states=hmm_states,
            )
            hmm_sig = hmm_result["signals"]
            warnings_list.extend(hmm_result["warnings"])
            regimes = hmm_result["regimes"]
            signal_summaries["hmm"] = {
                "regime_distribution": {
                    k: int(v)
                    for k, v in regimes.value_counts().items()
                },
                "long_days": int((hmm_sig == 1).sum()),
                "hold_days": int((hmm_sig == 0).sum()),
                "risk_off_days": int((hmm_sig == -1).sum()),
            }
        except BacktestError as exc:
            warnings_list.append(f"HMM: {exc}")
            signal_summaries["hmm"] = None

    if "garch" in models:
        try:
            garch_result = generate_garch_sizing(
                train_returns, test_returns,
                target_vol=garch_target_vol,
            )
            garch_siz = garch_result["sizing"]
            warnings_list.extend(garch_result["warnings"])
            signal_summaries["garch"] = {
                "target_vol": round(garch_result["target_vol"], 6),
                "avg_sizing": round(float(garch_siz.mean()), 4),
                "min_sizing": round(float(garch_siz.min()), 4),
                "max_sizing": round(float(garch_siz.max()), 4),
            }
        except BacktestError as exc:
            warnings_list.append(f"GARCH: {exc}")
            signal_summaries["garch"] = None

    if arima_sig is None and hmm_sig is None and garch_siz is None:
        raise BacktestError(
            "All models failed — cannot generate signals. " +
            "; ".join(warnings_list)
        )

    positions = combine_signals(arima_sig, hmm_sig, garch_siz)

    sim = simulate_strategy(
        positions, test_prices,
        initial_capital=initial_capital,
        commission_bps=commission_bps,
    )

    metrics = compute_backtest_metrics(
        equity_curve=sim["equity_curve"],
        daily_returns=sim["daily_returns"],
        trades=sim["trades"],
        benchmark_equity=sim["benchmark_equity"],
        benchmark_returns=sim["benchmark_returns"],
        initial_capital=initial_capital,
    )

    return {
        "signal_summaries": signal_summaries,
        "simulation": sim,
        "metrics": metrics,
        "warnings": warnings_list,
    }


def _date_str(idx) -> str:
    """Convert a pandas Timestamp or similar to YYYY-MM-DD string."""
    return str(idx.date() if hasattr(idx, "date") else idx)
