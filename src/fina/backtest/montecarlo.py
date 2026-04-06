"""
Monte Carlo simulation for backtesting.

Fits models once on the training period, generates N synthetic return
paths via GARCH(1,1) parametric simulation, runs the full strategy
pipeline on each path, and aggregates the results into percentile
distributions and a fan chart.

Key design decisions:
- ARIMA: deepcopy per simulation + walk-forward update (correct, adds ~50ms/sim)
- HMM: model.predict() is read-only, no copy needed
- GARCH: parametric path simulation from fitted omega/alpha/beta + last variance
- Price reconstruction: exp(cumsum(log_returns)) consistent with log-return convention
"""

import dataclasses
import warnings
from copy import deepcopy
from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from fina.backtest.signals import combine_signals
from fina.backtest.strategy import simulate_strategy
from fina.core.exceptions import BacktestError, FetcherError
from fina.data.cleaner import clean_prices
from fina.data.fetcher import fetch_close_prices
from fina.metrics.returns import compute_returns

_MC_MIN_SUCCESSFUL = 10   # minimum simulations before raising
_GARCH_VAR_FLOOR = 1e-8   # floor on scaled conditional variance
_SHOCK_CLIP_SIGMA = 10    # clip shocks at ±N*sigma to prevent blow-up


# ── Fitted model container ──────────────────────────────────────────────────

@dataclasses.dataclass
class _MCModels:
    arima_model: Any | None
    arima_order: tuple
    hmm_model: Any | None
    hmm_n_states: int
    hmm_rank_map: dict   # original_state_id → rank (0=low_vol)
    hmm_signal_map: dict # rank → signal {-1, 0, 1}
    garch_omega: float
    garch_alpha: float
    garch_beta: float
    garch_last_h_scaled: float  # last cond. var in (×100)^2 units
    garch_target_vol: float
    last_train_price: float
    test_index: pd.DatetimeIndex
    test_length: int


# ── GARCH path simulation ────────────────────────────────────────────────────

def _simulate_garch_path(
    omega: float,
    alpha: float,
    beta: float,
    last_h_scaled: float,
    T: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """
    Generate T synthetic log-returns using GARCH(1,1) parametric simulation.

    Returns unscaled log-returns (same units as train_returns).
    Internal computation uses ×100 scaling for numerical stability.

    Edge cases handled:
      - persistence >= 1: variance capped via epsilon floor on denominator
      - negative variance: hard floor at _GARCH_VAR_FLOOR
      - explosive shocks: clipped at ±_SHOCK_CLIP_SIGMA * sigma per step
    """
    persistence = alpha + beta
    # Pre-compute long-run variance cap for unstable GARCH
    eps = max(1 - persistence, 1e-6)
    h_cap = omega / eps * 10  # 10× long-run var as generous cap

    h = max(last_h_scaled, _GARCH_VAR_FLOOR)
    scaled_returns = np.empty(T)
    prev_e_sq = 0.0  # e_{-1}^2 = 0 (start with zero shock)

    for t in range(T):
        h = omega + alpha * prev_e_sq + beta * h
        h = max(min(h, h_cap), _GARCH_VAR_FLOOR)

        sigma = np.sqrt(h)
        e = rng.standard_normal() * sigma
        # Clip explosive shocks
        clip = _SHOCK_CLIP_SIGMA * sigma
        e = np.clip(e, -clip, clip)

        scaled_returns[t] = e
        prev_e_sq = e * e

    return scaled_returns / 100  # back to decimal scale


# ── Per-simulation signal generation ────────────────────────────────────────

def _arima_signals_synthetic(
    mc: _MCModels,
    synthetic_returns: np.ndarray,
    threshold: float,
) -> pd.Series | None:
    """Walk-forward ARIMA signals on a synthetic return path."""
    if mc.arima_model is None or mc.arima_order == (0, 0, 0):
        return None

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = deepcopy(mc.arima_model)
            signals = np.zeros(mc.test_length, dtype=int)
            for i, r in enumerate(synthetic_returns):
                pred = float(model.predict(n_periods=1)[0])
                if pred > threshold:
                    signals[i] = 1
                elif pred < -threshold:
                    signals[i] = -1
                model.update([r])
    except Exception:
        return None

    return pd.Series(signals, index=mc.test_index, name="arima_signal", dtype=int)


def _hmm_signals_synthetic(
    mc: _MCModels,
    synthetic_returns: np.ndarray,
) -> pd.Series | None:
    """HMM regime signals on a synthetic return path."""
    if mc.hmm_model is None:
        return None

    try:
        states = mc.hmm_model.predict(synthetic_returns.reshape(-1, 1))
        signal_values = [
            mc.hmm_signal_map[mc.hmm_rank_map[int(s)]]
            for s in states
        ]
        return pd.Series(signal_values, index=mc.test_index, name="hmm_signal", dtype=int)
    except Exception:
        return None


def _garch_sizing_synthetic(
    mc: _MCModels,
    synthetic_returns: np.ndarray,
    size_bounds: tuple = (0.5, 2.0),
) -> pd.Series | None:
    """GARCH position-sizing from conditional vol on the synthetic path."""
    T = mc.test_length
    h = max(mc.garch_last_h_scaled, _GARCH_VAR_FLOOR)
    cond_vols = np.empty(T)
    prev_e_sq = 0.0

    for t in range(T):
        h = mc.garch_omega + mc.garch_alpha * prev_e_sq + mc.garch_beta * h
        h = max(h, _GARCH_VAR_FLOOR)
        cond_vols[t] = np.sqrt(h) / 100   # unscaled
        prev_e_sq = (synthetic_returns[t] * 100) ** 2  # e_{t}^2 in scaled units

    sizing = mc.garch_target_vol / np.where(cond_vols > 0, cond_vols, mc.garch_target_vol)
    sizing = np.clip(sizing, size_bounds[0], size_bounds[1])
    return pd.Series(sizing, index=mc.test_index, name="garch_sizing")


# ── Model fitting ────────────────────────────────────────────────────────────

def _fit_models(
    train_returns: pd.Series,
    test_returns: pd.Series,
    models: list[str],
    arima_threshold: float,
    hmm_states: int,
) -> _MCModels:
    """Fit all requested models once on training data."""
    import pmdarima as pm
    from arch import arch_model
    from hmmlearn.hmm import GaussianHMM

    arima_model = None
    arima_order = (0, 0, 0)
    hmm_model = None
    hmm_rank_map: dict = {}
    hmm_signal_map: dict = {}
    garch_omega = 0.0
    garch_alpha = 0.0
    garch_beta = 0.0
    garch_last_h_scaled = 1.0
    garch_target_vol = 0.01

    train = train_returns.dropna()

    # ── ARIMA ──
    if "arima" in models and len(train) >= 60:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                arima_model = pm.auto_arima(
                    train.values,
                    start_p=0, max_p=5,
                    start_q=0, max_q=5,
                    d=None, max_d=2,
                    seasonal=False, stepwise=True,
                    suppress_warnings=True,
                    error_action="ignore",
                    information_criterion="aic",
                )
                arima_order = arima_model.order
        except Exception:
            arima_model = None

    # ── HMM ──
    if "hmm" in models and len(train) >= 100:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                hmm_model = GaussianHMM(
                    n_components=hmm_states,
                    covariance_type="full",
                    n_iter=200,
                    random_state=42,
                    tol=1e-4,
                )
                hmm_model.fit(train.values.reshape(-1, 1))

            # Build rank_map (state index → variance rank, 0=lowest)
            state_vars = []
            for i in range(hmm_states):
                cov = hmm_model.covars_[i]
                var = float(cov.flatten()[0]) if hasattr(cov, "flatten") else float(cov)
                state_vars.append(var)
            order = np.argsort(state_vars)
            hmm_rank_map = {int(orig): rank for rank, orig in enumerate(order)}

            if hmm_states == 3:
                hmm_signal_map = {0: 1, 1: 0, 2: -1}
            else:
                hmm_signal_map = {0: 1, 1: -1}
        except Exception:
            hmm_model = None

    # ── GARCH ──
    if "garch" in models and len(train) >= 50:
        try:
            scaled_train = train * 100
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                garch_m = arch_model(
                    scaled_train, vol="Garch", p=1, q=1,
                    mean="Zero", rescale=False,
                )
                garch_r = garch_m.fit(disp="off", show_warning=False)

            params = garch_r.params
            garch_omega = float(params.get("omega", 0))
            garch_alpha = float(params.get("alpha[1]", 0))
            garch_beta  = float(params.get("beta[1]", 0))
            persistence = garch_alpha + garch_beta

            # Last conditional variance (seed for simulation)
            garch_last_h_scaled = float(
                garch_r.conditional_volatility.iloc[-1] ** 2
            )

            # Long-run target vol for sizing
            if persistence < 1:
                garch_target_vol = float(
                    np.sqrt(garch_omega / max(1 - persistence, 1e-6)) / 100
                )
            else:
                garch_target_vol = float(
                    garch_r.conditional_volatility.median() / 100
                )
        except Exception:
            pass  # keep defaults (sizing will be ~1.0 everywhere)

    test = test_returns.dropna()

    return _MCModels(
        arima_model=arima_model,
        arima_order=arima_order,
        hmm_model=hmm_model,
        hmm_n_states=hmm_states,
        hmm_rank_map=hmm_rank_map,
        hmm_signal_map=hmm_signal_map,
        garch_omega=garch_omega,
        garch_alpha=garch_alpha,
        garch_beta=garch_beta,
        garch_last_h_scaled=garch_last_h_scaled,
        garch_target_vol=garch_target_vol,
        last_train_price=0.0,  # set after return
        test_index=test.index,
        test_length=len(test),
    )


# ── Aggregation ──────────────────────────────────────────────────────────────

def _aggregate(
    all_equity: np.ndarray,       # shape (n_ok, T)
    all_returns: np.ndarray,      # shape (n_ok,)
    all_drawdowns: np.ndarray,
    all_sharpes: np.ndarray,
    all_bh_returns: np.ndarray,
    test_index: pd.DatetimeIndex,
    initial_capital: float,
    n_ok: int,
) -> tuple[list[dict], dict]:
    """Compute percentile fan chart and metrics distribution."""
    percs = [5, 25, 50, 75, 95]
    equity_percs = np.percentile(all_equity[:n_ok], percs, axis=0)  # (5, T)

    fan_chart = [
        {
            "date": str(test_index[t].date() if hasattr(test_index[t], "date") else test_index[t]),
            "p5":  round(float(equity_percs[0, t]), 2),
            "p25": round(float(equity_percs[1, t]), 2),
            "p50": round(float(equity_percs[2, t]), 2),
            "p75": round(float(equity_percs[3, t]), 2),
            "p95": round(float(equity_percs[4, t]), 2),
        }
        for t in range(all_equity.shape[1])
    ]

    valid_returns = all_returns[:n_ok]
    valid_drawdowns = all_drawdowns[:n_ok]
    valid_sharpes = all_sharpes[:n_ok]
    valid_bh = all_bh_returns[:n_ok]

    ret_percs = np.percentile(valid_returns, percs)
    dd_percs = np.percentile(valid_drawdowns, [5, 50, 95])
    sh_percs = np.percentile(valid_sharpes, [5, 50, 95])

    var_95 = float(np.percentile(valid_returns, 5))
    tail = valid_returns[valid_returns <= var_95]
    cvar_95 = float(tail.mean()) if len(tail) > 0 else var_95

    prob_profit = float((valid_returns > 0).mean())
    prob_beat_bh = float((valid_returns > valid_bh).mean())

    def _pct_dict(arr, ks):
        return {f"p{k}": round(float(v), 6) for k, v in zip(ks, arr)}

    metrics_distribution = {
        "total_return": _pct_dict(ret_percs, percs),
        "max_drawdown": _pct_dict(dd_percs, [5, 50, 95]),
        "sharpe_ratio": _pct_dict(sh_percs, [5, 50, 95]),
        "var_95": round(var_95, 6),
        "cvar_95": round(cvar_95, 6),
        "prob_profit": round(prob_profit, 4),
        "prob_beat_benchmark": round(prob_beat_bh, 4),
    }

    return fan_chart, metrics_distribution


def _max_drawdown_fast(equity: np.ndarray) -> float:
    """Compute max drawdown from equity array without pandas overhead."""
    running_max = np.maximum.accumulate(equity)
    drawdowns = (equity - running_max) / np.where(running_max > 0, running_max, 1)
    return float(drawdowns.min())


# ── Main entry point ─────────────────────────────────────────────────────────

def run_montecarlo(
    ticker: str,
    train_start: str,
    train_end: str,
    test_start: str,
    test_end: str,
    n_simulations: int = 200,
    models: list[str] | None = None,
    initial_capital: float = 10_000.0,
    arima_threshold: float = 0.0,
    hmm_states: int = 3,
    garch_target_vol: float | None = None,
    commission_bps: float = 0.0,
    random_seed: int | None = None,
) -> dict:
    """
    Run N Monte Carlo simulations on the backtesting strategy.

    1. Fit models once on the training period
    2. Simulate N synthetic GARCH return paths for the test period length
    3. For each path: generate signals, simulate strategy, collect metrics
    4. Aggregate into percentile fan chart and risk metrics

    Args:
        ticker:          Stock ticker symbol.
        train_start:     Training period start (YYYY-MM-DD).
        train_end:       Training period end (YYYY-MM-DD).
        test_start:      Test period start (YYYY-MM-DD).
        test_end:        Test period end (YYYY-MM-DD).
        n_simulations:   Number of Monte Carlo paths (50–1000).
        models:          Subset of {"arima", "hmm", "garch"}.
        initial_capital: Starting capital.
        arima_threshold: Min |prediction| to trigger ARIMA signal.
        hmm_states:      Number of HMM states (2 or 3).
        garch_target_vol: Target vol for GARCH sizing (None = long-run vol).
        commission_bps:  Round-trip commission in basis points.
        random_seed:     Seed for reproducibility (None = random).

    Returns:
        dict with fan_chart, metrics_distribution, and metadata.

    Raises:
        BacktestError: On invalid inputs or insufficient data.
        FetcherError: On data fetching failures.
    """
    if models is None:
        models = ["arima", "hmm", "garch"]

    # ── Validate dates ──
    try:
        d_train_end  = date.fromisoformat(train_end)
        d_test_start = date.fromisoformat(test_start)
        d_train_start = date.fromisoformat(train_start)
        d_test_end   = date.fromisoformat(test_end)
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

    if n_simulations < _MC_MIN_SUCCESSFUL:
        raise BacktestError(
            f"n_simulations must be at least {_MC_MIN_SUCCESSFUL}, got {n_simulations}"
        )

    # ── Fetch & prepare data ──
    prices = fetch_close_prices(ticker, start=train_start, end=test_end)
    prices = clean_prices(prices)

    if len(prices) < 10:
        raise BacktestError(f"Insufficient price data: {len(prices)} points")

    returns_result = compute_returns(prices, method="log")
    returns_series = returns_result["returns"]

    train_returns = returns_series[returns_series.index <= str(d_train_end)]
    test_returns  = returns_series[returns_series.index >= str(d_test_start)]
    train_prices  = prices[prices.index <= str(d_train_end)]
    test_prices   = prices[prices.index >= str(d_test_start)]

    if len(train_returns) < 30:
        raise BacktestError(
            f"Train period too short: {len(train_returns)} trading days"
        )
    if len(test_returns) < 2:
        raise BacktestError(
            f"Test period too short: {len(test_returns)} trading days"
        )

    actual_train = {
        "start": str(train_returns.index[0].date()),
        "end":   str(train_returns.index[-1].date()),
        "trading_days": len(train_returns),
    }
    actual_test = {
        "start": str(test_returns.index[0].date()),
        "end":   str(test_returns.index[-1].date()),
        "trading_days": len(test_returns),
    }

    # ── Fit models once ──
    mc = _fit_models(train_returns, test_returns, models, arima_threshold, hmm_states)
    mc.last_train_price = float(train_prices.iloc[-1])

    # Override GARCH target vol if provided
    if garch_target_vol is not None:
        mc.garch_target_vol = garch_target_vol

    T = mc.test_length
    if T == 0:
        raise BacktestError("Test period produces empty return series")

    # ── Simulation loop ──
    rng = np.random.default_rng(random_seed)
    warn_list: list[str] = []

    all_equity     = np.zeros((n_simulations, T))
    all_returns    = np.zeros(n_simulations)
    all_drawdowns  = np.zeros(n_simulations)
    all_sharpes    = np.zeros(n_simulations)
    all_bh_returns = np.zeros(n_simulations)
    n_ok = 0

    for i in range(n_simulations):
        try:
            # 1. Generate synthetic returns via GARCH
            synth_returns = _simulate_garch_path(
                mc.garch_omega, mc.garch_alpha, mc.garch_beta,
                mc.garch_last_h_scaled, T, rng,
            )

            # 2. Reconstruct synthetic price path (log-return convention)
            synth_prices = mc.last_train_price * np.exp(np.cumsum(synth_returns))
            synth_prices_s = pd.Series(synth_prices, index=mc.test_index)

            # 3. Generate signals
            arima_sig = _arima_signals_synthetic(mc, synth_returns, arima_threshold)
            hmm_sig   = _hmm_signals_synthetic(mc, synth_returns)
            garch_siz = _garch_sizing_synthetic(mc, synth_returns)

            # 4. Combine signals → positions
            positions = combine_signals(arima_sig, hmm_sig, garch_siz)

            # 5. Simulate strategy
            sim = simulate_strategy(
                positions, synth_prices_s,
                initial_capital=initial_capital,
                commission_bps=commission_bps,
            )

            # 6. Collect metrics
            equity_arr = sim["equity_curve"].values
            all_equity[n_ok] = equity_arr

            final_eq = equity_arr[-1]
            all_returns[n_ok]    = final_eq / initial_capital - 1
            all_drawdowns[n_ok]  = _max_drawdown_fast(equity_arr)
            all_bh_returns[n_ok] = sim["benchmark_equity"].values[-1] / initial_capital - 1

            dr = sim["daily_returns"]
            if dr.std() > 0:
                all_sharpes[n_ok] = float(dr.mean() / dr.std() * np.sqrt(252))
            else:
                all_sharpes[n_ok] = 0.0

            n_ok += 1

        except Exception as exc:
            warn_list.append(f"Sim {i+1} failed: {exc}")
            continue

    if n_ok < _MC_MIN_SUCCESSFUL:
        raise BacktestError(
            f"Monte Carlo produced only {n_ok} successful simulations "
            f"(need at least {_MC_MIN_SUCCESSFUL}). "
            f"Warnings: {'; '.join(warn_list[:5])}"
        )

    # ── Aggregate ──
    fan_chart, metrics_dist = _aggregate(
        all_equity, all_returns, all_drawdowns, all_sharpes, all_bh_returns,
        mc.test_index, initial_capital, n_ok,
    )

    if n_ok < n_simulations:
        warn_list.append(
            f"{n_simulations - n_ok} simulations failed and were excluded "
            f"({n_ok} used for aggregation)"
        )

    return {
        "ticker": ticker,
        "n_simulations": n_ok,
        "train_period": actual_train,
        "test_period": actual_test,
        "fan_chart": fan_chart,
        "metrics_distribution": metrics_dist,
        "warnings": warn_list,
    }
