"""GET /fundamentals/{ticker} — company fundamental data."""

import asyncio

from fastapi import APIRouter, HTTPException

from fina.core.exceptions import FetcherError
from fina.data.fetcher import fetch_fundamentals

router = APIRouter(tags=["fundamentals"])


@router.get("/{ticker}")
async def get_fundamentals(ticker: str) -> dict:
    """
    Fetch fundamental company data (EPS, margins, ratios) for a ticker.

    Returns a dict with normalized field names. Fields may be null
    for tickers where the data is unavailable (ETFs, crypto, etc.).
    """
    try:
        result = await asyncio.to_thread(fetch_fundamentals, ticker)
    except FetcherError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal fundamentals error")

    return {"ticker": ticker.upper(), "fundamentals": result}
