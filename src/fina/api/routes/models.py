"""POST /models/, /models/timeseries/, /models/compare/ — quantitative model endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException

from fina.api.schemas import (
    ComparisonResponse,
    ModelsRequest,
    ModelsResponse,
    ModelsTimeseriesResponse,
)
from fina.core.exceptions import FetcherError, MetricsError, ValidationError
from fina.orchestration.models import run_comparison, run_models, run_models_timeseries

router = APIRouter(tags=["models"])


@router.post("/", response_model=ModelsResponse)
async def models_summary(request: ModelsRequest) -> ModelsResponse:
    """
    Run GARCH, HMM, and ARIMA models on a ticker and return summary results.
    """
    try:
        result = await asyncio.to_thread(
            run_models,
            ticker=request.first_ticker,
            period=request.period,
            garch_horizon=request.garch_horizon,
            hmm_states=request.hmm_states,
        )
    except (FetcherError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal models error")

    return ModelsResponse(
        ticker=request.first_ticker,
        period=request.period,
        garch=result.get("garch"),
        hmm=result.get("hmm"),
        arima=result.get("arima"),
        warnings=result.get("warnings", []),
    )


@router.post("/timeseries/", response_model=ModelsTimeseriesResponse)
async def models_timeseries(request: ModelsRequest) -> ModelsTimeseriesResponse:
    """
    Run models and return full time series for charting.
    """
    try:
        result = await asyncio.to_thread(
            run_models_timeseries,
            ticker=request.first_ticker,
            period=request.period,
            garch_horizon=request.garch_horizon,
            hmm_states=request.hmm_states,
        )
    except (FetcherError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal models timeseries error")

    return ModelsTimeseriesResponse(
        ticker=request.first_ticker,
        period=request.period,
        garch_vol=result.get("garch_vol", []),
        garch_forecast=result.get("garch_forecast", []),
        hmm_states=result.get("hmm_states", []),
        arima_fitted=result.get("arima_fitted", []),
        arima_forecast=result.get("arima_forecast", []),
        warnings=result.get("warnings", []),
    )


@router.post("/compare/", response_model=ComparisonResponse)
async def models_compare(request: ModelsRequest) -> ComparisonResponse:
    """
    Run ARIMA and GARCH side-by-side and return a comparison table with verdict.
    """
    try:
        result = await asyncio.to_thread(
            run_comparison,
            ticker=request.first_ticker,
            period=request.period,
            horizon=request.garch_horizon,
        )
    except (FetcherError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal comparison error")

    return ComparisonResponse(
        ticker=request.first_ticker,
        period=request.period,
        models=result.get("models", {}),
        comparison=result.get("comparison", []),
        verdict=result.get("verdict", {}),
        warnings=result.get("warnings", []),
    )
