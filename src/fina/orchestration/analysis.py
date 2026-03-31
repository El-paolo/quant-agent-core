"""
Full analysis pipeline — chains data acquisition, cleaning, and metrics.

run_analysis() is the single entry point for all business logic.
Routes call this function and map its exceptions to HTTP status codes.

Design rules:
  - No HTTP concerns here — only domain logic.
  - All returned values are Python-native types (float, int, str, bool, None)
    so FastAPI can serialize them without extra conversion.
  - Sortino ratio raises MetricsError when there are no downside returns
    (e.g. during bull markets). This is captured and returned as a warning,
    not re-raised, because it is expected behavior, not an error.
"""

from fina.core.exceptions import FetcherError, MetricsError, ValidationError
from fina.data.cleaner import clean_prices
from fina.data.fetcher import fetch_close_prices
from fina.metrics.correlation import compute_beta
from fina.metrics.ratios import sharpe_ratio, sortino_ratio
from fina.metrics.returns import compute_returns
from fina.metrics.technical import (
    compute_bollinger_bands,
    compute_macd,
    compute_rsi,
)
from fina.metrics.volatility import realized_volatility, rolling_volatility

_ALL_METRICS = frozenset(
    {
        "returns",
        "volatility",
        "rolling_volatility",
        "sharpe",
        "sortino",
        "rsi",
        "macd",
        "bollinger",
        "beta",
    }
)

# Default market benchmark for beta calculation
_MARKET_BENCHMARK = "SPY"


def _f(value: object) -> float | None:
    """Safely cast a value to Python float, returning None if not possible."""
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def run_analysis(
    ticker: str,
    period: str = "1y",
    metrics: list[str] | None = None,
) -> dict:
    """
    Fetch prices and compute the requested financial metrics for a ticker.

    Args:
        ticker:  Asset ticker symbol (already sanitized by the API layer).
        period:  yfinance period string (e.g. "1y", "6mo").
        metrics: List of metric names to compute. Defaults to all metrics.
                 Valid names: returns, volatility, rolling_volatility,
                 sharpe, sortino, rsi, macd, bollinger, beta.

    Returns:
        dict mapping each requested metric name to its result dict.
        All values are JSON-serializable Python native types.
        A top-level ``"warnings"`` key lists non-fatal issues (e.g. Sortino
        undefined because no downside returns exist).

    Raises:
        FetcherError:    If price data cannot be fetched from yfinance.
        MetricsError:    If a metric computation fails fatally.
        ValidationError: If cleaned data fails validation.
    """
    if metrics is None:
        metrics = list(_ALL_METRICS)

    requested = set(metrics)
    warnings: list[str] = []
    result: dict = {}

    # ------------------------------------------------------------------
    # 1. Fetch and clean prices
    # ------------------------------------------------------------------
    prices = fetch_close_prices(ticker, period=period)
    prices = clean_prices(prices)

    outlier_count = prices.attrs.get("outlier_count", 0)
    if outlier_count > 0:
        warnings.append(f"{outlier_count} price outlier(s) detected but not removed.")

    # ------------------------------------------------------------------
    # 2. Compute returns once — reused by multiple metrics
    # ------------------------------------------------------------------
    try:
        returns_result = compute_returns(prices, method="log")
        returns_series = returns_result["returns"]
    except MetricsError as exc:
        # Without returns, most metrics are impossible
        returns_result = None
        returns_series = None
        warnings.append(f"Returns computation failed: {exc}")

    # ------------------------------------------------------------------
    # 3. Compute requested metrics (each wrapped individually so that
    #    one failure does not prevent the rest from being computed)
    # ------------------------------------------------------------------

    if "returns" in requested:
        if returns_result is not None:
            result["returns"] = {
                "method": returns_result["method"],
                "observations": int(returns_result["observations"]),
                "mean": _f(returns_series.mean()),
                "std": _f(returns_series.std()),
                "min": _f(returns_series.min()),
                "max": _f(returns_series.max()),
            }
        else:
            result["returns"] = None

    if "volatility" in requested:
        try:
            if returns_series is None:
                raise MetricsError("No returns available")
            vol = realized_volatility(returns_series)
            result["volatility"] = {
                k: (_f(v) if isinstance(v, (int, float)) else v)
                for k, v in vol.items()
            }
        except MetricsError as exc:
            result["volatility"] = None
            warnings.append(f"Volatility unavailable: {exc}")

    if "rolling_volatility" in requested:
        try:
            if returns_series is None:
                raise MetricsError("No returns available")
            roll_vol = rolling_volatility(returns_series, window=21)
            latest = roll_vol.dropna().iloc[-1] if not roll_vol.dropna().empty else None
            result["rolling_volatility"] = {
                "latest_sd": _f(latest["volatility(s.d.)"]) if latest is not None else None,
                "latest_variance": _f(latest["volatility(variance)"]) if latest is not None else None,
                "window": int(roll_vol.attrs.get("window", 21)),
            }
        except (MetricsError, IndexError) as exc:
            result["rolling_volatility"] = None
            warnings.append(f"Rolling volatility unavailable: {exc}")

    if "sharpe" in requested:
        try:
            if returns_series is None:
                raise MetricsError("No returns available")
            sr = sharpe_ratio(returns_series)
            result["sharpe"] = {
                k: (_f(v) if isinstance(v, (int, float)) else v)
                for k, v in sr.items()
            }
        except MetricsError as exc:
            result["sharpe"] = None
            warnings.append(f"Sharpe ratio unavailable: {exc}")

    if "sortino" in requested:
        try:
            if returns_series is None:
                raise MetricsError("No returns available")
            so = sortino_ratio(returns_series)
            result["sortino"] = {
                k: (_f(v) if isinstance(v, (int, float)) else v)
                for k, v in so.items()
            }
        except MetricsError as exc:
            result["sortino"] = None
            warnings.append(f"Sortino ratio unavailable: {exc}")

    if "rsi" in requested:
        try:
            rsi = compute_rsi(prices)
            result["rsi"] = {
                "latest": _f(rsi.iloc[-1]) if len(rsi) > 0 else None,
                "observations": len(rsi),
                "window": 14,
            }
        except (MetricsError, IndexError) as exc:
            result["rsi"] = None
            warnings.append(f"RSI unavailable: {exc}")

    if "macd" in requested:
        try:
            macd_df = compute_macd(prices)
            if macd_df.empty:
                raise MetricsError("Insufficient data for MACD (need 35+ observations)")
            latest_macd = macd_df.iloc[-1]
            result["macd"] = {
                "macd": _f(latest_macd["macd"]),
                "signal": _f(latest_macd["signal"]),
                "histogram": _f(latest_macd["histogram"]),
                "fast": 12,
                "slow": 26,
                "signal_period": 9,
            }
        except (MetricsError, IndexError) as exc:
            result["macd"] = None
            warnings.append(f"MACD unavailable: {exc}")

    if "bollinger" in requested:
        try:
            bb = compute_bollinger_bands(prices)
            if bb.empty:
                raise MetricsError("Insufficient data for Bollinger Bands (need 20+ observations)")
            latest_bb = bb.iloc[-1]
            result["bollinger"] = {
                "upper": _f(latest_bb["upper"]),
                "middle": _f(latest_bb["middle"]),
                "lower": _f(latest_bb["lower"]),
                "bandwidth": _f(latest_bb["bandwidth"]),
                "percent_b": _f(latest_bb["percent_b"]),
                "window": 20,
                "std_dev": 2.0,
            }
        except (MetricsError, IndexError) as exc:
            result["bollinger"] = None
            warnings.append(f"Bollinger Bands unavailable: {exc}")

    if "beta" in requested:
        try:
            if returns_series is None:
                raise MetricsError("No returns available")
            market_prices = fetch_close_prices(_MARKET_BENCHMARK, period=period)
            market_prices = clean_prices(market_prices)
            market_returns = compute_returns(market_prices, method="log")["returns"]
            beta_result = compute_beta(returns_series, market_returns)
            result["beta"] = {
                k: (_f(v) if isinstance(v, (int, float)) else v)
                for k, v in beta_result.items()
            }
            result["beta"]["benchmark"] = _MARKET_BENCHMARK
        except (FetcherError, MetricsError) as exc:
            result["beta"] = None
            warnings.append(f"Beta vs {_MARKET_BENCHMARK} unavailable: {exc}")

    result["warnings"] = warnings
    return result
