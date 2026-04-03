"""
Signal generation from fitted models for backtesting.

Each generator takes pre-split train/test return series and produces
a daily signal pd.Series aligned with the test index:
  - Direction signals: {-1, 0, +1} (short / hold / long)
  - Sizing signals: float in [0.5, 2.0]

Signals are generated using fit-once-on-train with walk-forward
update (ARIMA) or filter (HMM/GARCH) — no refitting on test data.
"""

import warnings
from copy import deepcopy

import numpy as np
import pandas as pd

from fina.core.exceptions import BacktestError

_ARIMA_MIN_TRAIN = 60
_HMM_MIN_TRAIN = 100
_GARCH_MIN_TRAIN = 50


def generate_arima_signals(
    train_returns: pd.Series,
    test_returns: pd.Series,
    threshold: float = 0.0,
    max_order: int = 5,
) -> dict:
    """
    Generate directional signals from ARIMA walk-forward predictions.

    Fits auto-ARIMA on train, then walks forward through test using
    .update() (no refit). Positive prediction → +1, negative → -1,
    near-zero → 0.

    Returns:
        dict with signals (pd.Series), predictions (pd.Series),
        order (tuple), warnings (list).
    """
    import pmdarima as pm

    warn_list: list[str] = []
    train = train_returns.dropna()
    test = test_returns.dropna()

    if len(train) < _ARIMA_MIN_TRAIN:
        raise BacktestError(
            f"ARIMA needs ≥{_ARIMA_MIN_TRAIN} train obs, got {len(train)}"
        )
    if len(test) == 0:
        raise BacktestError("Test period is empty")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = pm.auto_arima(
                train.values,
                start_p=0, max_p=max_order,
                start_q=0, max_q=max_order,
                d=None, max_d=2,
                seasonal=False, stepwise=True,
                suppress_warnings=True,
                error_action="ignore",
                information_criterion="aic",
            )
    except Exception as exc:
        raise BacktestError(f"ARIMA fitting failed: {exc}") from exc

    order = model.order

    # ARIMA(0,0,0) means white noise — no directional opinion
    # Return None signals so combine_signals falls back to HMM direction
    if order == (0, 0, 0):
        warn_list.append("ARIMA(0,0,0): retornos son ruido blanco, sin señal direccional")
        return {
            "signals": None,
            "predictions": pd.Series(0.0, index=test.index, name="arima_pred"),
            "order": order,
            "warnings": warn_list,
        }

    # Walk-forward: predict 1-step, then update with actual
    eval_model = deepcopy(model)
    predictions = []

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for i in range(len(test)):
                pred = float(eval_model.predict(n_periods=1)[0])
                predictions.append(pred)
                eval_model.update(test.values[i : i + 1])
    except Exception as exc:
        raise BacktestError(f"ARIMA walk-forward failed: {exc}") from exc

    preds = pd.Series(predictions, index=test.index, name="arima_pred")

    # Convert predictions to signals
    signals = pd.Series(0, index=test.index, name="arima_signal", dtype=int)
    signals[preds > threshold] = 1
    signals[preds < -threshold] = -1

    return {
        "signals": signals,
        "predictions": preds,
        "order": order,
        "warnings": warn_list,
    }


def generate_hmm_signals(
    train_returns: pd.Series,
    test_returns: pd.Series,
    n_states: int = 3,
) -> dict:
    """
    Generate regime-based signals from HMM.

    Fits HMM on train, decodes test states. Maps:
      low_vol → +1 (long), mid_vol → 0 (hold), high_vol → -1 (risk-off).
    For 2-state: low_vol → +1, high_vol → -1.

    Returns:
        dict with signals (pd.Series), regimes (pd.Series), warnings (list).
    """
    from hmmlearn.hmm import GaussianHMM

    warn_list: list[str] = []
    train = train_returns.dropna()
    test = test_returns.dropna()

    if len(train) < _HMM_MIN_TRAIN:
        raise BacktestError(
            f"HMM needs ≥{_HMM_MIN_TRAIN} train obs, got {len(train)}"
        )
    if len(test) == 0:
        raise BacktestError("Test period is empty")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = GaussianHMM(
                n_components=n_states,
                covariance_type="full",
                n_iter=200,
                random_state=42,
                tol=1e-4,
            )
            model.fit(train.values.reshape(-1, 1))
    except Exception as exc:
        raise BacktestError(f"HMM fitting failed: {exc}") from exc

    # Decode test states
    test_states = model.predict(test.values.reshape(-1, 1))

    # Order states by variance (ascending) — same logic as hmm.py
    state_vars = []
    for i in range(n_states):
        cov = model.covars_[i]
        var = float(cov.flatten()[0]) if hasattr(cov, "flatten") else float(cov)
        state_vars.append(var)

    order = np.argsort(state_vars)
    label_keys = ["low_vol", "mid_vol", "high_vol"][:n_states]
    rank_map = {int(orig): rank for rank, orig in enumerate(order)}

    # Signal mapping
    if n_states == 3:
        signal_map = {0: 1, 1: 0, 2: -1}  # low_vol=long, mid=hold, high=short
    else:
        signal_map = {0: 1, 1: -1}  # low_vol=long, high=short

    labels = [label_keys[rank_map[s]] for s in test_states]
    signal_values = [signal_map[rank_map[s]] for s in test_states]

    regimes = pd.Series(labels, index=test.index, name="hmm_regime")
    signals = pd.Series(signal_values, index=test.index, name="hmm_signal", dtype=int)

    return {
        "signals": signals,
        "regimes": regimes,
        "warnings": warn_list,
    }


def generate_garch_sizing(
    train_returns: pd.Series,
    test_returns: pd.Series,
    target_vol: float | None = None,
    size_bounds: tuple[float, float] = (0.5, 2.0),
) -> dict:
    """
    Generate position-sizing multipliers from GARCH conditional volatility.

    Fits GARCH on train, filters conditional vol through test using
    trained parameters (maxiter=0). Sizing = target_vol / cond_vol,
    clipped to size_bounds.

    Returns:
        dict with sizing (pd.Series), cond_vol (pd.Series), warnings (list).
    """
    from arch import arch_model

    warn_list: list[str] = []
    train = train_returns.dropna()
    test = test_returns.dropna()

    if len(train) < _GARCH_MIN_TRAIN:
        raise BacktestError(
            f"GARCH needs ≥{_GARCH_MIN_TRAIN} train obs, got {len(train)}"
        )
    if len(test) == 0:
        raise BacktestError("Test period is empty")

    full = pd.concat([train, test])
    scaled_train = train * 100
    scaled_full = full * 100

    # Fit on train
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            train_model = arch_model(
                scaled_train, vol="Garch", p=1, q=1, mean="Zero", rescale=False,
            )
            train_result = train_model.fit(disp="off", show_warning=False)
    except Exception as exc:
        raise BacktestError(f"GARCH fitting failed: {exc}") from exc

    # Filter through full data with trained parameters (no refit)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            eval_m = arch_model(
                scaled_full, vol="Garch", p=1, q=1, mean="Zero", rescale=False,
            )
            eval_result = eval_m.fit(
                disp="off", show_warning=False,
                starting_values=train_result.params.values,
                options={"maxiter": 0},
            )
            cond_vol_full = eval_result.conditional_volatility / 100
    except Exception as exc:
        raise BacktestError(f"GARCH filtering failed: {exc}") from exc

    # Extract test-period conditional vol
    cond_vol_test = cond_vol_full.iloc[len(train):]
    cond_vol_test = pd.Series(cond_vol_test.values, index=test.index, name="garch_vol")

    # Determine target vol (default: long-run vol from train)
    if target_vol is None:
        params = train_result.params
        alpha = float(params.get("alpha[1]", 0))
        beta = float(params.get("beta[1]", 0))
        persistence = alpha + beta
        if persistence < 1:
            omega = float(params.get("omega", 0))
            target_vol = float(np.sqrt(omega / (1 - persistence)) / 100)
        else:
            target_vol = float(cond_vol_test.median())
            warn_list.append("GARCH persistencia ≥ 1, usando vol mediana como target")

    # Sizing: inverse vol scaling, clipped
    sizing = target_vol / cond_vol_test.replace(0, np.nan)
    sizing = sizing.clip(lower=size_bounds[0], upper=size_bounds[1]).fillna(1.0)
    sizing.name = "garch_sizing"

    return {
        "sizing": sizing,
        "cond_vol": cond_vol_test,
        "target_vol": target_vol,
        "warnings": warn_list,
    }


def combine_signals(
    arima_signals: pd.Series | None = None,
    hmm_signals: pd.Series | None = None,
    garch_sizing: pd.Series | None = None,
) -> pd.Series:
    """
    Combine model signals into a final position series.

    Logic:
      1. Base direction = HMM regime (if available), else flat.
      2. ARIMA overrides only on days where it has a non-zero opinion.
         If ARIMA is None (e.g. ARIMA(0,0,0) selected), HMM alone drives direction.
      3. HMM high_vol (risk-off, -1) always overrides final direction to 0.
      4. GARCH sizes the resulting position.

    This design ensures meaningful signals even when ARIMA selects (0,0,0)
    (white noise), by falling back to regime-based direction from HMM.

    Returns:
        pd.Series of float positions (signed, sized).
    """
    # Determine the common index
    indices = [s.index for s in [arima_signals, hmm_signals, garch_sizing] if s is not None]
    if not indices:
        raise BacktestError("At least one signal source is required")
    index = indices[0]

    # Step 1: Base direction from HMM (regime-based)
    if hmm_signals is not None:
        direction = hmm_signals.reindex(index, fill_value=0).astype(float)
    else:
        direction = pd.Series(0.0, index=index)

    # Step 2: ARIMA overrides on days it has a non-zero opinion
    if arima_signals is not None:
        arima = arima_signals.reindex(index, fill_value=0).astype(float)
        has_opinion = arima != 0
        direction = direction.copy()
        direction[has_opinion] = arima[has_opinion]

    # Step 3: if neither ARIMA nor HMM gave any direction, default to long
    if arima_signals is None and hmm_signals is None:
        direction = pd.Series(1.0, index=index)

    # Step 4: HMM risk-off filter — high_vol always overrides to hold
    if hmm_signals is not None:
        risk_off = hmm_signals.reindex(index, fill_value=0) == -1
        direction = direction.copy()
        direction[risk_off] = 0.0

    # Step 5: GARCH sizing
    if garch_sizing is not None:
        sizing = garch_sizing.reindex(index, fill_value=1.0)
        positions = direction * sizing
    else:
        positions = direction

    positions.name = "position"
    return positions
