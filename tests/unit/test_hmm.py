"""
Unit tests for fina.models.hmm — HMM regime detection.

Uses a dedicated fixture with synthetic regime data for 3-state tests,
since the standard sample_log_returns may not support 3-state convergence.
"""

import numpy as np
import pandas as pd
import pytest

from fina.core.exceptions import MetricsError
from fina.models.hmm import fit_hmm


@pytest.fixture
def regime_returns() -> pd.Series:
    """
    Synthetic returns with 3 clear regimes for reliable HMM fitting.

    - Low vol:  N(0.001, 0.005) — 150 days
    - High vol: N(-0.002, 0.03) — 80 days
    - Mid vol:  N(0.0005, 0.012) — 120 days

    Total: 350 observations — well above the 100 minimum.
    """
    rng = np.random.default_rng(42)
    low = rng.normal(0.001, 0.005, 150)
    high = rng.normal(-0.002, 0.03, 80)
    mid = rng.normal(0.0005, 0.012, 120)
    values = np.concatenate([low, high, mid])
    dates = pd.date_range("2023-01-01", periods=len(values), freq="B")
    return pd.Series(values, index=dates, name="SYNTH")


class TestFitHmmHappyPath:
    def test_returns_expected_keys(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns, n_states=3)
        expected = {
            "states", "state_sequence", "current_regime", "state_params",
            "distributions", "transition_matrix", "split", "train_score",
            "test_score", "n_states", "observations", "log_likelihood",
            "aic", "bic",
        }
        assert expected == set(result.keys())

    def test_states_series_length(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns, n_states=3)
        n = len(regime_returns.dropna())
        assert len(result["states"]) == n
        assert len(result["state_sequence"]) == n

    def test_states_are_valid_labels(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns, n_states=3)
        valid = {"low_vol", "mid_vol", "high_vol"}
        assert set(result["states"].unique()).issubset(valid)

    def test_state_sequence_values(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns, n_states=3)
        assert set(result["state_sequence"].unique()).issubset({0, 1, 2})

    def test_two_states(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns, n_states=2)
        assert result["n_states"] == 2
        assert len(result["state_params"]) == 2
        # With 2 states, labels are low_vol and mid_vol (first 2 from ordered list)
        valid = {"low_vol", "mid_vol"}
        assert set(result["states"].unique()).issubset(valid)

    def test_current_regime_fields(self, regime_returns: pd.Series) -> None:
        regime = fit_hmm(regime_returns, n_states=3)["current_regime"]
        assert set(regime.keys()) == {"label", "label_es", "since_date", "duration_days"}
        assert regime["duration_days"] >= 1
        assert regime["label"] in {"low_vol", "mid_vol", "high_vol"}

    def test_state_params_structure(self, regime_returns: pd.Series) -> None:
        params = fit_hmm(regime_returns, n_states=3)["state_params"]
        assert len(params) == 3
        for sp in params:
            assert set(sp.keys()) == {
                "label", "label_es", "mean_return", "std",
                "annualized_vol", "stationary_prob",
            }
            assert sp["std"] > 0
            assert sp["annualized_vol"] > 0
            assert 0 <= sp["stationary_prob"] <= 1

    def test_state_params_ordered_by_variance(self, regime_returns: pd.Series) -> None:
        params = fit_hmm(regime_returns, n_states=3)["state_params"]
        stds = [sp["std"] for sp in params]
        assert stds == sorted(stds), "States should be ordered by variance ascending"

    def test_stationary_probs_sum_to_one(self, regime_returns: pd.Series) -> None:
        params = fit_hmm(regime_returns, n_states=3)["state_params"]
        total = sum(sp["stationary_prob"] for sp in params)
        assert total == pytest.approx(1.0, abs=1e-6)


class TestHmmDistributions:
    def test_distributions_count(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns, n_states=3)
        assert len(result["distributions"]) == 3

    def test_distribution_fields(self, regime_returns: pd.Series) -> None:
        for dist in fit_hmm(regime_returns, n_states=3)["distributions"]:
            assert set(dist.keys()) == {"label", "label_es", "mean", "std", "x", "pdf"}
            assert len(dist["x"]) == 200
            assert len(dist["pdf"]) == 200

    def test_pdf_non_negative(self, regime_returns: pd.Series) -> None:
        for dist in fit_hmm(regime_returns, n_states=3)["distributions"]:
            assert all(v >= 0 for v in dist["pdf"])

    def test_x_range_covers_data(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns, n_states=3)
        data_min = float(regime_returns.dropna().min())
        data_max = float(regime_returns.dropna().max())
        for dist in result["distributions"]:
            assert dist["x"][0] <= data_min
            assert dist["x"][-1] >= data_max

    def test_distributions_match_state_params(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns, n_states=3)
        for dist, sp in zip(result["distributions"], result["state_params"]):
            assert dist["label"] == sp["label"]
            assert dist["mean"] == pytest.approx(sp["mean_return"], rel=1e-10)
            assert dist["std"] == pytest.approx(sp["std"], rel=1e-10)


class TestHmmTrainTestSplit:
    def test_split_metadata(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns, train_ratio=0.80)
        sp = result["split"]
        assert set(sp.keys()) == {"train_size", "test_size", "train_ratio"}
        assert sp["train_ratio"] == 0.80
        assert sp["train_size"] + sp["test_size"] == result["observations"]

    def test_default_split_is_80_20(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns)
        n = result["observations"]
        assert result["split"]["train_size"] == int(n * 0.80)

    def test_custom_split_70_30(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns, train_ratio=0.70)
        n = result["observations"]
        assert result["split"]["train_size"] == int(n * 0.70)
        assert result["split"]["train_ratio"] == 0.70

    def test_train_score_exists(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns)
        assert isinstance(result["train_score"], float)
        assert isinstance(result["test_score"], float)

    def test_scores_are_finite(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns)
        assert np.isfinite(result["train_score"])
        assert np.isfinite(result["test_score"])

    def test_invalid_train_ratio_too_low(self, regime_returns: pd.Series) -> None:
        with pytest.raises(MetricsError, match="train_ratio"):
            fit_hmm(regime_returns, train_ratio=0.3)

    def test_invalid_train_ratio_too_high(self, regime_returns: pd.Series) -> None:
        with pytest.raises(MetricsError, match="train_ratio"):
            fit_hmm(regime_returns, train_ratio=0.99)


class TestHmmTransitionMatrix:
    def test_shape(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns, n_states=3)
        tm = result["transition_matrix"]
        assert len(tm) == 3
        assert all(len(row) == 3 for row in tm)

    def test_rows_sum_to_one(self, regime_returns: pd.Series) -> None:
        tm = fit_hmm(regime_returns, n_states=3)["transition_matrix"]
        for row in tm:
            assert sum(row) == pytest.approx(1.0, abs=1e-6)

    def test_all_probs_non_negative(self, regime_returns: pd.Series) -> None:
        tm = fit_hmm(regime_returns, n_states=3)["transition_matrix"]
        for row in tm:
            for p in row:
                assert p >= 0


class TestHmmEdgeCases:
    def test_insufficient_data_raises(self) -> None:
        short = pd.Series(np.random.default_rng(0).normal(0, 0.01, 50))
        with pytest.raises(MetricsError, match="at least 100"):
            fit_hmm(short)

    def test_invalid_n_states_raises(self, regime_returns: pd.Series) -> None:
        with pytest.raises(MetricsError, match="2 or 3"):
            fit_hmm(regime_returns, n_states=5)

    def test_nans_are_dropped(self) -> None:
        rng = np.random.default_rng(42)
        values = rng.normal(0, 0.02, 120)
        values[10] = np.nan
        values[50] = np.nan
        returns = pd.Series(values)
        result = fit_hmm(returns, n_states=2)
        assert result["observations"] == 118

    def test_aic_bic_are_finite(self, regime_returns: pd.Series) -> None:
        result = fit_hmm(regime_returns, n_states=3)
        assert np.isfinite(result["aic"])
        assert np.isfinite(result["bic"])
