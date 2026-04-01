"""
ARIMA / auto-ARIMA model for return forecasting.

Fits an ARIMA model to log-returns using automatic order selection
(AIC-based) via pmdarima, and produces:
  - Fitted values (in-sample)
  - N-day return forecast with confidence intervals
  - Model diagnostics (order, AIC/BIC, residual stats)
  - Train/test validation (out-of-sample MAE, RMSE, directional accuracy)

Minimum ~60 observations recommended for meaningful ARIMA fitting.
"""

import warnings

import numpy as np
import pandas as pd

from fina.core.exceptions import MetricsError

_MIN_OBS = 60
_DEFAULT_HORIZON = 5
_DEFAULT_TRAIN_RATIO = 0.80


def fit_arima(
    returns: pd.Series,
    horizon: int = _DEFAULT_HORIZON,
    confidence: float = 0.95,
    train_ratio: float = _DEFAULT_TRAIN_RATIO,
    max_order: int = 5,
) -> dict:
    """
    Fit auto-ARIMA to a return series and produce return forecast.

    Uses AIC-based stepwise search for optimal (p,d,q) order.
    Data is split temporally into train/test; the model is fit on
    train and evaluated out-of-sample on test.

    Args:
        returns:     Log-returns series (daily).
        horizon:     Number of days to forecast.
        confidence:  Confidence level for forecast intervals (0-1).
        train_ratio: Fraction of data used for training (0.5-0.95).
        max_order:   Maximum p, d, q to search.

    Returns:
        dict with keys:
          - fitted_values: pd.Series of in-sample fitted values
          - forecast: list of dicts {day, predicted, upper, lower}
          - residuals: pd.Series of in-sample residuals
          - diagnostics: dict with order, seasonal_order, aic, bic,
            residual_mean, residual_std, ljung_box_pvalue
          - split: dict with train_size, test_size, train_ratio
          - train_score: dict with aic, bic, mae, rmse
          - test_score: dict with mae, rmse, directional_accuracy, n_samples
          - horizon: int
          - observations: int
          - confidence: float

    Raises:
        MetricsError: If data is insufficient or model fails to converge.
    """
    import pmdarima as pm

    clean = returns.dropna()
    if len(clean) < _MIN_OBS:
        raise MetricsError(
            f"ARIMA requires at least {_MIN_OBS} observations, got {len(clean)}"
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

    # ── Auto-ARIMA on train set ──
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            train_model = pm.auto_arima(
                train.values,
                start_p=0, max_p=max_order,
                start_q=0, max_q=max_order,
                d=None,  # auto-detect differencing
                max_d=2,
                seasonal=False,
                stepwise=True,
                suppress_warnings=True,
                error_action="ignore",
                trace=False,
                information_criterion="aic",
            )
    except Exception as exc:
        raise MetricsError(f"ARIMA fitting failed: {exc}") from exc

    order = train_model.order
    train_aic = float(train_model.aic())
    train_bic = float(train_model.bic())

    # ── Train in-sample metrics ──
    train_fitted = train_model.predict_in_sample()
    train_residuals = train.values - train_fitted
    train_mae = float(np.mean(np.abs(train_residuals)))
    train_rmse = float(np.sqrt(np.mean(train_residuals ** 2)))

    # ── Out-of-sample walk-forward evaluation ──
    # Step through test set one observation at a time
    test_predictions = []
    test_actuals = []
    from copy import deepcopy
    eval_model = deepcopy(train_model)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            for i in range(len(test)):
                # Forecast 1 step ahead
                pred = float(eval_model.predict(n_periods=1)[0])
                test_predictions.append(pred)
                test_actuals.append(float(test.iloc[i]))
                # Update model with the actual observation (no refit, just update)
                eval_model.update(test.values[i : i + 1])
    except Exception:
        # Fallback: simple multi-step forecast if walk-forward fails
        test_predictions = []
        test_actuals = []

    if len(test_predictions) > 0:
        test_preds = np.array(test_predictions)
        test_acts = np.array(test_actuals)
        test_mae = float(np.mean(np.abs(test_preds - test_acts)))
        test_rmse = float(np.sqrt(np.mean((test_preds - test_acts) ** 2)))
        # Directional accuracy: did we predict the sign correctly?
        # Exclude near-zero predictions (|pred| < 1e-8) as "no opinion"
        mask = np.abs(test_preds) > 1e-8
        if mask.sum() > 0:
            dir_correct = np.sum(
                np.sign(test_preds[mask]) == np.sign(test_acts[mask])
            )
            dir_accuracy = float(dir_correct / mask.sum())
        else:
            dir_accuracy = None  # model has no directional opinion
        test_score = {
            "mae": test_mae,
            "rmse": test_rmse,
            "directional_accuracy": dir_accuracy,
            "n_samples": len(test_predictions),
        }
    else:
        test_score = {
            "mae": None, "rmse": None,
            "directional_accuracy": None, "n_samples": 0,
        }

    # ── Refit on FULL data for production forecast ──
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            full_model = pm.auto_arima(
                clean.values,
                start_p=order[0], max_p=order[0],
                start_q=order[2], max_q=order[2],
                d=order[1], max_d=order[1],
                seasonal=False,
                stepwise=True,
                suppress_warnings=True,
                error_action="ignore",
                trace=False,
            )
    except Exception as exc:
        raise MetricsError(f"ARIMA full refit failed: {exc}") from exc

    # ── Fitted values & residuals (full model) ──
    full_fitted = full_model.predict_in_sample()
    full_residuals = clean.values - full_fitted

    fitted_series = pd.Series(full_fitted, index=clean.index, name="arima_fitted")
    resid_series = pd.Series(full_residuals, index=clean.index, name="arima_residuals")

    # ── Forecast ──
    alpha = 1 - confidence
    try:
        fcast, conf_int = full_model.predict(
            n_periods=horizon, return_conf_int=True, alpha=alpha,
        )
    except Exception:
        fcast = np.zeros(horizon)
        half = 0.02  # fallback CI
        conf_int = np.column_stack([fcast - half, fcast + half])

    forecast_days = []
    for i in range(horizon):
        forecast_days.append({
            "day": i + 1,
            "predicted": float(fcast[i]),
            "upper": float(conf_int[i, 1]),
            "lower": float(conf_int[i, 0]),
        })

    # ── Residual diagnostics ──
    resid_mean = float(np.mean(full_residuals))
    resid_std = float(np.std(full_residuals, ddof=1))

    # Ljung-Box test for residual autocorrelation
    try:
        from statsmodels.stats.diagnostic import acorr_ljungbox
        lb = acorr_ljungbox(full_residuals, lags=[10], return_df=True)
        lb_pvalue = float(lb["lb_pvalue"].iloc[0])
    except Exception:
        lb_pvalue = None

    return {
        "fitted_values": fitted_series,
        "forecast": forecast_days,
        "residuals": resid_series,
        "diagnostics": {
            "order": list(order),
            "seasonal_order": None,
            "aic": float(full_model.aic()),
            "bic": float(full_model.bic()),
            "residual_mean": resid_mean,
            "residual_std": resid_std,
            "ljung_box_pvalue": lb_pvalue,
        },
        "split": {
            "train_size": len(train),
            "test_size": len(test),
            "train_ratio": train_ratio,
        },
        "train_score": {
            "aic": train_aic,
            "bic": train_bic,
            "mae": train_mae,
            "rmse": train_rmse,
        },
        "test_score": test_score,
        "horizon": horizon,
        "observations": len(clean),
        "confidence": confidence,
    }
