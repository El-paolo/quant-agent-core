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
from datetime import date, datetime

import pandas as pd
import yfinance as yf

from fina.core.exceptions import FetcherError

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
    # --- Input validation (security boundary) ---
    clean_ticker = _sanitize_ticker(ticker)
    start_str = _parse_date(start, "start")
    end_str = _parse_date(end, "end")

    # Validate period if provided
    _VALID_PERIODS = {
        "1d", "5d", "1mo", "3mo", "6mo",
        "1y", "2y", "5y", "10y", "ytd", "max",
    }
    if period is not None and period not in _VALID_PERIODS:
        raise FetcherError(
            f"Invalid period '{period}'. "
            f"Valid values: {sorted(_VALID_PERIODS)}."
        )

    # Validate date ordering when both are given
    if start_str and end_str and start_str >= end_str:
        raise FetcherError(
            f"'start' ({start_str}) must be strictly before 'end' ({end_str})."
        )

    # --- Fetch ---
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

    # --- Validate response ---
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

    prices: pd.Series = df["Close"].rename(clean_ticker)

    if prices.isnull().all():
        raise FetcherError(
            f"All price values are null for '{clean_ticker}'."
        )

    # Drop any trailing NaNs from yfinance padding
    prices = prices.dropna()

    return prices
