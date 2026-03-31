"""
Yahoo Finance news fetcher — retrieves recent headlines for a given ticker.

Uses yfinance (no API key required) so news fetching is free and unlimited.
All errors are wrapped in FetcherError.

Security notes:
  - No API keys required or used.
  - Ticker symbols are passed directly to yfinance, never interpolated into
    shell commands or SQL queries.
  - max_articles is bounded to prevent oversized responses.
"""

import threading

import yfinance as yf
from cachetools import TTLCache
from cachetools.keys import hashkey

from fina.core.config import Settings
from fina.core.exceptions import FetcherError

_MAX_ARTICLES_CAP = 100
_DEFAULT_MAX = 10

# ---------------------------------------------------------------------------
# Cache — evita llamadas repetidas a Yahoo Finance para el mismo ticker.
# TTL default 15 min; configurable via configure_news_cache() en app startup.
# ---------------------------------------------------------------------------
_news_cache: TTLCache = TTLCache(maxsize=128, ttl=900)
_news_cache_lock = threading.Lock()


def configure_news_cache(ttl: int = 900, maxsize: int = 128) -> None:
    """
    Reconfigure el cache de noticias.

    Llamar una vez en el startup de la app (create_app) con valores de Settings.

    Args:
        ttl:     Time-to-live en segundos. Default: 900 (15 min).
        maxsize: Máximo de entradas en cache. Default: 128.
    """
    global _news_cache
    with _news_cache_lock:
        _news_cache = TTLCache(maxsize=maxsize, ttl=ttl)


def fetch_news_headlines(
    query: str,
    settings: Settings,
    *,
    max_articles: int = _DEFAULT_MAX,
) -> list[dict]:
    """
    Fetch recent news headlines for a ticker via Yahoo Finance (yfinance).

    No API key required.

    Args:
        query:        Ticker symbol (e.g. "AAPL").
        settings:     Application settings (used downstream by the summarizer).
        max_articles: Maximum number of articles to return (capped at 100).

    Returns:
        List of article dicts, each with keys:
          ``title``, ``description``, ``url``, ``publishedAt``.
        Articles without a title are silently skipped.

    Raises:
        FetcherError: On any yfinance or network error.
    """
    limit = min(max_articles, _MAX_ARTICLES_CAP)

    # --- Cache lookup ---
    cache_key = hashkey(query, limit)
    with _news_cache_lock:
        if cache_key in _news_cache:
            return _news_cache[cache_key]  # type: ignore[return-value]

    try:
        raw_articles = yf.Ticker(query).news[:limit]
    except Exception as exc:
        raise FetcherError(f"Yahoo Finance news fetch failed: {exc}") from exc

    result = [
        {
            "title": (c := a.get("content", {})).get("title", ""),
            "description": c.get("summary", "") or "",
            "url": (c.get("canonicalUrl") or {}).get("url", "") or "",
            "publishedAt": c.get("pubDate", "") or "",
        }
        for a in raw_articles
        if (c := a.get("content", {})) and c.get("title")
    ]

    # --- Store in cache ---
    with _news_cache_lock:
        _news_cache[cache_key] = result

    return result
