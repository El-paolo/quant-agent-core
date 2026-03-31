"""POST /analysis/timeseries/ — return full time-series data for charting."""

import asyncio

from fastapi import APIRouter, HTTPException

from fina.api.schemas import TimeseriesRequest, TimeseriesResponse
from fina.core.exceptions import FetcherError, MetricsError, ValidationError
from fina.data.cleaner import clean_prices
from fina.data.fetcher import fetch_close_prices, fetch_ohlc, fetch_volume
from fina.metrics.returns import compute_returns
from fina.metrics.technical import compute_bollinger_bands, compute_macd, compute_rsi
from fina.metrics.volatility import rolling_volatility

router = APIRouter(tags=["analysis"])


def _series_to_list(s) -> list[dict]:
    """Convert a pandas Series or DataFrame to a JSON-serialisable list of dicts."""
    if hasattr(s, "to_frame"):
        # Series → [{date, value}, ...]
        return [
            {"date": str(idx.date() if hasattr(idx, "date") else idx), "value": float(v) if v == v else None}
            for idx, v in s.items()
        ]
    # DataFrame → [{date, col1, col2, ...}, ...]
    rows = []
    for idx, row in s.iterrows():
        entry = {"date": str(idx.date() if hasattr(idx, "date") else idx)}
        for col in s.columns:
            val = row[col]
            entry[col] = float(val) if val == val else None
        rows.append(entry)
    return rows


def _compute_timeseries(ticker: str, period: str, requested: set[str]) -> dict:
    """Synchronous helper — runs in a thread to avoid blocking the event loop."""
    prices = fetch_close_prices(ticker, period=period)
    prices = clean_prices(prices)

    warnings: list[str] = []
    series: dict = {}

    # Returns are needed by rolling_volatility; compute once, gracefully
    returns_series = None
    try:
        returns_result = compute_returns(prices, method="log")
        returns_series = returns_result["returns"]
    except (MetricsError, Exception) as exc:
        warnings.append(f"Returns computation failed: {exc}")

    if "prices" in requested:
        series["prices"] = _series_to_list(prices)

    if "returns" in requested:
        if returns_series is not None:
            series["returns"] = _series_to_list(returns_series)
        else:
            series["returns"] = []

    if "rolling_volatility" in requested:
        try:
            if returns_series is None:
                raise MetricsError("No returns available")
            rv = rolling_volatility(returns_series, window=21)
            series["rolling_volatility"] = _series_to_list(rv["volatility(s.d.)"])
        except (MetricsError, IndexError, KeyError) as exc:
            series["rolling_volatility"] = []
            warnings.append(f"Rolling volatility unavailable: {exc}")

    if "rsi" in requested:
        try:
            rsi = compute_rsi(prices, window=14)
            series["rsi"] = _series_to_list(rsi)
        except (MetricsError, IndexError) as exc:
            series["rsi"] = []
            warnings.append(f"RSI unavailable: {exc}")

    if "macd" in requested:
        try:
            macd_df = compute_macd(prices)
            if macd_df.empty:
                raise MetricsError("Insufficient data for MACD")
            series["macd"] = _series_to_list(macd_df)
        except (MetricsError, IndexError) as exc:
            series["macd"] = []
            warnings.append(f"MACD unavailable: {exc}")

    if "bollinger" in requested:
        try:
            bb_df = compute_bollinger_bands(prices)
            if bb_df.empty:
                raise MetricsError("Insufficient data for Bollinger Bands")
            bb_with_price = bb_df.copy()
            bb_with_price["price"] = prices.reindex(bb_df.index)
            series["bollinger"] = _series_to_list(bb_with_price)
        except (MetricsError, IndexError) as exc:
            series["bollinger"] = []
            warnings.append(f"Bollinger Bands unavailable: {exc}")

    if "volume" in requested:
        try:
            vol_series = fetch_volume(ticker, period=period)
            if not vol_series.empty:
                series["volume"] = _series_to_list(vol_series)
            else:
                series["volume"] = []
                warnings.append("Volume data not available for this ticker.")
        except Exception as exc:
            series["volume"] = []
            warnings.append(f"Volume unavailable: {exc}")

    if "ohlc" in requested:
        try:
            ohlc_df = fetch_ohlc(ticker, period=period)
            if not ohlc_df.empty:
                series["ohlc"] = _series_to_list(ohlc_df)
            else:
                series["ohlc"] = []
                warnings.append("OHLC data not available for this ticker.")
        except Exception as exc:
            series["ohlc"] = []
            warnings.append(f"OHLC unavailable: {exc}")

    return {"series": series, "warnings": warnings}


@router.post("/timeseries/", response_model=TimeseriesResponse)
async def analysis_timeseries(request: TimeseriesRequest) -> TimeseriesResponse:
    """
    Fetch prices and return full time-series data for the requested indicators.

    Unlike POST /analysis/ (which returns only the latest scalar value per metric),
    this endpoint returns the complete time series so the frontend can render charts.

    Raises HTTP 422 for bad input or data issues, 500 for unexpected errors.
    """
    try:
        result = await asyncio.to_thread(
            _compute_timeseries, request.ticker, request.period, set(request.series),
        )
    except (FetcherError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal timeseries error")

    return TimeseriesResponse(
        ticker=request.ticker,
        period=request.period,
        series=result["series"],
        warnings=result["warnings"],
    )
