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


class AskRequest(BaseModel):
    question: str
    ticker: str | None = None
    context: dict[str, Any] | None = None

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Question must not be empty.")
        return stripped

    @field_validator("ticker")
    @classmethod
    def ticker_must_be_valid(cls, v: str | None) -> str | None:
        if v is None:
            return None
        normalized = v.strip().upper()
        if not _TICKER_RE.match(normalized):
            raise ValueError(f"Invalid ticker '{v}'.")
        return normalized


class AskResponse(BaseModel):
    question: str
    answer: str
    ticker: str | None = None


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
    arima: dict[str, Any] | None = None
    warnings: list[str] = []


class ModelsTimeseriesResponse(BaseModel):
    ticker: str
    period: str
    garch_vol: list[dict[str, Any]] = []
    garch_forecast: list[dict[str, Any]] = []
    hmm_states: list[dict[str, Any]] = []
    arima_fitted: list[dict[str, Any]] = []
    arima_forecast: list[dict[str, Any]] = []
    warnings: list[str] = []


class ComparisonResponse(BaseModel):
    ticker: str
    period: str
    models: dict[str, Any] = {}
    comparison: list[dict[str, Any]] = []
    verdict: dict[str, Any] = {}
    warnings: list[str] = []


# ---------------------------------------------------------------------------
# Backtest
# ---------------------------------------------------------------------------

_VALID_BACKTEST_MODELS = frozenset({"arima", "hmm", "garch"})
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class BacktestRequest(BaseModel):
    ticker: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    models: list[str] = ["arima", "hmm", "garch"]
    initial_capital: float = 10_000.0
    arima_threshold: float = 0.0
    hmm_states: int = 3
    commission_bps: float = 0.0

    @field_validator("ticker")
    @classmethod
    def ticker_must_be_valid(cls, v: str) -> str:
        normalized = v.strip().upper()
        if not _TICKER_RE.match(normalized):
            raise ValueError(f"Invalid ticker '{v}'.")
        return normalized

    @field_validator("train_start", "train_end", "test_start", "test_end")
    @classmethod
    def dates_must_be_iso(cls, v: str) -> str:
        if not _DATE_RE.match(v):
            raise ValueError(f"Invalid date '{v}'. Use YYYY-MM-DD format.")
        return v

    @field_validator("models")
    @classmethod
    def models_must_be_valid(cls, v: list[str]) -> list[str]:
        normalized = [m.lower().strip() for m in v]
        invalid = set(normalized) - _VALID_BACKTEST_MODELS
        if invalid:
            raise ValueError(f"Invalid models: {invalid}. Valid: {sorted(_VALID_BACKTEST_MODELS)}")
        if not normalized:
            raise ValueError("At least one model is required")
        return normalized

    @field_validator("hmm_states")
    @classmethod
    def hmm_states_valid(cls, v: int) -> int:
        if v not in (2, 3):
            raise ValueError("hmm_states must be 2 or 3")
        return v

    @field_validator("initial_capital")
    @classmethod
    def capital_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("initial_capital must be positive")
        return v


class BacktestResponse(BaseModel):
    ticker: str
    train_period: dict[str, Any]
    test_period: dict[str, Any]
    models_used: list[str]
    signals: dict[str, Any]
    metrics: dict[str, Any]
    equity_curve: list[dict[str, Any]]
    benchmark_curve: list[dict[str, Any]]
    positions: list[dict[str, Any]]
    trades: list[dict[str, Any]]
    warnings: list[str] = []
