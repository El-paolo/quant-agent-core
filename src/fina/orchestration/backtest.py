"""
Backtest orchestration — wraps the backtest engine with error handling.

Follows the same pattern as models.py: catch known exceptions and
return structured error responses.
"""

from fina.backtest.engine import run_backtest
from fina.core.exceptions import BacktestError, FetcherError


def run_backtest_orchestrated(
    ticker: str,
    train_start: str,
    train_end: str,
    test_start: str,
    test_end: str,
    **kwargs,
) -> dict:
    """
    Run a backtest with graceful error handling.

    Raises:
        FetcherError: Re-raised (HTTP 422 in route layer).
        BacktestError: Re-raised (HTTP 422 in route layer).
        Exception: Unexpected errors re-raised for 500 handling.
    """
    return run_backtest(
        ticker=ticker,
        train_start=train_start,
        train_end=train_end,
        test_start=test_start,
        test_end=test_end,
        **kwargs,
    )
