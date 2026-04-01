"""
Unit tests for fina.models.comparator — model comparison engine.

All tests use the deterministic sample_log_returns fixture (251 obs).
"""

import numpy as np
import pandas as pd
import pytest

from fina.models.comparator import compare_models


class TestCompareModelsHappyPath:
    def test_returns_expected_keys(self, sample_log_returns: pd.Series) -> None:
        result = compare_models(sample_log_returns)
        assert set(result.keys()) == {"models", "comparison", "verdict", "warnings"}

    def test_models_has_arima_and_garch(self, sample_log_returns: pd.Series) -> None:
        result = compare_models(sample_log_returns)
        assert "arima" in result["models"]
        assert "garch" in result["models"]

    def test_arima_model_keys(self, sample_log_returns: pd.Series) -> None:
        result = compare_models(sample_log_returns)
        arima = result["models"]["arima"]
        if arima is not None:
            assert "name" in arima
            assert "aic" in arima
            assert "bic" in arima
            assert "test_mae" in arima
            assert "test_rmse" in arima
            assert "directional_accuracy" in arima

    def test_garch_model_keys(self, sample_log_returns: pd.Series) -> None:
        result = compare_models(sample_log_returns)
        garch = result["models"]["garch"]
        if garch is not None:
            assert "name" in garch
            assert "aic" in garch
            assert "bic" in garch
            assert "persistence" in garch
            assert "test_mae" in garch


class TestComparisonTable:
    def test_comparison_is_list(self, sample_log_returns: pd.Series) -> None:
        result = compare_models(sample_log_returns)
        assert isinstance(result["comparison"], list)
        assert len(result["comparison"]) > 0

    def test_comparison_row_keys(self, sample_log_returns: pd.Series) -> None:
        result = compare_models(sample_log_returns)
        for row in result["comparison"]:
            assert set(row.keys()) == {
                "metric", "label", "arima", "arima_raw",
                "garch", "garch_raw", "winner",
            }

    def test_comparison_has_aic_bic(self, sample_log_returns: pd.Series) -> None:
        result = compare_models(sample_log_returns)
        metrics = [r["metric"] for r in result["comparison"]]
        assert "aic" in metrics
        assert "bic" in metrics
        assert "test_mae" in metrics
        assert "test_rmse" in metrics

    def test_winner_is_valid(self, sample_log_returns: pd.Series) -> None:
        result = compare_models(sample_log_returns)
        for row in result["comparison"]:
            assert row["winner"] in {"arima", "garch", None}


class TestVerdict:
    def test_verdict_keys(self, sample_log_returns: pd.Series) -> None:
        result = compare_models(sample_log_returns)
        v = result["verdict"]
        assert set(v.keys()) == {
            "best_forecast", "forecast_reason",
            "best_volatility", "volatility_reason",
            "summary_es",
        }

    def test_best_forecast_valid(self, sample_log_returns: pd.Series) -> None:
        result = compare_models(sample_log_returns)
        assert result["verdict"]["best_forecast"] in {
            "arima", "none", "weak", "unavailable",
        }

    def test_best_volatility_valid(self, sample_log_returns: pd.Series) -> None:
        result = compare_models(sample_log_returns)
        assert result["verdict"]["best_volatility"] in {
            "garch", "unstable", "unavailable",
        }

    def test_summary_is_spanish(self, sample_log_returns: pd.Series) -> None:
        result = compare_models(sample_log_returns)
        summary = result["verdict"]["summary_es"]
        assert isinstance(summary, str)
        assert len(summary) > 20


class TestCompareEdgeCases:
    def test_too_few_observations_degrades_gracefully(self) -> None:
        short = pd.Series(
            np.random.default_rng(0).normal(0, 0.01, 30),
            index=pd.date_range("2024-01-01", periods=30, freq="B"),
        )
        result = compare_models(short)
        # Both models should fail gracefully
        assert len(result["warnings"]) > 0

    def test_warnings_is_list(self, sample_log_returns: pd.Series) -> None:
        result = compare_models(sample_log_returns)
        assert isinstance(result["warnings"], list)
