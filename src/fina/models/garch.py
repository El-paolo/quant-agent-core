"""
GARCH(1,1) volatility model.

Fits a GARCH(1,1) to log-returns and produces:
  - Conditional volatility series (historical)
  - N-day volatility forecast with confidence intervals
  - Model diagnostics (persistence, AIC/BIC)
  - Train/test validation metrics (out-of-sample MAE)

Uses a train/test split (default 80/20) so forecast quality can be
evaluated on unseen data.

Minimum ~50 observations recommended for stable estimation.
"""

import warnings

import numpy as np
import pandas as pd

from fina.core.exceptions import MetricsError

_MIN_OBS = 50
_DEFAULT_HORIZON = 5
_DEFAULT_TRAIN_RATIO = 0.80


def fit_garch(
    returns: pd.Series,
    horizon: int = _DEFAULT_HORIZON,
    confidence: float = 0.95,
    train_ratio: float = _DEFAULT_TRAIN_RATIO,
) -> dict:
    """
    Fit GARCH(1,1) to a return series and produce volatility forecast.

    The data is split temporally into train/test sets. The model is fit
    on the train set; out-of-sample evaluation compares predicted
    conditional volatility against realized volatility on the test set.

    Args:
        returns:     Log-returns series (daily).
        horizon:     Number of days to forecast.
        confidence:  Confidence level for forecast intervals (0-1).
        train_ratio: Fraction of data used for training (0.5-0.95).

    Returns:
        dict with keys:
          - conditional_vol: pd.Series of historical conditional volatility
          - forecast: list of dicts with day, volatility, upper, lower
          - diagnostics: dict with omega, alpha, beta, persistence, aic, bic
          - split: dict with train_size, test_size, train_ratio
          - train_score: dict with aic, bic (on train set)
          - test_score: dict with mae, rmse, realized_vol (out-of-sample)
          - horizon: int
          - observations: int
          - confidence: float

    Raises:
        MetricsError: If data is insufficient or model fails to converge.
    """
    from arch import arch_model

    clean = returns.dropna()
    if len(clean) < _MIN_OBS:
        raise MetricsError(
            f"GARCH requires at least {_MIN_OBS} observations, got {len(clean)}"
        )

    if not 0.5 <= train_ratio <= 0.95:
        raise MetricsError("train_ratio must be between 0.5 and 0.95")

    # ── Train/test split (temporal) ──
    split_idx = int(len(clean) * train_ratio)
    train = clean.iloc[:split_idx]
    test = clean.iloc[split_idx:]

    if len(train) < _MIN_OBS:
        raise MetricsError(
            f"Train set too small after split: {len(train)} obs (need {_MIN_OBS})"
        )

    # Scale returns to percentage for numerical stability (arch convention)
    scaled_train = train * 100
    scaled_full = clean * 100

    # ── Fit on TRAIN set ──
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            train_model = arch_model(
                scaled_train, vol="Garch", p=1, q=1, mean="Zero", rescale=False
            )
            train_result = train_model.fit(disp="off", show_warning=False)
    except Exception as exc:
        raise MetricsError(f"GARCH fitting failed: {exc}") from exc

    # ── Refit on FULL data for production conditional vol ──
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            full_model = arch_model(
                scaled_full, vol="Garch", p=1, q=1, mean="Zero", rescale=False
            )
            full_result = full_model.fit(disp="off", show_warning=False)
    except Exception as exc:
        raise MetricsError(f"GARCH full refit failed: {exc}") from exc

    # Extract parameters (from full fit for production use)
    params = full_result.params
    omega = float(params.get("omega", 0))
    alpha = float(params.get("alpha[1]", 0))
    beta = float(params.get("beta[1]", 0))
    persistence = alpha + beta

    # Conditional volatility (from full fit, back to decimal)
    cond_vol = full_result.conditional_volatility / 100

    # ── Out-of-sample evaluation ──
    # Predicted vol on test set: use train model's conditional vol extrapolated
    # by applying the trained parameters to the full series
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            # Apply train parameters to full data to get conditional vol
            train_params = train_result.params
            eval_model = arch_model(
                scaled_full, vol="Garch", p=1, q=1, mean="Zero", rescale=False
            )
            eval_result = eval_model.fit(
                disp="off", show_warning=False,
                starting_values=train_params.values,
                options={"maxiter": 0},  # don't re-optimize, just filter
            )
            predicted_vol_test = eval_result.conditional_volatility.iloc[split_idx:] / 100
    except Exception:
        predicted_vol_test = None

    # Realized volatility on test set (rolling 5-day realized vol as proxy)
    test_abs_returns = test.abs()
    # Use absolute returns as realized vol proxy (unbiased for daily scale)
    if predicted_vol_test is not None and len(test) > 0:
        realized = test_abs_returns.values
        predicted = predicted_vol_test.values
        # Align lengths
        n_eval = min(len(realized), len(predicted))
        realized = realized[:n_eval]
        predicted = predicted[:n_eval]
        mae = float(np.mean(np.abs(predicted - realized)))
        rmse = float(np.sqrt(np.mean((predicted - realized) ** 2)))
        realized_vol_mean = float(np.mean(realized))
        test_score = {
            "mae": mae,
            "rmse": rmse,
            "realized_vol": realized_vol_mean,
            "n_samples": n_eval,
        }
    else:
        test_score = {"mae": None, "rmse": None, "realized_vol": None, "n_samples": 0}

    # ── Forecast (from full fit) ──
    try:
        fcast = full_result.forecast(horizon=horizon)
        variance_fcast = fcast.variance.iloc[-1].values / 10000
        vol_fcast = np.sqrt(variance_fcast)
    except Exception:
        uncond_var = (
            omega / (1 - persistence)
            if persistence < 1
            else cond_vol.iloc[-1] ** 2 * 10000
        )
        variance_fcast = np.full(horizon, uncond_var / 10000)
        vol_fcast = np.sqrt(variance_fcast)

    # Confidence intervals
    from scipy.stats import norm

    z = norm.ppf(0.5 + confidence / 2)

    forecast_days = []
    for i in range(horizon):
        point = float(vol_fcast[i])
        margin = point * z * 0.2  # ~20% relative uncertainty approximation
        forecast_days.append(
            {
                "day": i + 1,
                "volatility": point,
                "upper": point + margin,
                "lower": max(0, point - margin),
            }
        )

    # Train-set AIC/BIC
    train_aic = float(train_result.aic)
    train_bic = float(train_result.bic)

    return {
        "conditional_vol": pd.Series(
            cond_vol.values, index=clean.index, name="conditional_vol"
        ),
        "forecast": forecast_days,
        "diagnostics": {
            "omega": omega / 10000,  # back to decimal scale
            "alpha": alpha,
            "beta": beta,
            "persistence": persistence,
            "aic": float(full_result.aic),
            "bic": float(full_result.bic),
            "long_run_vol": (
                float(np.sqrt(omega / (1 - persistence)) / 100)
                if persistence < 1
                else None
            ),
        },
        "split": {
            "train_size": len(train),
            "test_size": len(test),
            "train_ratio": train_ratio,
        },
        "train_score": {
            "aic": train_aic,
            "bic": train_bic,
        },
        "test_score": test_score,
        "horizon": horizon,
        "observations": len(clean),
        "confidence": confidence,
    }
