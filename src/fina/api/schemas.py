"""
Pydantic v2 request and response models for the FINA API.

All input validation happens here — routes receive already-validated objects.
No business logic lives in schemas; they only define shapes and constraints.
"""

import re
from typing import Any

from pydantic import BaseModel, field_validator

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TICKER_RE = re.compile(r"^[A-Z0-9\-=\.]{1,20}$")

_KNOWN_METRICS = frozenset(
    {"returns", "volatility", "rolling_volatility", "sharpe", "sortino", "rsi", "macd", "bollinger"}
)

_VALID_PERIODS = frozenset(
    {"1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"}
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class AnalysisRequest(BaseModel):
    ticker: str
    period: str = "1y"
    metrics: list[str] = list(_KNOWN_METRICS)

    @field_validator("ticker")
    @classmethod
    def ticker_must_be_valid(cls, v: str) -> str:
        normalized = v.strip().upper()
        if not _TICKER_RE.match(normalized):
            raise ValueError(
                f"Invalid ticker '{v}'. Must match pattern [A-Z0-9\\-=\\.] "
                "with length 1–20."
            )
        return normalized

    @field_validator("period")
    @classmethod
    def period_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_PERIODS:
            raise ValueError(
                f"Invalid period '{v}'. Valid options: {sorted(_VALID_PERIODS)}."
            )
        return v

    @field_validator("metrics")
    @classmethod
    def metrics_must_be_known(cls, v: list[str]) -> list[str]:
        unknown = set(v) - _KNOWN_METRICS
        if unknown:
            raise ValueError(
                f"Unknown metrics: {unknown}. "
                f"Valid options: {sorted(_KNOWN_METRICS)}."
            )
        return v


class AgentRequest(BaseModel):
    ticker: str
    summary_prompt: str | None = None

    @field_validator("ticker")
    @classmethod
    def ticker_must_be_valid(cls, v: str) -> str:
        normalized = v.strip().upper()
        if not _TICKER_RE.match(normalized):
            raise ValueError(f"Invalid ticker '{v}'.")
        return normalized


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    version: str


class MetricsPayload(BaseModel):
    ticker: str
    period: str
    computed: dict[str, Any]
    warnings: list[str] = []


class AnalysisResponse(BaseModel):
    status: str
    data: MetricsPayload


class AgentResponse(BaseModel):
    ticker: str
    summary: str
    headlines: list[str]
