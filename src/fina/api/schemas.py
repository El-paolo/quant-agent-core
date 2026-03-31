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
    {"returns", "volatility", "rolling_volatility", "sharpe", "sortino", "rsi", "macd", "bollinger", "beta"}
)

_KNOWN_TIMESERIES = frozenset(
    {"rolling_volatility", "rsi", "macd", "bollinger", "returns", "prices", "volume", "ohlc"}
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


class TimeseriesRequest(BaseModel):
    ticker: str
    period: str = "1y"
    series: list[str] = list(_KNOWN_TIMESERIES)

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

    @field_validator("series")
    @classmethod
    def series_must_be_known(cls, v: list[str]) -> list[str]:
        unknown = set(v) - _KNOWN_TIMESERIES
        if unknown:
            raise ValueError(
                f"Unknown series: {unknown}. "
                f"Valid options: {sorted(_KNOWN_TIMESERIES)}."
            )
        return v


class TimeseriesResponse(BaseModel):
    ticker: str
    period: str
    series: dict[str, Any]
    warnings: list[str] = []


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


# ---------------------------------------------------------------------------
# Models (GARCH, HMM)
# ---------------------------------------------------------------------------


class ModelsRequest(BaseModel):
    ticker: str
    period: str = "1y"
    garch_horizon: int = 5
    hmm_states: int = 3

    @field_validator("ticker")
    @classmethod
    def ticker_must_be_valid(cls, v: str) -> str:
        normalized = v.strip().upper()
        if not _TICKER_RE.match(normalized):
            raise ValueError(f"Invalid ticker '{v}'.")
        return normalized

    @field_validator("period")
    @classmethod
    def period_must_be_valid(cls, v: str) -> str:
        if v not in _VALID_PERIODS:
            raise ValueError(
                f"Invalid period '{v}'. Valid options: {sorted(_VALID_PERIODS)}."
            )
        return v

    @field_validator("hmm_states")
    @classmethod
    def hmm_states_valid(cls, v: int) -> int:
        if v not in (2, 3):
            raise ValueError("hmm_states must be 2 or 3")
        return v


class ModelsResponse(BaseModel):
    ticker: str
    period: str
    garch: dict[str, Any] | None = None
    hmm: dict[str, Any] | None = None
    warnings: list[str] = []


class ModelsTimeseriesResponse(BaseModel):
    ticker: str
    period: str
    garch_vol: list[dict[str, Any]] = []
    garch_forecast: list[dict[str, Any]] = []
    hmm_states: list[dict[str, Any]] = []
    warnings: list[str] = []
