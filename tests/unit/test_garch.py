"""
Unit tests for fina.models.garch — GARCH(1,1) volatility model.

All tests use the deterministic sample_log_returns fixture (251 obs).
"""

import numpy as np
import pandas as pd
import pytest

from fina.core.exceptions import MetricsError
from fina.models.garch import fit_garch


class TestFitGarchHappyPath:
    def test_returns_expected_keys(self, sample_log_returns: pd.Series) -> None:
        result = fit_garch(sample_log_returns)
        expected = {
            "conditional_vol", "forecast", "diagnostics", "split",
            "train_score", "test_score", "horizon", "observations", "confidence",
        }
        assert expected == set(result.keys())

    def test_conditional_vol_is_series(self, sample_log_returns: pd.Series) -> None:
        result = fit_garch(sample_log_returns)
        assert isinstance(result["conditional_vol"], pd.Series)
        assert len(result["conditional_vol"]) == len(sample_log_returns.dropna())

    def test_conditional_vol_positive(self, sample_log_returns: pd.Series) -> None:
        result = fit_garch(sample_log_returns)
        assert (result["conditional_vol"] > 0).all()

    def test_forecast_length_matches_horizon(self, sample_log_returns: pd.Series) -> None:
        result = fit_garch(sample_log_returns, horizon=5)
        assert len(result["forecast"]) == 5

    def test_forecast_has_expected_fields(self, sample_log_returns: pd.Series) -> None:
        result = fit_garch(sample_log_returns)
        for day in result["forecast"]:
            assert set(day.keys()) == {"day", "volatility", "upper", "lower"}
            assert day["upper"] >= day["volatility"] >= day["lower"]
            assert day["lower"] >= 0

    def test_forecast_days_sequential(self, sample_log_returns: pd.Series) -> None:
        result = fit_garch(sample_log_returns, horizon=3)
        days = [d["day"] for d in result["forecast"]]
        assert days == [1, 2, 3]

    def test_diagnostics_keys(self, sample_log_returns: pd.Series) -> None:
        diag = fit_garch(sample_log_returns)["diagnostics"]
        expected = {"omega", "alpha", "beta", "persistence", "aic", "bic", "long_run_vol"}
        assert expected == set(diag.keys())

    def test_persistence_is_alpha_plus_beta(self, sample_log_returns: pd.Series) -> None:
        diag = fit_garch(sample_log_returns)["diagnostics"]
        assert diag["persistence"] == pytest.approx(diag["alpha"] + diag["beta"], rel=1e-10)

    def test_alpha_beta_non_negative(self, sample_log_returns: pd.Series) -> None:
        diag = fit_garch(sample_log_returns)["diagnostics"]
        assert diag["alpha"] >= 0
        assert diag["beta"] >= 0

    def test_persistence_reasonable(self, sample_log_returns: pd.Series) -> None:
        diag = fit_garch(sample_log_returns)["diagnostics"]
        assert 0 < diag["persistence"] <= 1.05

    def test_observations_count(self, sample_log_returns: pd.Series) -> None:
        result = fit_garch(sample_log_returns)
        assert result["observations"] == len(sample_log_returns.dropna())

    def test_custom_horizon(self, sample_log_returns: pd.Series) -> None:
        result = fit_garch(sample_log_returns, horizon=10)
        assert result["horizon"] == 10
        assert len(result["forecast"]) == 10

    def test_custom_confidence(self, sample_log_returns: pd.Series) -> None:
        result = fit_garch(sample_log_returns, confidence=0.99)
        assert result["confidence"] == 0.99

    def test_wider_confidence_gives_wider_bands(self, sample_log_returns: pd.Series) -> None:
        r95 = fit_garch(sample_log_returns, confidence=0.95)
        r99 = fit_garch(sample_log_returns, confidence=0.99)
        spread95 = r95["forecast"][0]["upper"] - r95["forecast"][0]["lower"]
        spread99 = r99["forecast"][0]["upper"] - r99["forecast"][0]["lower"]
        assert spread99 > spread95


class TestFitGarchTrainTestSplit:
    def test_split_metadata(self, sample_log_returns: pd.Series) -> None:
        result = fit_garch(sample_log_returns, train_ratio=0.80)
        sp = result["split"]
        assert set(sp.keys()) == {"train_size", "test_size", "train_ratio"}
        assert sp["train_ratio"] == 0.80
        assert sp["train_size"] + sp["test_size"] == result["observations"]

    def test_default_split_is_80_20(self, sample_log_returns: pd.Series) -> None:
        result = fit_garch(sample_log_returns)
        n = result["observations"]
        assert result["split"]["train_size"] == int(n * 0.80)

    def test_custom_split_70_30(self, sample_log_returns: pd.Series) -> None:
        result = fit_garch(sample_log_returns, train_ratio=0.70)
        assert result["split"]["train_ratio"] == 0.70

    def test_train_score_has_aic_bic(self, sample_log_returns: pd.Series) -> None:
        ts = fit_garch(sample_log_returns)["train_score"]
        assert "aic" in ts
        assert "bic" in ts
        assert np.isfinite(ts["aic"])
        assert np.isfinite(ts["bic"])

    def test_test_score_has_mae(self, sample_log_returns: pd.Series) -> None:
        ts = fit_garch(sample_log_returns)["test_score"]
        assert "mae" in ts
        assert "rmse" in ts
        assert "realized_vol" in ts
        assert "n_samples" in ts

    def test_test_score_mae_positive(self, sample_log_returns: pd.Series) -> None:
        ts = fit_garch(sample_log_returns)["test_score"]
        if ts["mae"] is not None:
            assert ts["mae"] >= 0
            assert ts["rmse"] >= 0
            assert ts["rmse"] >= ts["mae"]  # RMSE >= MAE always

    def test_invalid_train_ratio(self, sample_log_returns: pd.Series) -> None:
        with pytest.raises(MetricsError, match="train_ratio"):
            fit_garch(sample_log_returns, train_ratio=0.3)


class TestFitGarchEdgeCases:
    def test_insufficient_data_raises(self) -> None:
        short = pd.Series(np.random.default_rng(0).normal(0, 0.01, 30))
        with pytest.raises(MetricsError, match="at least 50"):
            fit_garch(short)

    def test_minimum_viable_observations(self) -> None:
        """With 80/20 split, need enough for train set >= 50 obs."""
        rng = np.random.default_rng(42)
        # 63 obs → 50 train, 13 test (just enough)
        returns = pd.Series(rng.normal(0, 0.02, 63))
        result = fit_garch(returns)
        assert result["observations"] == 63
        assert result["split"]["train_size"] == 50

    def test_nans_are_dropped(self) -> None:
        rng = np.random.default_rng(42)
        values = rng.normal(0, 0.02, 70)
        values[5] = np.nan
        values[10] = np.nan
        returns = pd.Series(values)
        result = fit_garch(returns)
        assert result["observations"] == 68

    def test_train_set_too_small_raises(self) -> None:
        """50 obs with 80/20 split → 40 train → should fail."""
        rng = np.random.default_rng(42)
        returns = pd.Series(rng.normal(0, 0.02, 50))
        with pytest.raises(MetricsError, match="Train set too small"):
            fit_garch(returns)
