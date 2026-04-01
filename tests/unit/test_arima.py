"""
Unit tests for fina.models.arima — Auto-ARIMA return forecast model.

All tests use the deterministic sample_log_returns fixture (251 obs).
"""

import numpy as np
import pandas as pd
import pytest

from fina.core.exceptions import MetricsError
from fina.models.arima import fit_arima


class TestFitArimaHappyPath:
    def test_returns_expected_keys(self, sample_log_returns: pd.Series) -> None:
        result = fit_arima(sample_log_returns)
        expected = {
            "fitted_values", "forecast", "residuals", "diagnostics",
            "split", "train_score", "test_score", "horizon",
            "observations", "confidence",
        }
        assert expected == set(result.keys())

    def test_fitted_values_is_series(self, sample_log_returns: pd.Series) -> None:
        result = fit_arima(sample_log_returns)
        assert isinstance(result["fitted_values"], pd.Series)
        assert len(result["fitted_values"]) == len(sample_log_returns.dropna())

    def test_residuals_is_series(self, sample_log_returns: pd.Series) -> None:
        result = fit_arima(sample_log_returns)
        assert isinstance(result["residuals"], pd.Series)
        assert len(result["residuals"]) == len(sample_log_returns.dropna())

    def test_forecast_length_matches_horizon(self, sample_log_returns: pd.Series) -> None:
        result = fit_arima(sample_log_returns, horizon=5)
        assert len(result["forecast"]) == 5

    def test_forecast_has_expected_fields(self, sample_log_returns: pd.Series) -> None:
        result = fit_arima(sample_log_returns)
        for day in result["forecast"]:
            assert set(day.keys()) == {"day", "predicted", "upper", "lower"}
            assert day["upper"] >= day["lower"]

    def test_forecast_days_sequential(self, sample_log_returns: pd.Series) -> None:
        result = fit_arima(sample_log_returns, horizon=3)
        days = [d["day"] for d in result["forecast"]]
        assert days == [1, 2, 3]

    def test_diagnostics_keys(self, sample_log_returns: pd.Series) -> None:
        diag = fit_arima(sample_log_returns)["diagnostics"]
        expected = {
            "order", "seasonal_order", "aic", "bic",
            "residual_mean", "residual_std", "ljung_box_pvalue",
        }
        assert expected == set(diag.keys())

    def test_order_is_list_of_three(self, sample_log_returns: pd.Series) -> None:
        order = fit_arima(sample_log_returns)["diagnostics"]["order"]
        assert isinstance(order, list)
        assert len(order) == 3
        assert all(isinstance(v, int) for v in order)

    def test_aic_bic_are_finite(self, sample_log_returns: pd.Series) -> None:
        diag = fit_arima(sample_log_returns)["diagnostics"]
        assert np.isfinite(diag["aic"])
        assert np.isfinite(diag["bic"])


class TestArimaTrainTestSplit:
    def test_split_keys(self, sample_log_returns: pd.Series) -> None:
        split = fit_arima(sample_log_returns)["split"]
        assert set(split.keys()) == {"train_size", "test_size", "train_ratio"}

    def test_split_ratio_matches(self, sample_log_returns: pd.Series) -> None:
        result = fit_arima(sample_log_returns, train_ratio=0.80)
        split = result["split"]
        assert split["train_ratio"] == 0.80
        total = split["train_size"] + split["test_size"]
        assert total == result["observations"]

    def test_train_score_keys(self, sample_log_returns: pd.Series) -> None:
        ts = fit_arima(sample_log_returns)["train_score"]
        assert set(ts.keys()) == {"aic", "bic", "mae", "rmse"}

    def test_test_score_keys(self, sample_log_returns: pd.Series) -> None:
        ts = fit_arima(sample_log_returns)["test_score"]
        assert set(ts.keys()) == {"mae", "rmse", "directional_accuracy", "n_samples"}

    def test_test_score_n_samples_positive(self, sample_log_returns: pd.Series) -> None:
        ts = fit_arima(sample_log_returns)["test_score"]
        assert ts["n_samples"] > 0

    def test_train_mae_non_negative(self, sample_log_returns: pd.Series) -> None:
        ts = fit_arima(sample_log_returns)["train_score"]
        assert ts["mae"] >= 0
        assert ts["rmse"] >= 0

    def test_test_mae_non_negative(self, sample_log_returns: pd.Series) -> None:
        ts = fit_arima(sample_log_returns)["test_score"]
        assert ts["mae"] is None or ts["mae"] >= 0
        assert ts["rmse"] is None or ts["rmse"] >= 0


class TestArimaLjungBox:
    def test_ljung_box_pvalue_in_range(self, sample_log_returns: pd.Series) -> None:
        lb = fit_arima(sample_log_returns)["diagnostics"]["ljung_box_pvalue"]
        if lb is not None:
            assert 0 <= lb <= 1


class TestArimaEdgeCases:
    def test_too_few_observations_raises(self) -> None:
        short = pd.Series(
            np.random.default_rng(0).normal(0, 0.01, 30),
            index=pd.date_range("2024-01-01", periods=30, freq="B"),
        )
        with pytest.raises(MetricsError, match="at least 60"):
            fit_arima(short)

    def test_invalid_train_ratio_raises(self, sample_log_returns: pd.Series) -> None:
        with pytest.raises(MetricsError, match="train_ratio"):
            fit_arima(sample_log_returns, train_ratio=0.99)

    def test_invalid_train_ratio_low_raises(self, sample_log_returns: pd.Series) -> None:
        with pytest.raises(MetricsError, match="train_ratio"):
            fit_arima(sample_log_returns, train_ratio=0.3)

    def test_custom_horizon(self, sample_log_returns: pd.Series) -> None:
        result = fit_arima(sample_log_returns, horizon=10)
        assert result["horizon"] == 10
        assert len(result["forecast"]) == 10

    def test_observations_count(self, sample_log_returns: pd.Series) -> None:
        result = fit_arima(sample_log_returns)
        assert result["observations"] == len(sample_log_returns.dropna())

    def test_confidence_stored(self, sample_log_returns: pd.Series) -> None:
        result = fit_arima(sample_log_returns, confidence=0.99)
        assert result["confidence"] == 0.99
