"""POST /backtest/, /backtest/montecarlo/, /backtest/portfolio/ — backtesting endpoints."""

import asyncio

from fastapi import APIRouter, HTTPException

from fina.api.schemas import (
    BacktestPortfolioRequest,
    BacktestPortfolioResponse,
    BacktestRequest,
    BacktestResponse,
    MonteCarloRequest,
    MonteCarloResponse,
)
from fina.core.exceptions import BacktestError, FetcherError, MetricsError
from fina.orchestration.backtest import (
    run_backtest_orchestrated,
    run_montecarlo_orchestrated,
    run_portfolio_backtest_orchestrated,
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
    if len(request.tickers) > 1:
        raise HTTPException(
            status_code=422,
            detail="Multi-ticker backtest available via POST /backtest/portfolio/.",
        )

    try:
        result = await asyncio.to_thread(
            run_backtest_orchestrated,
            ticker=request.first_ticker,
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
    if len(request.tickers) > 1:
        raise HTTPException(
            status_code=422,
            detail="Multi-ticker Monte Carlo not yet supported.",
        )

    try:
        result = await asyncio.to_thread(
            run_montecarlo_orchestrated,
            ticker=request.first_ticker,
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


@router.post("/portfolio/", response_model=BacktestPortfolioResponse)
async def portfolio_backtest_run(
    request: BacktestPortfolioRequest,
) -> BacktestPortfolioResponse:
    """
    Run a portfolio backtest across multiple tickers.

    Runs per-asset signal generation and strategy simulation, then
    combines equity curves using the chosen weighting scheme.
    Optionally applies cross-sectional signals (momentum or pairs).
    """
    try:
        result = await asyncio.to_thread(
            run_portfolio_backtest_orchestrated,
            tickers=request.tickers,
            train_start=request.train_start,
            train_end=request.train_end,
            test_start=request.test_start,
            test_end=request.test_end,
            models=request.models,
            weight_scheme=request.weight_scheme,
            custom_weights=request.custom_weights,
            cross_signal=request.cross_signal,
            cross_signal_params=request.cross_signal_params or {},
            initial_capital=request.initial_capital,
            arima_threshold=request.arima_threshold,
            hmm_states=request.hmm_states,
            commission_bps=request.commission_bps,
        )
    except (FetcherError, BacktestError, MetricsError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal portfolio backtest error")

    return BacktestPortfolioResponse(**result)
