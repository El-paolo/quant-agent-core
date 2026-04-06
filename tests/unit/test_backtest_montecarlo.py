"""
Unit tests for fina.backtest.montecarlo

Covers: GARCH path simulation, _fit_models, _aggregate, run_montecarlo
(with mocked fetcher), and the /backtest/montecarlo/ route.
"""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from fina.core.exceptions import BacktestError


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_prices():
    """500-day deterministic price series spanning 2022-2024."""
    dates = pd.date_range("2022-01-03", periods=500, freq="B")
    rng = np.random.default_rng(7)
    prices = pd.Series(
        100 * np.exp(np.cumsum(rng.normal(0.0005, 0.015, 500))),
        index=dates, name="AAPL", dtype=float,
    )
    return prices


@pytest.fixture
def regime_returns():
    """300 log-returns with regime structure (stable GARCH / HMM fits)."""
    rng = np.random.default_rng(42)
    dates = pd.date_range("2022-01-03", periods=300, freq="B")
    low  = rng.normal(0.001,  0.008, 100)
    mid  = rng.normal(0.000,  0.015, 100)
    high = rng.normal(-0.001, 0.030, 100)
    return pd.Series(np.concatenate([low, mid, high]), index=dates, name="returns")


# ── _simulate_garch_path ──────────────────────────────────────────────────────

class TestSimulateGarchPath:
    def test_output_length(self):
        from fina.backtest.montecarlo import _simulate_garch_path
        rng = np.random.default_rng(1)
        out = _simulate_garch_path(0.01, 0.1, 0.85, 1.0, 60, rng)
        assert len(out) == 60

    def test_returns_are_finite(self):
        from fina.backtest.montecarlo import _simulate_garch_path
        rng = np.random.default_rng(2)
        out = _simulate_garch_path(0.01, 0.1, 0.85, 1.0, 120, rng)
        assert np.all(np.isfinite(out))

    def test_unstable_garch_stays_finite(self):
        """Persistence >= 1 must not explode."""
        from fina.backtest.montecarlo import _simulate_garch_path
        rng = np.random.default_rng(3)
        # alpha + beta = 1.05 → unstable
        out = _simulate_garch_path(0.05, 0.5, 0.55, 1.0, 100, rng)
        assert np.all(np.isfinite(out))
        assert np.all(np.abs(out) < 5.0)  # decimal returns, not blow-up

    def test_shock_clipping_prevents_extremes(self):
        """Returns should be well within reasonable range."""
        from fina.backtest.montecarlo import _simulate_garch_path
        rng = np.random.default_rng(99)
        out = _simulate_garch_path(0.01, 0.15, 0.80, 2.0, 252, rng)
        # Even with high last_h, daily returns shouldn't exceed ±50% in decimal
        assert out.max() < 0.5
        assert out.min() > -0.5

    def test_scale_is_decimal(self):
        """Output must be in decimal scale, not percentage."""
        from fina.backtest.montecarlo import _simulate_garch_path
        rng = np.random.default_rng(5)
        out = _simulate_garch_path(0.005, 0.05, 0.90, 0.5, 252, rng)
        # Typical daily returns are < 5% in decimal
        assert np.percentile(np.abs(out), 99) < 0.10


# ── _fit_models ───────────────────────────────────────────────────────────────

class TestFitModels:
    def test_returns_mcmodels_dataclass(self, regime_returns):
        from fina.backtest.montecarlo import _fit_models, _MCModels
        test_r = regime_returns.iloc[-60:]
        train_r = regime_returns.iloc[:-60]
        mc = _fit_models(train_r, test_r, ["arima", "hmm", "garch"], 0.0, 3)
        assert isinstance(mc, _MCModels)
        assert mc.test_length == 60
        assert len(mc.test_index) == 60

    def test_garch_params_reasonable(self, regime_returns):
        from fina.backtest.montecarlo import _fit_models
        test_r = regime_returns.iloc[-60:]
        train_r = regime_returns.iloc[:-60]
        mc = _fit_models(train_r, test_r, ["garch"], 0.0, 3)
        assert mc.garch_omega >= 0
        assert 0 <= mc.garch_alpha <= 1
        assert 0 <= mc.garch_beta <= 1
        assert mc.garch_last_h_scaled > 0
        assert mc.garch_target_vol > 0

    def test_hmm_maps_valid(self, regime_returns):
        from fina.backtest.montecarlo import _fit_models
        test_r = regime_returns.iloc[-60:]
        train_r = regime_returns.iloc[:-60]
        mc = _fit_models(train_r, test_r, ["hmm"], 0.0, 3)
        if mc.hmm_model is not None:
            assert set(mc.hmm_signal_map.values()).issubset({-1, 0, 1})

    def test_garch_only_skips_arima_hmm(self, regime_returns):
        from fina.backtest.montecarlo import _fit_models
        test_r = regime_returns.iloc[-60:]
        train_r = regime_returns.iloc[:-60]
        mc = _fit_models(train_r, test_r, ["garch"], 0.0, 3)
        assert mc.arima_model is None
        assert mc.hmm_model is None


# ── _aggregate ────────────────────────────────────────────────────────────────

class TestAggregate:
    def _make_equity(self, n_sims, T, initial=10_000.0):
        rng = np.random.default_rng(0)
        # Equity paths: random walks starting at initial
        paths = np.full((n_sims, T), initial)
        for t in range(1, T):
            paths[:, t] = paths[:, t-1] * (1 + rng.normal(0.001, 0.015, n_sims))
        return paths

    def test_fan_chart_length_matches_T(self):
        from fina.backtest.montecarlo import _aggregate
        T = 50
        n = 100
        eq = self._make_equity(n, T)
        idx = pd.date_range("2024-01-01", periods=T, freq="B")
        fc, md = _aggregate(eq, eq[:, -1]/10_000 - 1, np.zeros(n), np.zeros(n), np.zeros(n), idx, 10_000.0, n)
        assert len(fc) == T

    def test_fan_chart_has_all_percentiles(self):
        from fina.backtest.montecarlo import _aggregate
        T = 30
        n = 80
        eq = self._make_equity(n, T)
        idx = pd.date_range("2024-01-01", periods=T, freq="B")
        fc, md = _aggregate(eq, eq[:, -1]/10_000 - 1, np.zeros(n), np.zeros(n), np.zeros(n), idx, 10_000.0, n)
        for row in fc:
            assert {"date", "p5", "p25", "p50", "p75", "p95"} == set(row.keys())

    def test_percentile_ordering(self):
        """p5 <= p25 <= p50 <= p75 <= p95 for every date."""
        from fina.backtest.montecarlo import _aggregate
        T = 20
        n = 100
        eq = self._make_equity(n, T)
        idx = pd.date_range("2024-01-01", periods=T, freq="B")
        fc, _ = _aggregate(eq, eq[:, -1]/10_000 - 1, np.zeros(n), np.zeros(n), np.zeros(n), idx, 10_000.0, n)
        for row in fc:
            assert row["p5"] <= row["p25"] <= row["p50"] <= row["p75"] <= row["p95"]

    def test_metrics_distribution_keys(self):
        from fina.backtest.montecarlo import _aggregate
        T = 20
        n = 60
        eq = self._make_equity(n, T)
        rets = eq[:, -1] / 10_000 - 1
        idx = pd.date_range("2024-01-01", periods=T, freq="B")
        _, md = _aggregate(eq, rets, np.zeros(n), np.zeros(n), np.zeros(n), idx, 10_000.0, n)
        expected = {"total_return", "max_drawdown", "sharpe_ratio", "var_95", "cvar_95", "prob_profit", "prob_beat_benchmark"}
        assert expected == set(md.keys())

    def test_prob_profit_in_range(self):
        from fina.backtest.montecarlo import _aggregate
        T = 10
        n = 50
        eq = self._make_equity(n, T)
        rets = eq[:, -1] / 10_000 - 1
        idx = pd.date_range("2024-01-01", periods=T, freq="B")
        _, md = _aggregate(eq, rets, np.zeros(n), np.zeros(n), np.zeros(n), idx, 10_000.0, n)
        assert 0.0 <= md["prob_profit"] <= 1.0
        assert 0.0 <= md["prob_beat_benchmark"] <= 1.0


# ── run_montecarlo integration ────────────────────────────────────────────────

class TestRunMontecarlo:
    def test_returns_expected_keys(self, mock_prices):
        from fina.backtest.montecarlo import run_montecarlo
        with patch("fina.backtest.montecarlo.fetch_close_prices", return_value=mock_prices):
            result = run_montecarlo(
                "AAPL",
                train_start="2022-01-03", train_end="2023-06-30",
                test_start="2023-07-01", test_end="2023-12-31",
                n_simulations=50,
            )
        assert "fan_chart" in result
        assert "metrics_distribution" in result
        assert "n_simulations" in result
        assert "train_period" in result
        assert "test_period" in result
        assert "warnings" in result

    def test_n_simulations_reported(self, mock_prices):
        from fina.backtest.montecarlo import run_montecarlo
        with patch("fina.backtest.montecarlo.fetch_close_prices", return_value=mock_prices):
            result = run_montecarlo(
                "AAPL",
                train_start="2022-01-03", train_end="2023-06-30",
                test_start="2023-07-01", test_end="2023-12-31",
                n_simulations=50,
            )
        assert result["n_simulations"] >= 10  # at least _MC_MIN_SUCCESSFUL

    def test_fan_chart_aligned_with_test_period(self, mock_prices):
        from fina.backtest.montecarlo import run_montecarlo
        with patch("fina.backtest.montecarlo.fetch_close_prices", return_value=mock_prices):
            result = run_montecarlo(
                "AAPL",
                train_start="2022-01-03", train_end="2023-06-30",
                test_start="2023-07-01", test_end="2023-12-31",
                n_simulations=50,
            )
        assert len(result["fan_chart"]) == result["test_period"]["trading_days"]

    def test_overlapping_dates_raises(self):
        from fina.backtest.montecarlo import run_montecarlo
        with pytest.raises(BacktestError, match="before test start"):
            run_montecarlo(
                "AAPL",
                train_start="2022-01-01", train_end="2024-06-30",
                test_start="2024-01-01", test_end="2024-12-31",
                n_simulations=50,
            )

    def test_garch_only_mode(self, mock_prices):
        from fina.backtest.montecarlo import run_montecarlo
        with patch("fina.backtest.montecarlo.fetch_close_prices", return_value=mock_prices):
            result = run_montecarlo(
                "AAPL",
                train_start="2022-01-03", train_end="2023-06-30",
                test_start="2023-07-01", test_end="2023-12-31",
                n_simulations=50,
                models=["garch"],
            )
        assert result["n_simulations"] >= 10

    def test_reproducible_with_seed(self, mock_prices):
        from fina.backtest.montecarlo import run_montecarlo
        kwargs = dict(
            ticker="AAPL",
            train_start="2022-01-03", train_end="2023-06-30",
            test_start="2023-07-01", test_end="2023-12-31",
            n_simulations=50,
            random_seed=42,
        )
        with patch("fina.backtest.montecarlo.fetch_close_prices", return_value=mock_prices):
            r1 = run_montecarlo(**kwargs)
        with patch("fina.backtest.montecarlo.fetch_close_prices", return_value=mock_prices):
            r2 = run_montecarlo(**kwargs)
        assert r1["fan_chart"][0]["p50"] == r2["fan_chart"][0]["p50"]

    def test_metrics_distribution_var_le_cvar(self, mock_prices):
        """CVaR (expected shortfall) should be <= VaR (or close)."""
        from fina.backtest.montecarlo import run_montecarlo
        with patch("fina.backtest.montecarlo.fetch_close_prices", return_value=mock_prices):
            result = run_montecarlo(
                "AAPL",
                train_start="2022-01-03", train_end="2023-06-30",
                test_start="2023-07-01", test_end="2023-12-31",
                n_simulations=50,
            )
        md = result["metrics_distribution"]
        # CVaR is the average of tail beyond VaR, so CVaR <= VaR
        assert md["cvar_95"] <= md["var_95"] + 1e-9


# ── Route tests ───────────────────────────────────────────────────────────────

class TestMonteCarloRoute:
    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from fina.api.main import app
        return TestClient(app)

    @pytest.fixture
    def mc_payload(self):
        return {
            "ticker": "AAPL",
            "train_start": "2022-01-03",
            "train_end": "2023-06-30",
            "test_start": "2023-07-01",
            "test_end": "2023-12-31",
            "n_simulations": 50,
        }

    def test_valid_request_returns_200(self, client, mc_payload, mock_prices):
        with patch("fina.backtest.montecarlo.fetch_close_prices", return_value=mock_prices):
            resp = client.post("/backtest/montecarlo/", json=mc_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert "fan_chart" in data
        assert "metrics_distribution" in data

    def test_invalid_n_simulations_returns_422(self, client, mc_payload):
        mc_payload["n_simulations"] = 10  # below minimum 50
        resp = client.post("/backtest/montecarlo/", json=mc_payload)
        assert resp.status_code == 422

    def test_invalid_ticker_returns_422(self, client, mc_payload):
        mc_payload["ticker"] = "invalid ticker!"
        resp = client.post("/backtest/montecarlo/", json=mc_payload)
        assert resp.status_code == 422

    def test_overlapping_dates_returns_422(self, client, mc_payload):
        mc_payload["train_end"] = "2023-12-31"
        mc_payload["test_start"] = "2023-06-01"
        with patch("fina.backtest.montecarlo.fetch_close_prices", return_value=pd.Series(dtype=float)):
            resp = client.post("/backtest/montecarlo/", json=mc_payload)
        assert resp.status_code == 422

    def test_response_schema(self, client, mc_payload, mock_prices):
        with patch("fina.backtest.montecarlo.fetch_close_prices", return_value=mock_prices):
            resp = client.post("/backtest/montecarlo/", json=mc_payload)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data["fan_chart"], list)
        assert isinstance(data["metrics_distribution"], dict)
        assert isinstance(data["n_simulations"], int)
        assert isinstance(data["warnings"], list)
