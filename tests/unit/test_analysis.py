"""
Unit tests for fina.orchestration.analysis

All external calls (fetch_close_prices, clean_prices) are monkeypatched.
Tests verify orchestration logic, metric presence, and JSON serializability.
"""

import json

import numpy as np
import pandas as pd
import pytest

from fina.core.exceptions import FetcherError, MetricsError
from fina.orchestration.analysis import run_analysis

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_N = 252


def _make_prices(n: int = _N, seed: int = 42) -> pd.Series:
    dates = pd.date_range("2023-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed)
    return pd.Series(
        100.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n))),
        index=dates,
        name="TEST",
        dtype=float,
    )


@pytest.fixture(autouse=True)
def mock_fetcher(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace fetch_close_prices and clean_prices for all tests in this file."""
    prices = _make_prices()

    monkeypatch.setattr(
        "fina.orchestration.analysis.fetch_close_prices",
        lambda ticker, period="1y": prices,
    )
    monkeypatch.setattr(
        "fina.orchestration.analysis.clean_prices",
        lambda p, **kw: p,
    )


# ---------------------------------------------------------------------------
# Return type and shape
# ---------------------------------------------------------------------------


class TestRunAnalysisShape:
    def test_returns_dict(self) -> None:
        result = run_analysis("AAPL")
        assert isinstance(result, dict)

    def test_always_has_warnings_key(self) -> None:
        result = run_analysis("AAPL")
        assert "warnings" in result
        assert isinstance(result["warnings"], list)

    def test_default_includes_all_metrics(self) -> None:
        result = run_analysis("AAPL")
        for key in ("returns", "volatility", "sharpe", "sortino", "rsi", "macd", "bollinger"):
            assert key in result

    def test_only_requested_metrics_returned(self) -> None:
        result = run_analysis("AAPL", metrics=["returns", "sharpe"])
        assert "returns" in result
        assert "sharpe" in result
        assert "volatility" not in result
        assert "rsi" not in result

    def test_empty_metrics_list_returns_only_warnings(self) -> None:
        result = run_analysis("AAPL", metrics=[])
        assert list(result.keys()) == ["warnings"]


# ---------------------------------------------------------------------------
# JSON serializability (critical — FastAPI serializes this)
# ---------------------------------------------------------------------------


class TestJSONSerializability:
    def test_returns_metric_is_serializable(self) -> None:
        result = run_analysis("AAPL", metrics=["returns"])
        json.dumps(result)

    def test_volatility_metric_is_serializable(self) -> None:
        result = run_analysis("AAPL", metrics=["volatility"])
        json.dumps(result)

    def test_sharpe_metric_is_serializable(self) -> None:
        result = run_analysis("AAPL", metrics=["sharpe"])
        json.dumps(result)

    def test_sortino_metric_is_serializable(self) -> None:
        result = run_analysis("AAPL", metrics=["sortino"])
        json.dumps(result)

    def test_rsi_metric_is_serializable(self) -> None:
        result = run_analysis("AAPL", metrics=["rsi"])
        json.dumps(result)

    def test_macd_metric_is_serializable(self) -> None:
        result = run_analysis("AAPL", metrics=["macd"])
        json.dumps(result)

    def test_bollinger_metric_is_serializable(self) -> None:
        result = run_analysis("AAPL", metrics=["bollinger"])
        json.dumps(result)

    def test_full_result_is_serializable(self) -> None:
        result = run_analysis("AAPL")
        json.dumps(result)


# ---------------------------------------------------------------------------
# Individual metric shapes
# ---------------------------------------------------------------------------


class TestReturnsMetric:
    def test_has_required_keys(self) -> None:
        result = run_analysis("AAPL", metrics=["returns"])
        r = result["returns"]
        for key in ("method", "observations", "mean", "std", "min", "max"):
            assert key in r

    def test_observations_is_int(self) -> None:
        result = run_analysis("AAPL", metrics=["returns"])
        assert isinstance(result["returns"]["observations"], int)

    def test_observations_matches_input(self) -> None:
        result = run_analysis("AAPL", metrics=["returns"])
        assert result["returns"]["observations"] == _N - 1  # log returns loses one


class TestVolatilityMetric:
    def test_has_volatility_sd_key(self) -> None:
        result = run_analysis("AAPL", metrics=["volatility"])
        assert "volatility(s.d.)" in result["volatility"]

    def test_volatility_is_positive(self) -> None:
        result = run_analysis("AAPL", metrics=["volatility"])
        assert result["volatility"]["volatility(s.d.)"] > 0


class TestSharpeMetric:
    def test_has_sharpe_ratio_key(self) -> None:
        result = run_analysis("AAPL", metrics=["sharpe"])
        assert "sharpe_ratio" in result["sharpe"]

    def test_sharpe_is_float(self) -> None:
        result = run_analysis("AAPL", metrics=["sharpe"])
        assert isinstance(result["sharpe"]["sharpe_ratio"], float)


class TestSortinoMetric:
    def test_sortino_present_for_mixed_returns(self) -> None:
        result = run_analysis("AAPL", metrics=["sortino"])
        # sample_prices has mixed positive/negative returns → sortino defined
        assert result["sortino"] is not None
        assert "sortino_ratio" in result["sortino"]

    def test_sortino_none_when_no_downside(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """All-positive returns → Sortino undefined → result is None + warning."""
        dates = pd.date_range("2023-01-01", periods=100, freq="B")
        all_up = pd.Series(
            100.0 * np.exp(np.cumsum([0.001] * 100)), index=dates, name="UP"
        )
        monkeypatch.setattr(
            "fina.orchestration.analysis.fetch_close_prices",
            lambda t, period="1y": all_up,
        )
        result = run_analysis("FAKE", metrics=["sortino"])
        assert result["sortino"] is None
        assert any("Sortino" in w for w in result["warnings"])


class TestRSIMetric:
    def test_has_latest_key(self) -> None:
        result = run_analysis("AAPL", metrics=["rsi"])
        assert "latest" in result["rsi"]

    def test_rsi_in_valid_range(self) -> None:
        result = run_analysis("AAPL", metrics=["rsi"])
        v = result["rsi"]["latest"]
        assert v is None or 0.0 <= v <= 100.0


class TestMACDMetric:
    def test_has_required_keys(self) -> None:
        result = run_analysis("AAPL", metrics=["macd"])
        for key in ("macd", "signal", "histogram"):
            assert key in result["macd"]

    def test_histogram_equals_macd_minus_signal(self) -> None:
        result = run_analysis("AAPL", metrics=["macd"])
        m = result["macd"]
        assert abs(m["histogram"] - (m["macd"] - m["signal"])) < 1e-9


class TestBollingerMetric:
    def test_has_required_keys(self) -> None:
        result = run_analysis("AAPL", metrics=["bollinger"])
        for key in ("upper", "middle", "lower", "bandwidth", "percent_b"):
            assert key in result["bollinger"]

    def test_upper_ge_middle_ge_lower(self) -> None:
        result = run_analysis("AAPL", metrics=["bollinger"])
        b = result["bollinger"]
        assert b["upper"] >= b["middle"] >= b["lower"]


# ---------------------------------------------------------------------------
# Error propagation
# ---------------------------------------------------------------------------


class TestErrorPropagation:
    def test_fetcher_error_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "fina.orchestration.analysis.fetch_close_prices",
            lambda *a, **kw: (_ for _ in ()).throw(FetcherError("no data")),
        )
        with pytest.raises(FetcherError):
            run_analysis("AAPL")

    def test_beta_fetch_failure_becomes_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Beta uses a second fetch for SPY. If that fails, it's a warning, not a crash."""
        prices = _make_prices()
        call_count = {"n": 0}

        def selective_fetch(ticker: str, period: str = "1y") -> pd.Series:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return prices  # first call: asset
            raise FetcherError("SPY unavailable")  # second call: benchmark

        monkeypatch.setattr("fina.orchestration.analysis.fetch_close_prices", selective_fetch)
        result = run_analysis("AAPL", metrics=["beta"])
        assert result["beta"] is None
        assert any("Beta" in w or "beta" in w.lower() for w in result["warnings"])


# ---------------------------------------------------------------------------
# Outlier warning
# ---------------------------------------------------------------------------


class TestOutlierWarning:
    def test_outlier_warning_added_when_detected(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        prices = _make_prices()

        def fake_clean(p: pd.Series, **kw: object) -> pd.Series:
            p.attrs["outlier_count"] = 3
            return p

        monkeypatch.setattr("fina.orchestration.analysis.clean_prices", fake_clean)
        result = run_analysis("AAPL", metrics=["returns"])
        assert any("outlier" in w.lower() for w in result["warnings"])

    def test_no_warning_when_no_outliers(self) -> None:
        result = run_analysis("AAPL", metrics=["returns"])
        outlier_warnings = [w for w in result["warnings"] if "outlier" in w.lower()]
        assert len(outlier_warnings) == 0
