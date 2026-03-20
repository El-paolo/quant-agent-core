"""POST /analysis/ — run financial metrics pipeline for a ticker."""

from fastapi import APIRouter, HTTPException

from fina.api.dependencies import SettingsDep
from fina.api.schemas import AnalysisRequest, AnalysisResponse, MetricsPayload
from fina.core.exceptions import FetcherError, MetricsError, ValidationError
from fina.orchestration.analysis import run_analysis

router = APIRouter(tags=["analysis"])


@router.post("/", response_model=AnalysisResponse, status_code=200)
async def analyze(
    request: AnalysisRequest,
    settings: SettingsDep,
) -> AnalysisResponse:
    """
    Fetch prices and compute the requested financial metrics for a ticker.

    Raises HTTP 422 for bad input or data issues, 500 for unexpected errors.
    """
    try:
        result = run_analysis(
            ticker=request.ticker,
            period=request.period,
            metrics=request.metrics,
        )
    except (FetcherError, MetricsError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Internal analysis error")

    return AnalysisResponse(
        status="ok",
        data=MetricsPayload(
            ticker=request.ticker,
            period=request.period,
            computed=result,
        ),
    )
