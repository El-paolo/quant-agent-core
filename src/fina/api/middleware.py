"""
Custom middleware for the FINA API.

RequestTimingMiddleware: adds X-Process-Time-Ms header to every response.
CORS is configured in the app factory (main.py) using settings.cors_origins.
"""

import time
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestTimingMiddleware(BaseHTTPMiddleware):
    """Inject X-Process-Time-Ms into every response header."""

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        start = time.perf_counter()
        response: Response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        response.headers["X-Process-Time-Ms"] = f"{duration_ms:.2f}"
        return response
