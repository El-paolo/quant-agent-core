"""POST /backtest/ — backtesting endpoint."""

import asyncio

from fastapi import APIRouter, HTTPException

from fina.api.schemas import BacktestRequest, BacktestResponse
from fina.core.exceptions import BacktestError, FetcherError, MetricsError
from fina.orchestration.backtest import run_backtest_orchestrated

router = APIRouter(tags=["backtest"])


@router.post("/", response_model=BacktestResponse)
async def backtest_run(request: BacktestRequest) -> BacktestResponse:
    """
    Run a full backtest with user-defined train/test periods.

    Trains models on the training period, generates signals on the
    test period, simulates a strategy, and returns performance metrics
    compared against buy-and-hold.
    """
    try:
        result = await asyncio.to_thread(
            run_backtest_orchestrated,
            ticker=request.ticker,
            train_start=request.train_start,
            train_end=request.train_end,
            test_start=request.test_start,
            test_end=request.test_end,
            models=request.models,
            initial_capital=request.initial_capital,
            arima_threshold=request.arima_threshold,
            hmm_states=request.hmm_states,
            commission_bps=request.commission_bps,
        )
    except (FetcherError, BacktestError, MetricsError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal backtest error")

    return BacktestResponse(**result)
