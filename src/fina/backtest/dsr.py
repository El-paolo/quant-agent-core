"""
Deflated Sharpe Ratio — Bailey & López de Prado (2014).

Corrects observed Sharpe ratios for multiple testing bias.
When you try N strategies, the best Sharpe is inflated by luck.
The DSR estimates the probability that the observed Sharpe exceeds
the expected maximum under the null hypothesis (no skill).

Reference:
    Bailey, D.H. & López de Prado, M. (2014).
    "The Deflated Sharpe Ratio: Correcting for Selection Bias,
    Backtest Overfitting, and Non-Normality."
    Journal of Portfolio Management, 40(5), 94-107.
"""

import numpy as np
from scipy.stats import norm


def deflated_sharpe_ratio(
    observed_sr: float,
    n_trials: int,
    n_obs: int,
    skewness: float = 0.0,
    kurtosis: float = 3.0,
) -> dict:
    """
    Compute the Deflated Sharpe Ratio.

    Args:
        observed_sr: Annualized Sharpe ratio from the best backtest.
        n_trials:    Number of independent strategy configurations tested.
                     Must be >= 1.
        n_obs:       Number of return observations in the backtest.
                     Must be >= 2.
        skewness:    Skewness of the return distribution (0 for normal).
        kurtosis:    Kurtosis of the return distribution (3 for normal).

    Returns:
        dict with:
          - ``"dsr"``            — Deflated Sharpe Ratio (probability, 0–1).
          - ``"sr_benchmark"``   — Expected max Sharpe under H0.
          - ``"se"``             — Standard error of Sharpe estimate.
          - ``"n_trials"``       — Echo of input.
          - ``"n_obs"``          — Echo of input.
          - ``"is_significant"`` — True if DSR > 0.95.

    Raises:
        ValueError: On invalid inputs.
    """
    if n_trials < 1:
        raise ValueError(f"n_trials must be >= 1; got {n_trials}.")
    if n_obs < 2:
        raise ValueError(f"n_obs must be >= 2; got {n_obs}.")
    if not np.isfinite(observed_sr):
        raise ValueError(f"observed_sr must be finite; got {observed_sr}.")

    # Expected maximum Sharpe ratio under H0 (Euler–Mascheroni approximation)
    # E[max(SR)] ≈ sqrt(2 * ln(N)) - (gamma + ln(pi/2)) / (2 * sqrt(2 * ln(N)))
    # Simplified form commonly used:
    if n_trials == 1:
        sr_benchmark = 0.0
    else:
        sr_benchmark = np.sqrt(2.0 * np.log(n_trials)) * (
            1.0 - _EULER_MASCHERONI / (2.0 * np.log(n_trials))
        ) + _EULER_MASCHERONI / (2.0 * np.sqrt(2.0 * np.log(n_trials)))

    # Standard error of Sharpe ratio (Lo 2002, adjusted for non-normality)
    # Var[SR] ≈ (1 - γ₁·SR + (γ₂-1)/4 · SR²) / (T-1)
    sr = observed_sr
    var_sr = (
        1.0
        - skewness * sr
        + ((kurtosis - 1.0) / 4.0) * sr ** 2
    ) / (n_obs - 1)

    se = np.sqrt(max(var_sr, 1e-12))  # floor to prevent division by zero

    # DSR = Φ((SR_obs - SR_benchmark) / SE)
    z = (observed_sr - sr_benchmark) / se
    dsr = float(norm.cdf(z))

    return {
        "dsr": float(dsr),
        "sr_benchmark": float(sr_benchmark),
        "se": float(se),
        "n_trials": n_trials,
        "n_obs": n_obs,
        "is_significant": dsr > 0.95,
    }


# Euler–Mascheroni constant
_EULER_MASCHERONI = 0.5772156649015329
