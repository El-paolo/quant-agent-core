"""
Custom middleware for the FINA API.

RequestTimingMiddleware: adds X-Process-Time-Ms header to every response.
RateLimitMiddleware:     simple in-memory per-IP rate limiter for POST endpoints.
CORS is configured in the app factory (main.py) using settings.cors_origins.
"""

import time
import threading
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Inject X-Process-Time-Ms into every response header."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory sliding-window rate limiter for POST endpoints.

    Only limits POST requests (the expensive ones — analysis, agent, timeseries).
    GET requests (health, static files) are never limited.

    Args:
        max_requests: Maximum POST requests per window per client IP.
        window_seconds: Sliding window duration in seconds.
    """

    def __init__(self, app: Any, max_requests: int = 30, window_seconds: int = 60) -> None:
        super().__init__(app)
        self._max = max_requests
        self._window = window_seconds
        self._requests: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    def _cleanup_old(self, timestamps: list[float], now: float) -> list[float]:
        cutoff = now - self._window
        return [t for t in timestamps if t > cutoff]

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        if request.method != "POST":
            return await call_next(request)

        client_ip = self._get_client_ip(request)
        now = time.monotonic()

        with self._lock:
            timestamps = self._requests.get(client_ip, [])
            timestamps = self._cleanup_old(timestamps, now)

            if len(timestamps) >= self._max:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests. Try again shortly."},
                    headers={"Retry-After": str(self._window)},
                )

            timestamps.append(now)
            self._requests[client_ip] = timestamps

        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add standard security headers to every response."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response
