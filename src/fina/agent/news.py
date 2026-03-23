"""
NewsAPI fetcher — retrieves recent headlines for a given query.

Uses httpx (synchronous) so it fits naturally in the synchronous
orchestration pipeline. All HTTP errors are wrapped in FetcherError.

Security notes:
  - The API key is never logged or included in error messages.
  - Query strings are passed as URL parameters (httpx handles encoding),
    never interpolated into URLs directly.
  - max_articles is bounded to prevent oversized responses.
"""

import threading

import httpx
from cachetools import TTLCache
from cachetools.keys import hashkey

from fina.core.config import Settings
from fina.core.exceptions import FetcherError

_NEWSAPI_BASE = "https://newsapi.org/v2/top-headlines"
_MAX_ARTICLES_CAP = 100   # NewsAPI hard limit per page
_DEFAULT_MAX = 10

# ---------------------------------------------------------------------------
# Cache — evita llamadas repetidas a NewsAPI para la misma query.
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
    Fetch recent news headlines for a query via NewsAPI.

    Args:
        query:        Search query (e.g. ticker symbol or company name).
        settings:     Application settings — must contain a valid news_api_key.
        max_articles: Maximum number of articles to return (capped at 100).

    Returns:
        List of article dicts, each with keys:
          ``title``, ``description``, ``url``, ``publishedAt``.
        Articles without a title are silently skipped.

    Raises:
        ConfigError:  If news_api_key is not set (via validate_for_agent).
        FetcherError: On HTTP errors, timeout, or non-ok NewsAPI status.
    """
    settings.validate_for_agent()

    page_size = min(max_articles, _MAX_ARTICLES_CAP)

    # --- Cache lookup ---
    cache_key = hashkey(query, page_size)
    with _news_cache_lock:
        if cache_key in _news_cache:
            return _news_cache[cache_key]  # type: ignore[return-value]

    params = {
        "q": query,
        "apiKey": settings.news_api_key,
        "pageSize": page_size,
        "sortBy": "publishedAt",
        "language": "en",
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(_NEWSAPI_BASE, params=params)
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise FetcherError(
            f"NewsAPI HTTP error {exc.response.status_code}: {exc}"
        ) from exc
    except httpx.TimeoutException as exc:
        raise FetcherError(f"NewsAPI request timed out: {exc}") from exc
    except httpx.RequestError as exc:
        raise FetcherError(f"NewsAPI request failed: {exc}") from exc

    data = response.json()

    if data.get("status") != "ok":
        raise FetcherError(
            f"NewsAPI returned non-ok status: {data.get('message', 'unknown error')}"
        )

    articles = data.get("articles", [])[:max_articles]

    result = [
        {
            "title": a.get("title", ""),
            "description": a.get("description", "") or "",
            "url": a.get("url", "") or "",
            "publishedAt": a.get("publishedAt", "") or "",
        }
        for a in articles
        if a.get("title")  # skip articles with no title
    ]

    # --- Store in cache ---
    with _news_cache_lock:
        _news_cache[cache_key] = result

    return result
