"""POST /backtest/ and POST /backtest/montecarlo/ — backtesting endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException

from fina.api.schemas import (
    BacktestRequest,
    BacktestResponse,
    MonteCarloRequest,
    MonteCarloResponse,
)
from fina.core.exceptions import BacktestError, FetcherError, MetricsError
from fina.orchestration.backtest import (
    run_backtest_orchestrated,
    run_montecarlo_orchestrated,
)

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


@router.post("/montecarlo/", response_model=MonteCarloResponse)
async def montecarlo_run(request: MonteCarloRequest) -> MonteCarloResponse:
    """
    Run N Monte Carlo simulations using GARCH parametric path generation.

    Fits models once on the training period, then generates N synthetic
    return paths and runs the full strategy on each. Returns a percentile
    fan chart and risk metric distributions (VaR, CVaR, prob_profit).
    """
    try:
        result = await asyncio.to_thread(
            run_montecarlo_orchestrated,
            ticker=request.ticker,
            train_start=request.train_start,
            train_end=request.train_end,
            test_start=request.test_start,
            test_end=request.test_end,
            n_simulations=request.n_simulations,
            models=request.models,
            initial_capital=request.initial_capital,
            arima_threshold=request.arima_threshold,
            hmm_states=request.hmm_states,
            commission_bps=request.commission_bps,
        )
    except (FetcherError, BacktestError, MetricsError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal Monte Carlo error")

    return MonteCarloResponse(**result)
