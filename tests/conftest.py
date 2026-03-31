"""
Shared fixtures for the FINA test suite.

All fixtures use deterministic seeds and in-memory data — no external API
calls are made from this file.
"""

import numpy as np
import pandas as pd
import pytest

from fina.metrics.returns import simple_returns, log_returns
from fina.data.fetcher import configure_price_cache
from fina.agent.news import configure_news_cache


@pytest.fixture(autouse=True)
def reset_caches() -> None:
    """Reset all module-level caches before every test for isolation."""
    configure_price_cache()
    configure_news_cache()


@pytest.fixture
def sample_prices() -> pd.Series:
    """
    Deterministic price series (252 trading days) for reproducible tests.

    Uses a fixed random seed so every test run produces identical values.
    Prices follow a log-normal random walk starting at 100.
    """
    dates = pd.date_range("2023-01-01", periods=252, freq="B")
    rng = np.random.default_rng(42)
    prices = pd.Series(
        100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, 252))),
        index=dates,
        name="TEST",
        dtype=float,
    )
    return prices


@pytest.fixture
def sample_returns(sample_prices: pd.Series) -> pd.Series:
    """Simple returns derived from the deterministic price fixture."""
    return simple_returns(sample_prices)


@pytest.fixture
def sample_log_returns(sample_prices: pd.Series) -> pd.Series:
    """Log returns derived from the deterministic price fixture (251 obs)."""
    return log_returns(sample_prices)


@pytest.fixture
def single_price() -> pd.Series:
    """A single-element price series — useful for testing edge cases."""
    return pd.Series(
        [100.0],
        index=pd.date_range("2023-01-01", periods=1, freq="B"),
        name="TEST",
    )


@pytest.fixture
def prices_with_nan() -> pd.Series:
    """Price series containing NaN values — should trigger validation errors."""
    dates = pd.date_range("2023-01-01", periods=5, freq="B")
    return pd.Series([100.0, 101.0, float("nan"), 103.0, 104.0], index=dates, name="TEST")


@pytest.fixture
def prices_with_negatives() -> pd.Series:
    """Price series containing non-positive values — should trigger validation errors."""
    dates = pd.date_range("2023-01-01", periods=5, freq="B")
    return pd.Series([100.0, 101.0, -5.0, 103.0, 104.0], index=dates, name="TEST")
