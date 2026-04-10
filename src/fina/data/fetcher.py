"""
Data fetcher — acquires adjusted close prices via yfinance.

Security notes:
  - Ticker symbols are validated against a strict allowlist regex before any
    external call.  This prevents injection-style attacks where a crafted
    ticker could influence shell commands, log aggregators, or downstream
    parsers that consume the ticker string.
  - Raw yfinance exceptions are always wrapped in FetcherError so that
    internal library stack-traces (which may leak environment details) are
    never propagated to callers.
  - Date strings are parsed through a controlled helper that rejects anything
    that does not conform to ISO-8601 (YYYY-MM-DD), preventing format-string
    or log-injection via date parameters.
"""

import re
import threading
from datetime import date, datetime

import pandas as pd
import yfinance as yf
from cachetools import TTLCache
from cachetools.keys import hashkey

from fina.core.exceptions import FetcherError

# ---------------------------------------------------------------------------
# Cache — avoids redundant yfinance network calls for the same ticker/period.
# Thread-safe via _price_cache_lock (FastAPI runs sync fetchers in threadpool).
# Call configure_price_cache() once at app startup to apply Settings values.
# ---------------------------------------------------------------------------
_price_cache: TTLCache = TTLCache(maxsize=128, ttl=300)
_price_cache_lock = threading.Lock()


def configure_price_cache(ttl: int = 300, maxsize: int = 128) -> None:
    """
    Reconfigure the price cache TTL and size.

    Call once at app startup (e.g. from create_app) with values from Settings.
    Safe to call multiple times — replaces the existing cache.

    Args:
        ttl:     Time-to-live in seconds. Default: 300 (5 min).
        maxsize: Maximum number of cached entries. Default: 128.
    """
    global _price_cache
    with _price_cache_lock:
        _price_cache = TTLCache(maxsize=maxsize, ttl=ttl)

# ---------------------------------------------------------------------------
# Security: strict allowlist for ticker symbols.
# Only uppercase letters, digits, hyphens (-), equals signs (=), and dots (.)
# are allowed. Max 20 characters covers all known real-world ticker formats.
# This regex is compiled once at module load for performance.
# ---------------------------------------------------------------------------
_TICKER_RE = re.compile(r"^[A-Z0-9\-=\.]{1,20}$")

_MIN_DATE = date(1970, 1, 1)
_MAX_DATE = date(2100, 12, 31)


def _sanitize_ticker(ticker: str) -> str:
    """
    Validate and normalize a ticker symbol.

    Args:
        ticker: Raw ticker string provided by the caller.

    Returns:
        Uppercased, stripped ticker string.

    Raises:
        FetcherError: If the ticker fails format validation.
    """
    if not isinstance(ticker, str):
        raise FetcherError("Ticker must be a string.")

    sanitized = ticker.strip().upper()

    if not sanitized:
        raise FetcherError("Ticker must not be empty.")

    if not _TICKER_RE.match(sanitized):
        raise FetcherError(
            f"Invalid ticker format: '{sanitized}'. "
            "Only letters, digits, hyphens, equals signs, and dots are allowed "
            "(max 20 characters)."
        )

    return sanitized


def _parse_date(value: str | date | None, param_name: str) -> str | None:
    """
    Parse and validate a date parameter.

    Accepts ISO-8601 strings (YYYY-MM-DD) or date objects.
    Rejects anything outside the plausible trading date range.

    Args:
        value: Date as string, date object, or None.
        param_name: Parameter name used in error messages.

    Returns:
        ISO-8601 string or None.

    Raises:
        FetcherError: If the value is not a valid date or is out of range.
    """
    if value is None:
        return None

    if isinstance(value, datetime):
        parsed: date = value.date()
    elif isinstance(value, date):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = date.fromisoformat(value)
        except ValueError:
            raise FetcherError(
                f"Invalid date for '{param_name}': '{value}'. "
                "Expected ISO-8601 format YYYY-MM-DD."
            )
    else:
        raise FetcherError(
            f"'{param_name}' must be a string, date, or None; "
            f"got {type(value).__name__}."
        )

    if not (_MIN_DATE <= parsed <= _MAX_DATE):
        raise FetcherError(
            f"Date '{parsed}' for '{param_name}' is outside the valid range "
            f"({_MIN_DATE} – {_MAX_DATE})."
        )

    return parsed.isoformat()


def _fetch_history(
    ticker: str,
    start: str | date | None = None,
    end: str | date | None = None,
    period: str | None = "1y",
) -> pd.DataFrame:
    """
    Internal: fetch full OHLCV DataFrame via yfinance with caching.

    Returns the raw DataFrame (Close, Volume, etc.) so that public functions
    can extract the column they need without duplicate network calls.
    """
    clean_ticker = _sanitize_ticker(ticker)
    start_str = _parse_date(start, "start")
    end_str = _parse_date(end, "end")

    cache_key = hashkey(clean_ticker, start_str, end_str, period or "1y")
    with _price_cache_lock:
        if cache_key in _price_cache:
            return _price_cache[cache_key]  # type: ignore[return-value]

    _VALID_PERIODS = {
        "1d", "5d", "1mo", "3mo", "6mo",
        "1y", "2y", "5y", "10y", "ytd", "max",
    }
    if period is not None and period not in _VALID_PERIODS:
        raise FetcherError(
            f"Invalid period '{period}'. "
            f"Valid values: {sorted(_VALID_PERIODS)}."
        )

    if start_str and end_str and start_str >= end_str:
        raise FetcherError(
            f"'start' ({start_str}) must be strictly before 'end' ({end_str})."
        )

    try:
        ticker_obj = yf.Ticker(clean_ticker)

        if start_str:
            df: pd.DataFrame = ticker_obj.history(
                start=start_str,
                end=end_str or date.today().isoformat(),
                auto_adjust=True,
            )
        else:
            df = ticker_obj.history(
                period=period or "1y",
                auto_adjust=True,
            )
    except Exception as exc:
        raise FetcherError(
            f"Failed to fetch data for '{clean_ticker}': {exc}"
        ) from exc

    if df is None or df.empty:
        raise FetcherError(
            f"No price data returned for '{clean_ticker}'. "
            "The ticker may be invalid or delisted."
        )

    if "Close" not in df.columns:
        raise FetcherError(
            f"Unexpected response format for '{clean_ticker}': "
            "'Close' column not found."
        )

    with _price_cache_lock:
        _price_cache[cache_key] = df

    return df


def fetch_close_prices(
    ticker: str,
    start: str | date | None = None,
    end: str | date | None = None,
    period: str | None = "1y",
) -> pd.Series:
    """
    Fetch adjusted close prices for a given ticker via yfinance.

    Exactly one of ``(start/end)`` or ``period`` must drive the request:
    - If ``start`` is provided, ``period`` is ignored and a date-range query
      is used.  ``end`` defaults to today when ``start`` is given.
    - If neither ``start`` nor ``period`` is given, ``period="1y"`` is used.

    Args:
        ticker: Asset ticker symbol (e.g. ``"AAPL"``, ``"BTC-USD"``,
                ``"EURUSD=X"``).
        start:  Start date as ISO-8601 string or ``date`` object.
        end:    End date as ISO-8601 string or ``date`` object.
        period: yfinance period string (e.g. ``"1y"``, ``"6mo"``).
                Ignored when ``start`` is provided.

    Returns:
        ``pd.Series`` with a ``DatetimeIndex`` of trading days, named after
        the sanitized ticker.  Values are adjusted close prices (float).

    Raises:
        FetcherError: On invalid inputs, network failures, or empty responses.

    Examples:
        >>> prices = fetch_close_prices("AAPL", period="6mo")
        >>> prices = fetch_close_prices("BTC-USD", start="2023-01-01")
    """
    clean_ticker = _sanitize_ticker(ticker)
    df = _fetch_history(ticker, start=start, end=end, period=period)

    prices: pd.Series = df["Close"].rename(clean_ticker)

    if prices.isnull().all():
        raise FetcherError(
            f"All price values are null for '{clean_ticker}'."
        )

    return prices.dropna()


def fetch_volume(
    ticker: str,
    start: str | date | None = None,
    end: str | date | None = None,
    period: str | None = "1y",
) -> pd.Series:
    """
    Fetch trading volume for a given ticker via yfinance.

    Uses the same cached DataFrame as ``fetch_close_prices``, so calling
    both for the same ticker/period does not trigger a second network request.

    Returns:
        ``pd.Series`` with a ``DatetimeIndex``, values are daily volume (int/float).
        Returns an empty Series if volume data is not available (e.g. FX pairs).

    Raises:
        FetcherError: On invalid inputs, network failures, or empty responses.
    """
    df = _fetch_history(ticker, start=start, end=end, period=period)

    if "Volume" not in df.columns:
        return pd.Series(dtype=float, name="Volume")

    volume: pd.Series = df["Volume"].rename("Volume")
    return volume.dropna()


def fetch_ohlc(
    ticker: str,
    start: str | date | None = None,
    end: str | date | None = None,
    period: str | None = "1y",
) -> pd.DataFrame:
    """
    Fetch OHLC (Open, High, Low, Close) data for a given ticker.

    Uses the same cached DataFrame as other fetch functions.

    Returns:
        ``pd.DataFrame`` with columns [open, high, low, close] (lowercase)
        and a ``DatetimeIndex``.  Returns an empty DataFrame if OHLC
        columns are not available.

    Raises:
        FetcherError: On invalid inputs, network failures, or empty responses.
    """
    df = _fetch_history(ticker, start=start, end=end, period=period)

    required = {"Open", "High", "Low", "Close"}
    if not required.issubset(df.columns):
        return pd.DataFrame(columns=["open", "high", "low", "close"])

    ohlc = df[["Open", "High", "Low", "Close"]].copy()
    ohlc.columns = ["open", "high", "low", "close"]
    return ohlc.dropna()


# ---------------------------------------------------------------------------
# Fundamentals cache (separate from price cache)
# ---------------------------------------------------------------------------
_fundamentals_cache: TTLCache = TTLCache(maxsize=64, ttl=600)
_fundamentals_cache_lock = threading.Lock()

# Fields to extract from yfinance .info dict
_FUNDAMENTAL_FIELDS = {
    "trailingEps": "eps",
    "forwardEps": "forward_eps",
    "earningsQuarterlyGrowth": "eps_growth",
    "profitMargins": "profit_margin",
    "grossMargins": "gross_margin",
    "operatingMargins": "operating_margin",
    "debtToEquity": "debt_to_equity",
    "currentRatio": "current_ratio",
    "returnOnEquity": "roe",
    "returnOnAssets": "roa",
    "revenueGrowth": "revenue_growth",
    "marketCap": "market_cap",
    "trailingPE": "pe_ratio",
    "forwardPE": "forward_pe",
    "priceToBook": "price_to_book",
    "dividendYield": "dividend_yield",
    "sector": "sector",
    "industry": "industry",
    "longName": "company_name",
}


def fetch_fundamentals(ticker: str) -> dict:
    """
    Fetch fundamental company data for a given ticker via yfinance.

    Returns a dict with normalized field names. Values may be None
    if the field is not available for the given ticker (e.g. ETFs).

    Raises:
        FetcherError: On invalid ticker or network failures.
    """
    clean_ticker = _sanitize_ticker(ticker)

    cache_key = hashkey(clean_ticker, "fundamentals")
    with _fundamentals_cache_lock:
        if cache_key in _fundamentals_cache:
            return _fundamentals_cache[cache_key]  # type: ignore[return-value]

    try:
        ticker_obj = yf.Ticker(clean_ticker)
        info = ticker_obj.info or {}
    except Exception as exc:
        raise FetcherError(
            f"Failed to fetch fundamentals for '{clean_ticker}': {exc}"
        ) from exc

    result: dict = {}
    for yf_key, our_key in _FUNDAMENTAL_FIELDS.items():
        val = info.get(yf_key)
        result[our_key] = val if val is not None and val != "N/A" else None

    with _fundamentals_cache_lock:
        _fundamentals_cache[cache_key] = result

    return result
