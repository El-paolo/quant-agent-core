"""POST /models/ and /models/timeseries/ — quantitative model endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException

from fina.api.schemas import (
    ModelsRequest,
    ModelsResponse,
    ModelsTimeseriesResponse,
)
from fina.core.exceptions import FetcherError, MetricsError, ValidationError
from fina.orchestration.models import run_models, run_models_timeseries

router = APIRouter(tags=["models"])


@router.post("/", response_model=ModelsResponse)
async def models_summary(request: ModelsRequest) -> ModelsResponse:
    """
    Run GARCH and HMM models on a ticker and return summary results.

    Returns scalar diagnostics, forecasts, and current regime.
    """
    try:
        result = await asyncio.to_thread(
            run_models,
            ticker=request.ticker,
            period=request.period,
            garch_horizon=request.garch_horizon,
            hmm_states=request.hmm_states,
        )
    except (FetcherError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal models error")

    return ModelsResponse(
        ticker=request.ticker,
        period=request.period,
        garch=result.get("garch"),
        hmm=result.get("hmm"),
        warnings=result.get("warnings", []),
    )


@router.post("/timeseries/", response_model=ModelsTimeseriesResponse)
async def models_timeseries(request: ModelsRequest) -> ModelsTimeseriesResponse:
    """
    Run GARCH and HMM models and return full time series for charting.

    Returns conditional volatility series and regime state sequence.
    """
    try:
        result = await asyncio.to_thread(
            run_models_timeseries,
            ticker=request.ticker,
            period=request.period,
            garch_horizon=request.garch_horizon,
            hmm_states=request.hmm_states,
        )
    except (FetcherError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal models timeseries error")

    return ModelsTimeseriesResponse(
        ticker=request.ticker,
        period=request.period,
        garch_vol=result.get("garch_vol", []),
        garch_forecast=result.get("garch_forecast", []),
        hmm_states=result.get("hmm_states", []),
        warnings=result.get("warnings", []),
    )
