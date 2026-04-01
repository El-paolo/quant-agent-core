"""
Models orchestration — runs GARCH and HMM on price data.

Follows the same pattern as analysis.py: fetch → clean → compute,
with per-model graceful degradation (None + warning on failure).
"""

from fina.core.exceptions import FetcherError, MetricsError
from fina.data.cleaner import clean_prices
from fina.data.fetcher import fetch_close_prices
from fina.metrics.returns import compute_returns
from fina.models.arima import fit_arima
from fina.models.comparator import compare_models
from fina.models.garch import fit_garch
from fina.models.hmm import fit_hmm


def run_models(
    ticker: str,
    period: str = "1y",
    garch_horizon: int = 5,
    hmm_states: int = 3,
) -> dict:
    """
    Fetch prices and run quantitative models (GARCH, HMM).

    Each model is wrapped individually so one failure does not
    prevent the others from running.

    Returns:
        dict with keys: garch, hmm, warnings
        - garch: model results or None
        - hmm: model results or None
        - warnings: list of non-fatal issues
    """
    warnings: list[str] = []

    # Fetch and prepare data
    prices = fetch_close_prices(ticker, period=period)
    prices = clean_prices(prices)
    returns_result = compute_returns(prices, method="log")
    returns_series = returns_result["returns"]

    result: dict = {}

    # GARCH
    try:
        garch_result = fit_garch(returns_series, horizon=garch_horizon)
        result["garch"] = {
            "forecast": garch_result["forecast"],
            "diagnostics": garch_result["diagnostics"],
            "split": garch_result["split"],
            "train_score": garch_result["train_score"],
            "test_score": garch_result["test_score"],
            "horizon": garch_result["horizon"],
            "observations": garch_result["observations"],
            "confidence": garch_result["confidence"],
        }
    except MetricsError as exc:
        result["garch"] = None
        warnings.append(f"GARCH unavailable: {exc}")

    # HMM
    try:
        hmm_result = fit_hmm(returns_series, n_states=hmm_states)
        result["hmm"] = {
            "current_regime": hmm_result["current_regime"],
            "state_params": hmm_result["state_params"],
            "distributions": hmm_result["distributions"],
            "transition_matrix": hmm_result["transition_matrix"],
            "split": hmm_result["split"],
            "train_score": hmm_result["train_score"],
            "test_score": hmm_result["test_score"],
            "n_states": hmm_result["n_states"],
            "observations": hmm_result["observations"],
            "aic": hmm_result["aic"],
            "bic": hmm_result["bic"],
        }
    except MetricsError as exc:
        result["hmm"] = None
        warnings.append(f"HMM unavailable: {exc}")

    # ARIMA
    try:
        arima_result = fit_arima(returns_series, horizon=garch_horizon)
        result["arima"] = {
            "forecast": arima_result["forecast"],
            "diagnostics": arima_result["diagnostics"],
            "split": arima_result["split"],
            "train_score": arima_result["train_score"],
            "test_score": arima_result["test_score"],
            "horizon": arima_result["horizon"],
            "observations": arima_result["observations"],
            "confidence": arima_result["confidence"],
        }
    except MetricsError as exc:
        result["arima"] = None
        warnings.append(f"ARIMA unavailable: {exc}")

    result["warnings"] = warnings
    return result


def run_comparison(
    ticker: str,
    period: str = "1y",
    horizon: int = 5,
) -> dict:
    """
    Fetch prices and run the model comparator (ARIMA vs GARCH).

    Returns:
        dict with keys: models, comparison, verdict, warnings
    """
    prices = fetch_close_prices(ticker, period=period)
    prices = clean_prices(prices)
    returns_result = compute_returns(prices, method="log")
    returns_series = returns_result["returns"]

    return compare_models(returns_series, horizon=horizon)


def run_models_timeseries(
    ticker: str,
    period: str = "1y",
    garch_horizon: int = 5,
    hmm_states: int = 3,
) -> dict:
    """
    Like run_models but returns full time series for charting.

    Returns:
        dict with keys: garch_vol, hmm_states, warnings
        - garch_vol: list of {date, value} for conditional volatility
        - hmm_states: list of {date, state, label} for regime sequence
        - warnings: list of non-fatal issues
    """
    warnings: list[str] = []

    prices = fetch_close_prices(ticker, period=period)
    prices = clean_prices(prices)
    returns_result = compute_returns(prices, method="log")
    returns_series = returns_result["returns"]

    series: dict = {}

    # GARCH conditional volatility series
    try:
        garch_result = fit_garch(returns_series, horizon=garch_horizon)
        cond_vol = garch_result["conditional_vol"]
        series["garch_vol"] = [
            {
                "date": str(idx.date() if hasattr(idx, "date") else idx),
                "value": float(v) if v == v else None,
            }
            for idx, v in cond_vol.items()
        ]
        series["garch_forecast"] = garch_result["forecast"]
    except MetricsError as exc:
        series["garch_vol"] = []
        series["garch_forecast"] = []
        warnings.append(f"GARCH unavailable: {exc}")

    # HMM regime state sequence
    try:
        hmm_result = fit_hmm(returns_series, n_states=hmm_states)
        states = hmm_result["states"]
        state_ids = hmm_result["state_sequence"]
        series["hmm_states"] = [
            {
                "date": str(idx.date() if hasattr(idx, "date") else idx),
                "state": int(state_ids.iloc[i]),
                "label": states.iloc[i],
            }
            for i, idx in enumerate(states.index)
        ]
    except MetricsError as exc:
        series["hmm_states"] = []
        warnings.append(f"HMM unavailable: {exc}")

    # ARIMA fitted values
    try:
        arima_result = fit_arima(returns_series, horizon=garch_horizon)
        fitted = arima_result["fitted_values"]
        residuals = arima_result["residuals"]
        series["arima_fitted"] = [
            {
                "date": str(idx.date() if hasattr(idx, "date") else idx),
                "actual": float(returns_series.loc[idx]) if idx in returns_series.index else None,
                "fitted": float(fitted.iloc[i]) if fitted.iloc[i] == fitted.iloc[i] else None,
                "residual": float(residuals.iloc[i]) if residuals.iloc[i] == residuals.iloc[i] else None,
            }
            for i, idx in enumerate(fitted.index)
        ]
        series["arima_forecast"] = arima_result["forecast"]
    except MetricsError as exc:
        series["arima_fitted"] = []
        series["arima_forecast"] = []
        warnings.append(f"ARIMA unavailable: {exc}")

    series["warnings"] = warnings
    return series
