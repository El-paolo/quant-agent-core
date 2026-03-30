"""POST /analysis/timeseries/ — return full time-series data for charting."""

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


@router.post("/timeseries/", response_model=TimeseriesResponse)
async def analysis_timeseries(request: TimeseriesRequest) -> TimeseriesResponse:
    """
    Fetch prices and return full time-series data for the requested indicators.

    Unlike POST /analysis/ (which returns only the latest scalar value per metric),
    this endpoint returns the complete time series so the frontend can render charts.

    Raises HTTP 422 for bad input or data issues, 500 for unexpected errors.
    """
    try:
        prices = fetch_close_prices(request.ticker, period=request.period)
        prices = clean_prices(prices)

        warnings: list[str] = []
        series: dict = {}
        requested = set(request.series)

        returns_result = compute_returns(prices, method="log")
        returns_series = returns_result["returns"]

        if "prices" in requested:
            series["prices"] = _series_to_list(prices)

        if "returns" in requested:
            series["returns"] = _series_to_list(returns_series)

        if "rolling_volatility" in requested:
            rv = rolling_volatility(returns_series, window=21)
            series["rolling_volatility"] = _series_to_list(rv["volatility(s.d.)"])

        if "rsi" in requested:
            rsi = compute_rsi(prices, window=14)
            series["rsi"] = _series_to_list(rsi)

        if "macd" in requested:
            macd_df = compute_macd(prices)
            series["macd"] = _series_to_list(macd_df)

        if "bollinger" in requested:
            bb_df = compute_bollinger_bands(prices)
            # Include price for context in Bollinger chart
            bb_with_price = bb_df.copy()
            bb_with_price["price"] = prices.reindex(bb_df.index)
            series["bollinger"] = _series_to_list(bb_with_price)

        if "volume" in requested:
            vol_series = fetch_volume(request.ticker, period=request.period)
            if not vol_series.empty:
                series["volume"] = _series_to_list(vol_series)
            else:
                series["volume"] = []
                warnings.append("Volume data not available for this ticker.")

        if "ohlc" in requested:
            ohlc_df = fetch_ohlc(request.ticker, period=request.period)
            if not ohlc_df.empty:
                series["ohlc"] = _series_to_list(ohlc_df)
            else:
                series["ohlc"] = []
                warnings.append("OHLC data not available for this ticker.")

    except (FetcherError, MetricsError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal timeseries error")

    return TimeseriesResponse(
        ticker=request.ticker,
        period=request.period,
        series=series,
        warnings=warnings,
    )
