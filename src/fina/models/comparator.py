"""
Model comparator — runs multiple models and produces a side-by-side
comparison table with standardized metrics.

This is the core differentiator: instead of hiding model quality behind
a single "signal", we show the user exactly how each model performs
and let them make informed decisions.

Comparison dimensions:
  - In-sample fit: AIC, BIC
  - Out-of-sample accuracy: MAE, RMSE
  - Model-specific: directional accuracy (ARIMA), volatility fit (GARCH)
  - Residual quality: Ljung-Box p-value
  - Verdict: which model is better for what purpose
"""

import numpy as np
import pandas as pd

from fina.core.exceptions import MetricsError


def compare_models(
    returns: pd.Series,
    horizon: int = 5,
    confidence: float = 0.95,
    train_ratio: float = 0.80,
) -> dict:
    """
    Run ARIMA and GARCH on the same return series and compare them.

    Args:
        returns:     Log-returns series (daily).
        horizon:     Forecast horizon in days.
        confidence:  Confidence level.
        train_ratio: Train/test split ratio.

    Returns:
        dict with keys:
          - models: dict mapping model name → summary results
          - comparison: list of dicts with metric, arima_value, garch_value, winner
          - verdict: dict with best_forecast, best_volatility, summary_es
          - warnings: list of non-fatal issues
    """
    from fina.models.arima import fit_arima
    from fina.models.garch import fit_garch

    warnings_list: list[str] = []
    models: dict = {}

    # ── Fit ARIMA ──
    try:
        arima = fit_arima(
            returns, horizon=horizon, confidence=confidence,
            train_ratio=train_ratio,
        )
        models["arima"] = {
            "name": "ARIMA",
            "name_full": f"ARIMA{tuple(arima['diagnostics']['order'])}",
            "type": "return_forecast",
            "order": arima["diagnostics"]["order"],
            "aic": arima["diagnostics"]["aic"],
            "bic": arima["diagnostics"]["bic"],
            "train_mae": arima["train_score"]["mae"],
            "train_rmse": arima["train_score"]["rmse"],
            "test_mae": arima["test_score"]["mae"],
            "test_rmse": arima["test_score"]["rmse"],
            "directional_accuracy": arima["test_score"]["directional_accuracy"],
            "ljung_box_p": arima["diagnostics"]["ljung_box_pvalue"],
            "forecast": arima["forecast"],
            "observations": arima["observations"],
            "split": arima["split"],
        }
    except MetricsError as exc:
        models["arima"] = None
        warnings_list.append(f"ARIMA unavailable: {exc}")

    # ── Fit GARCH ──
    try:
        garch = fit_garch(
            returns, horizon=horizon, confidence=confidence,
            train_ratio=train_ratio,
        )
        models["garch"] = {
            "name": "GARCH(1,1)",
            "name_full": "GARCH(1,1)",
            "type": "volatility_forecast",
            "order": [1, 1],
            "aic": garch["diagnostics"]["aic"],
            "bic": garch["diagnostics"]["bic"],
            "persistence": garch["diagnostics"]["persistence"],
            "train_mae": None,  # GARCH doesn't forecast returns
            "train_rmse": None,
            "test_mae": garch["test_score"]["mae"],
            "test_rmse": garch["test_score"]["rmse"],
            "directional_accuracy": None,
            "ljung_box_p": None,
            "forecast": garch["forecast"],
            "observations": garch["observations"],
            "split": garch["split"],
        }
    except MetricsError as exc:
        models["garch"] = None
        warnings_list.append(f"GARCH unavailable: {exc}")

    # ── Build comparison table ──
    comparison = _build_comparison(models)

    # ── Verdict ──
    verdict = _build_verdict(models)

    return {
        "models": models,
        "comparison": comparison,
        "verdict": verdict,
        "warnings": warnings_list,
    }


def _build_comparison(models: dict) -> list[dict]:
    """Build a list of metric rows for the comparison table."""
    arima = models.get("arima")
    garch = models.get("garch")

    rows = []

    def _add(metric, label, arima_val, garch_val, lower_is_better=True, fmt="auto"):
        a_str = _fmt_val(arima_val, fmt)
        g_str = _fmt_val(garch_val, fmt)

        winner = None
        if arima_val is not None and garch_val is not None:
            if lower_is_better:
                winner = "arima" if arima_val < garch_val else "garch"
            else:
                winner = "arima" if arima_val > garch_val else "garch"

        rows.append({
            "metric": metric,
            "label": label,
            "arima": a_str,
            "arima_raw": arima_val,
            "garch": g_str,
            "garch_raw": garch_val,
            "winner": winner,
        })

    _add("aic", "AIC (full)",
         arima["aic"] if arima else None,
         garch["aic"] if garch else None,
         lower_is_better=True)

    _add("bic", "BIC (full)",
         arima["bic"] if arima else None,
         garch["bic"] if garch else None,
         lower_is_better=True)

    _add("test_mae", "MAE out-of-sample",
         arima["test_mae"] if arima else None,
         garch["test_mae"] if garch else None,
         lower_is_better=True, fmt="pct4")

    _add("test_rmse", "RMSE out-of-sample",
         arima["test_rmse"] if arima else None,
         garch["test_rmse"] if garch else None,
         lower_is_better=True, fmt="pct4")

    _add("directional_accuracy", "Precisión direccional",
         arima["directional_accuracy"] if arima else None,
         None,  # GARCH doesn't forecast direction
         lower_is_better=False, fmt="pct1")

    _add("ljung_box_p", "Ljung-Box p-value",
         arima["ljung_box_p"] if arima else None,
         None,  # GARCH residuals not tested here
         lower_is_better=False)  # higher p = less autocorrelation = better

    return rows


def _build_verdict(models: dict) -> dict:
    """Determine which model is better for what purpose."""
    arima = models.get("arima")
    garch = models.get("garch")

    # Return forecast verdict
    best_forecast = None
    if arima and arima.get("test_mae") is not None:
        order = arima.get("order", [0, 0, 0])
        if order == [0, 0, 0]:
            best_forecast = "none"
            forecast_reason = "ARIMA seleccionó orden (0,0,0): los retornos son ruido blanco — no son predecibles con información histórica."
        elif arima["directional_accuracy"] is not None and arima["directional_accuracy"] > 0.55:
            best_forecast = "arima"
            forecast_reason = f"ARIMA{tuple(order)} tiene precisión direccional de {arima['directional_accuracy']*100:.0f}% — superior al azar (50%)."
        else:
            best_forecast = "weak"
            forecast_reason = "ARIMA tiene precisión direccional ≤55% — no es confiable como señal de trading."
    else:
        best_forecast = "unavailable"
        forecast_reason = "ARIMA no disponible."

    # Volatility forecast verdict
    best_volatility = None
    if garch:
        persistence = garch.get("persistence", 0)
        if persistence >= 1.0:
            best_volatility = "unstable"
            vol_reason = "GARCH tiene persistencia ≥1 (IGARCH) — la volatilidad no revierte a un nivel de largo plazo."
        elif persistence > 0.95:
            best_volatility = "garch"
            vol_reason = f"GARCH(1,1) con alta persistencia ({persistence:.3f}) — buena captura de clustering de volatilidad."
        else:
            best_volatility = "garch"
            vol_reason = f"GARCH(1,1) estacionario (persistencia {persistence:.3f}) — modelo estable de volatilidad."
    else:
        best_volatility = "unavailable"
        vol_reason = "GARCH no disponible."

    # Summary
    if best_forecast == "none":
        summary = "Los retornos no muestran estructura predecible (ARIMA 0,0,0). " + vol_reason
    elif best_forecast == "arima":
        summary = forecast_reason + " " + vol_reason
    else:
        summary = forecast_reason + " " + vol_reason

    return {
        "best_forecast": best_forecast,
        "forecast_reason": forecast_reason,
        "best_volatility": best_volatility,
        "volatility_reason": vol_reason,
        "summary_es": summary,
    }


def _fmt_val(val, fmt="auto") -> str:
    """Format a value for display."""
    if val is None:
        return "N/A"
    if fmt == "pct4":
        return f"{val * 100:.4f}%"
    if fmt == "pct1":
        return f"{val * 100:.1f}%"
    if isinstance(val, float):
        if abs(val) > 100:
            return f"{val:.1f}"
        return f"{val:.4f}"
    return str(val)
