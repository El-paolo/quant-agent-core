"""
Unit tests for fina.backtest.dsr — Deflated Sharpe Ratio.

Tests verify mathematical correctness against known properties
of the DSR formula (Bailey & López de Prado 2014).
"""

import pytest

from fina.backtest.dsr import deflated_sharpe_ratio


class TestDeflatedSharpeRatio:
    def test_single_trial_no_deflation(self) -> None:
        """With n_trials=1, SR benchmark is 0 — DSR should be high for positive SR."""
        result = deflated_sharpe_ratio(
            observed_sr=1.5, n_trials=1, n_obs=252
        )
        assert result["sr_benchmark"] == 0.0
        assert result["dsr"] > 0.95
        assert result["is_significant"] is True

    def test_many_trials_deflates(self) -> None:
        """More trials → higher SR benchmark → lower DSR for same observed SR."""
        dsr_1 = deflated_sharpe_ratio(observed_sr=1.0, n_trials=1, n_obs=252)
        dsr_10 = deflated_sharpe_ratio(observed_sr=1.0, n_trials=10, n_obs=252)
        dsr_100 = deflated_sharpe_ratio(observed_sr=1.0, n_trials=100, n_obs=252)

        assert dsr_1["dsr"] > dsr_10["dsr"] > dsr_100["dsr"]

    def test_zero_sharpe_low_dsr(self) -> None:
        """Zero Sharpe should produce low DSR regardless of trials."""
        result = deflated_sharpe_ratio(
            observed_sr=0.0, n_trials=1, n_obs=252
        )
        assert result["dsr"] < 0.55  # near 0.5 for SR=0, benchmark=0

    def test_negative_sharpe(self) -> None:
        """Negative Sharpe should produce very low DSR."""
        result = deflated_sharpe_ratio(
            observed_sr=-1.0, n_trials=1, n_obs=252
        )
        assert result["dsr"] < 0.1

    def test_high_sharpe_significant(self) -> None:
        """Very high Sharpe should be significant even with many trials."""
        result = deflated_sharpe_ratio(
            observed_sr=3.0, n_trials=50, n_obs=504
        )
        assert result["is_significant"] is True

    def test_more_observations_tighter_se(self) -> None:
        """More observations → smaller SE → more decisive DSR."""
        short = deflated_sharpe_ratio(observed_sr=1.0, n_trials=5, n_obs=50)
        long = deflated_sharpe_ratio(observed_sr=1.0, n_trials=5, n_obs=1000)
        assert long["se"] < short["se"]

    def test_kurtosis_increases_se(self) -> None:
        """Fat tails (high kurtosis) → larger SE → harder to be significant."""
        normal = deflated_sharpe_ratio(
            observed_sr=1.0, n_trials=5, n_obs=252, kurtosis=3.0
        )
        fat_tail = deflated_sharpe_ratio(
            observed_sr=1.0, n_trials=5, n_obs=252, kurtosis=6.0
        )
        assert fat_tail["se"] > normal["se"]

    def test_returns_all_keys(self) -> None:
        result = deflated_sharpe_ratio(observed_sr=1.0, n_trials=3, n_obs=252)
        expected_keys = {"dsr", "sr_benchmark", "se", "n_trials", "n_obs", "is_significant"}
        assert set(result.keys()) == expected_keys

    def test_invalid_n_trials_raises(self) -> None:
        with pytest.raises(ValueError, match="n_trials"):
            deflated_sharpe_ratio(observed_sr=1.0, n_trials=0, n_obs=252)

    def test_invalid_n_obs_raises(self) -> None:
        with pytest.raises(ValueError, match="n_obs"):
            deflated_sharpe_ratio(observed_sr=1.0, n_trials=1, n_obs=1)

    def test_nan_sharpe_raises(self) -> None:
        with pytest.raises(ValueError, match="finite"):
            deflated_sharpe_ratio(observed_sr=float("nan"), n_trials=1, n_obs=252)
