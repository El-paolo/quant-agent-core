"""
Portfolio backtest engine — multi-ticker orchestrator.

Runs the single-ticker pipeline per asset, combines equity curves
using portfolio weights, and computes portfolio-level metrics.
"""

from datetime import date

import numpy as np
import pandas as pd

from fina.core.exceptions import BacktestError, FetcherError
from fina.data.cleaner import clean_dataframe
from fina.data.fetcher import fetch_universe
from fina.metrics.returns import compute_returns

from fina.backtest.cross_signals import momentum_rank_signal, pairs_signal
from fina.backtest.engine import _run_single_ticker_pipeline, _date_str
from fina.backtest.metrics import compute_portfolio_metrics
from fina.backtest.weights import equal_weight, inverse_vol_weight, custom_weight

_VALID_MODELS = {"arima", "hmm", "garch"}
_VALID_WEIGHT_SCHEMES = {"equal", "inverse_vol", "custom"}
_VALID_CROSS_SIGNALS = {"momentum", "pairs", None}


def run_portfolio_backtest(
    tickers: list[str],
    train_start: str,
    train_end: str,
    test_start: str,
    test_end: str,
    models: list[str] | None = None,
    weight_scheme: str = "equal",
    custom_weights: list[float] | None = None,
    cross_signal: str | None = None,
    cross_signal_params: dict | None = None,
    initial_capital: float = 10_000.0,
    arima_threshold: float = 0.0,
    hmm_states: int = 3,
    garch_target_vol: float | None = None,
    commission_bps: float = 0.0,
    n_trials: int = 1,
) -> dict:
    """
    Run a portfolio backtest across multiple tickers.

    1. Fetch prices for all tickers
    2. Split into train/test by dates
    3. Run single-ticker pipeline per asset
    4. Combine equity curves using weights
    5. Compute portfolio-level metrics (VaR, CVaR, DSR, effective N)

    Args:
        tickers:         List of ticker symbols.
        train_start:     Training period start (YYYY-MM-DD).
        train_end:       Training period end.
        test_start:      Test period start.
        test_end:        Test period end.
        models:          Models to use (subset of {arima, hmm, garch}).
        weight_scheme:   "equal", "inverse_vol", or "custom".
        custom_weights:  Required when weight_scheme="custom".
        cross_signal:    Cross-sectional signal: "momentum", "pairs", or None.
        cross_signal_params: Extra params for the cross signal generator.
        initial_capital: Total starting capital.
        arima_threshold: ARIMA signal threshold.
        hmm_states:      HMM state count.
        garch_target_vol: GARCH vol target.
        commission_bps:  Commission in basis points.
        n_trials:        Strategy trials tested (for DSR).

    Returns:
        dict with portfolio metrics, per-asset results, equity curves, weights.

    Raises:
        BacktestError: On invalid inputs or insufficient data.
        FetcherError: On data fetching failures.
    """
    if not tickers or len(tickers) < 2:
        raise BacktestError("Portfolio backtest requires at least 2 tickers.")

    if models is None:
        models = ["arima", "hmm", "garch"]

    unknown = set(models) - _VALID_MODELS
    if unknown:
        raise BacktestError(f"Unknown models: {unknown}")

    if weight_scheme not in _VALID_WEIGHT_SCHEMES:
        raise BacktestError(
            f"Unknown weight scheme '{weight_scheme}'. "
            f"Valid: {sorted(_VALID_WEIGHT_SCHEMES)}"
        )

    if cross_signal not in _VALID_CROSS_SIGNALS:
        raise BacktestError(
            f"Unknown cross_signal '{cross_signal}'. "
            f"Valid: {sorted(s for s in _VALID_CROSS_SIGNALS if s)}"
        )

    if cross_signal == "pairs" and len(tickers) != 2:
        raise BacktestError("Pairs signal requires exactly 2 tickers.")

    if cross_signal_params is None:
        cross_signal_params = {}

    if weight_scheme == "custom":
        if custom_weights is None:
            raise BacktestError("custom_weights required when weight_scheme='custom'.")
        if len(custom_weights) != len(tickers):
            raise BacktestError(
                f"custom_weights length ({len(custom_weights)}) "
                f"must match tickers length ({len(tickers)})."
            )

    # ── Validate dates ──
    try:
        d_train_start = date.fromisoformat(train_start)
        d_train_end = date.fromisoformat(train_end)
        d_test_start = date.fromisoformat(test_start)
        d_test_end = date.fromisoformat(test_end)
    except ValueError as exc:
        raise BacktestError(f"Invalid date format: {exc}") from exc

    if d_train_end >= d_test_start:
        raise BacktestError("Train end must be before test start.")
    if d_train_start >= d_train_end:
        raise BacktestError("Train start must be before train end.")
    if d_test_start >= d_test_end:
        raise BacktestError("Test start must be before test end.")

    # ── Fetch & prepare data ──
    prices_df = fetch_universe(tickers, start=train_start, end=test_end)
    prices_df = clean_dataframe(prices_df)

    fetch_warnings = prices_df.attrs.get("warnings", [])
    active_tickers = list(prices_df.columns)

    if len(active_tickers) < 2:
        raise BacktestError(
            f"Only {len(active_tickers)} tickers available after fetch. "
            "Portfolio requires at least 2."
        )

    # ── Compute weights ──
    # Compute returns for weight calculation
    train_prices_df = prices_df[prices_df.index <= str(d_train_end)]

    if weight_scheme == "equal":
        weights = equal_weight(len(active_tickers))
    elif weight_scheme == "inverse_vol":
        train_rets_df = train_prices_df.pct_change().dropna()
        weights = inverse_vol_weight(train_rets_df)
    else:  # custom
        # Re-index custom weights to match active tickers
        ticker_idx = {t: i for i, t in enumerate(tickers)}
        weights = custom_weight([custom_weights[ticker_idx[t]] for t in active_tickers])

    # ── Per-asset pipeline ──
    per_asset_results: dict[str, dict] = {}
    all_warnings: list[str] = list(fetch_warnings)
    per_asset_equity: dict[str, pd.Series] = {}
    per_asset_daily_returns: dict[str, pd.Series] = {}

    for ticker in active_tickers:
        prices = prices_df[ticker].dropna()
        returns_result = compute_returns(prices, method="log")
        returns_series = returns_result["returns"]

        train_returns = returns_series[returns_series.index <= str(d_train_end)]
        test_returns = returns_series[returns_series.index >= str(d_test_start)]
        test_prices = prices[prices.index >= str(d_test_start)]

        if len(train_returns) < 30 or len(test_returns) < 2:
            all_warnings.append(f"{ticker}: insufficient data, skipped.")
            continue

        try:
            result = _run_single_ticker_pipeline(
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
            per_asset_results[ticker] = result
            per_asset_equity[ticker] = result["simulation"]["equity_curve"]
            per_asset_daily_returns[ticker] = result["simulation"]["daily_returns"]
            all_warnings.extend(
                f"{ticker}: {w}" for w in result["warnings"]
            )
        except BacktestError as exc:
            all_warnings.append(f"{ticker}: {exc}")

    if len(per_asset_results) < 2:
        raise BacktestError(
            f"Only {len(per_asset_results)} tickers succeeded. "
            "Portfolio requires at least 2."
        )

    # Re-normalize weights to active tickers only
    success_tickers = list(per_asset_results.keys())
    success_indices = [active_tickers.index(t) for t in success_tickers]
    active_weights_raw = [weights[i] for i in success_indices]
    total_w = sum(active_weights_raw)
    active_weights = [w / total_w for w in active_weights_raw]

    # ── Cross-sectional signals (dynamic weight overrides) ──
    cross_weight_df = None
    cross_summary: dict | None = None

    if cross_signal == "momentum":
        try:
            test_returns_df = pd.DataFrame(per_asset_daily_returns)
            # Need full returns (train + test) for lookback
            full_returns_df = prices_df[success_tickers].pct_change().dropna()
            mom_signals = momentum_rank_signal(full_returns_df, **cross_signal_params)
            # Keep only test-period rows
            cross_weight_df = mom_signals.loc[test_returns_df.index]
            cross_summary = {
                "type": "momentum",
                "lookback": cross_signal_params.get("lookback", 252),
                "skip": cross_signal_params.get("skip", 21),
                "top_n": cross_signal_params.get(
                    "top_n", max(1, len(success_tickers) // 3)
                ),
            }
        except BacktestError as exc:
            all_warnings.append(f"Momentum signal: {exc}")

    elif cross_signal == "pairs":
        try:
            pair = (success_tickers[0], success_tickers[1])
            full_prices = prices_df[list(pair)]
            pair_sig = pairs_signal(full_prices, pair=pair, **cross_signal_params)
            # Convert scalar signal to per-ticker weight override
            # +1 → long A / short B; -1 → short A / long B
            test_idx = per_asset_daily_returns[success_tickers[0]].index
            pair_sig_test = pair_sig.loc[test_idx]
            cross_weight_df = pd.DataFrame({
                success_tickers[0]: pair_sig_test,
                success_tickers[1]: -pair_sig_test,
            })
            cross_summary = {"type": "pairs", "pair": list(pair)}
        except BacktestError as exc:
            all_warnings.append(f"Pairs signal: {exc}")

    # ── Combine equity curves ──
    equity_df = pd.DataFrame(per_asset_equity)
    # Normalize each equity to start at weight * capital
    for i, ticker in enumerate(success_tickers):
        scale = active_weights[i] * initial_capital / equity_df[ticker].iloc[0]
        equity_df[ticker] = equity_df[ticker] * scale

    if cross_weight_df is not None:
        # Apply dynamic cross-signal weights day-by-day
        # final_weight[ticker][t] = base_weight[ticker] * (1 + cross_override[ticker][t])
        # cross_override is {-1, 0, +1}: scale position between 0x and 2x base weight
        for i, ticker in enumerate(success_tickers):
            if ticker in cross_weight_df.columns:
                override = cross_weight_df[ticker].reindex(equity_df.index, fill_value=0.0)
                # Scale factor: 0 (short override) → 1 (neutral) → 2 (long override)
                scale_factor = 1.0 + override
                equity_df[ticker] = equity_df[ticker] * scale_factor

    portfolio_equity = equity_df.sum(axis=1)
    portfolio_returns = portfolio_equity.pct_change().dropna()

    # Per-asset returns DataFrame for correlation
    returns_df = pd.DataFrame(per_asset_daily_returns)

    # ── Portfolio metrics ──
    portfolio_metrics = compute_portfolio_metrics(
        portfolio_returns=portfolio_returns,
        per_asset_returns=returns_df,
        weights=active_weights,
        n_trials=n_trials,
    )

    # ── Serialize ──
    equity_list = [
        {"date": _date_str(idx), "value": round(float(v), 2)}
        for idx, v in portfolio_equity.items()
    ]

    per_asset_summary = {}
    for ticker in success_tickers:
        r = per_asset_results[ticker]
        per_asset_summary[ticker] = {
            "metrics": r["metrics"],
            "signal_summaries": r["signal_summaries"],
        }

    actual_train = {
        "start": str(d_train_start),
        "end": str(d_train_end),
    }
    actual_test = {
        "start": str(d_test_start),
        "end": str(d_test_end),
    }

    result = {
        "tickers": success_tickers,
        "weights": {t: round(w, 4) for t, w in zip(success_tickers, active_weights)},
        "weight_scheme": weight_scheme,
        "train_period": actual_train,
        "test_period": actual_test,
        "models_used": models,
        "portfolio_metrics": portfolio_metrics,
        "per_asset": per_asset_summary,
        "portfolio_equity_curve": equity_list,
        "warnings": all_warnings,
    }

    if cross_summary is not None:
        result["cross_signal"] = cross_summary

    return result
