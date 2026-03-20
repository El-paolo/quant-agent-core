"""
Risk-adjusted return ratios: Sharpe and Sortino.

Both ratios measure return per unit of risk, differing only in how "risk"
is defined:
  - Sharpe  — penalises ALL volatility (upside and downside equally).
  - Sortino — penalises only DOWNSIDE volatility (returns below the MAR).

Formula reference:
  Sharpe  = (mean(r) - r_f) / std(r)           * sqrt(trading_days)
  Sortino = (mean(r) - MAR) / downside_std(r)   * sqrt(trading_days)

  where downside_std(r) = std of returns below the MAR (semi-deviation).

Security notes:
  - No external data is fetched in this module.
  - All numeric parameters are validated before use; strings are checked
    against an explicit allowlist where applicable.
  - Division-by-zero is handled explicitly and raises a descriptive error
    rather than returning NaN or inf silently.
"""

import numpy as np
import pandas as pd

from fina.core.exceptions import MetricsError


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_returns(returns: object) -> pd.Series:
    if not isinstance(returns, pd.Series):
        raise MetricsError(
            f"'returns' must be a pandas Series; got {type(returns).__name__}."
        )
    if len(returns) < 2:
        raise MetricsError(
            "At least 2 return observations are required to compute a ratio."
        )
    if returns.isnull().any():
        raise MetricsError(
            "Returns series contains NaN values. Clean data before computing ratios."
        )
    result: pd.Series = returns
    return result


def _validate_rate(value: float, name: str) -> None:
    if not isinstance(value, (int, float)):
        raise MetricsError(f"'{name}' must be a numeric value; got {type(value).__name__}.")
    if np.isnan(value) or np.isinf(value):
        raise MetricsError(f"'{name}' must be a finite number; got {value}.")


def _validate_trading_days(trading_days: int) -> None:
    if not isinstance(trading_days, int) or trading_days <= 0:
        raise MetricsError(
            f"'trading_days' must be a positive integer; got {trading_days!r}."
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    trading_days: int = 252,
    annualize: bool = True,
) -> dict:
    """
    Compute the annualized Sharpe ratio for a return series.

    Args:
        returns:         Periodic return series (e.g., daily log or simple returns).
        risk_free_rate:  Annualized risk-free rate (e.g., 0.05 for 5%).
                         Converted to per-period rate internally.
        trading_days:    Number of trading periods per year (252 for equities,
                         365 for crypto).
        annualize:       If True, scale the ratio by sqrt(trading_days).

    Returns:
        dict with keys:
          - ``"sharpe_ratio"``    (float)
          - ``"mean_return"``     (float) — per-period mean return
          - ``"volatility"``      (float) — per-period std deviation
          - ``"risk_free_rate"``  (float) — annualized rate passed in
          - ``"annualized"``      (bool)
          - ``"trading_days"``    (int | None)
          - ``"observations"``    (int)

    Raises:
        MetricsError: On invalid inputs or zero volatility.
    """
    returns = _validate_returns(returns)
    _validate_rate(risk_free_rate, "risk_free_rate")
    _validate_trading_days(trading_days)

    # Convert annualized rate to per-period
    rf_per_period: float = risk_free_rate / trading_days

    mean_r: float = float(returns.mean())
    vol: float = float(returns.std())

    if vol == 0:
        raise MetricsError(
            "Sharpe ratio is undefined: return series has zero volatility."
        )

    ratio: float = (mean_r - rf_per_period) / vol

    if annualize:
        ratio *= np.sqrt(trading_days)

    return {
        "sharpe_ratio": ratio,
        "mean_return": mean_r,
        "volatility": vol,
        "risk_free_rate": risk_free_rate,
        "annualized": annualize,
        "trading_days": trading_days if annualize else None,
        "observations": len(returns),
    }


def sortino_ratio(
    returns: pd.Series,
    minimum_acceptable_return: float = 0.0,
    trading_days: int = 252,
    annualize: bool = True,
) -> dict:
    """
    Compute the annualized Sortino ratio for a return series.

    Unlike the Sharpe ratio, the Sortino ratio only penalises returns that
    fall below the *minimum acceptable return* (MAR), ignoring upside
    variability.  This makes it more suitable for assets with asymmetric
    return distributions (e.g., options, crypto).

    Args:
        returns:                   Periodic return series.
        minimum_acceptable_return: Annualized MAR (e.g., 0.0 for no loss).
                                   Converted to per-period rate internally.
        trading_days:              Periods per year.
        annualize:                 If True, scale by sqrt(trading_days).

    Returns:
        dict with keys:
          - ``"sortino_ratio"``              (float)
          - ``"mean_return"``                (float) — per-period mean
          - ``"downside_deviation"``         (float) — semi-deviation
          - ``"minimum_acceptable_return"``  (float) — annualized MAR
          - ``"annualized"``                 (bool)
          - ``"trading_days"``               (int | None)
          - ``"observations"``               (int)
          - ``"downside_observations"``      (int)

    Raises:
        MetricsError: On invalid inputs or zero downside deviation.
    """
    returns = _validate_returns(returns)
    _validate_rate(minimum_acceptable_return, "minimum_acceptable_return")
    _validate_trading_days(trading_days)

    mar_per_period: float = minimum_acceptable_return / trading_days

    mean_r: float = float(returns.mean())

    downside = returns[returns < mar_per_period] - mar_per_period
    downside_obs = len(downside)

    if downside_obs == 0:
        raise MetricsError(
            "Sortino ratio is undefined: no returns fall below the MAR "
            f"({minimum_acceptable_return:.4f} annualized). "
            "All returns exceed the minimum acceptable return."
        )

    # Semi-deviation: sqrt of mean squared downside deviations
    downside_dev: float = float(np.sqrt((downside**2).mean()))

    if downside_dev == 0:
        raise MetricsError(
            "Sortino ratio is undefined: downside deviation is zero."
        )

    ratio: float = (mean_r - mar_per_period) / downside_dev

    if annualize:
        ratio *= np.sqrt(trading_days)

    return {
        "sortino_ratio": ratio,
        "mean_return": mean_r,
        "downside_deviation": downside_dev,
        "minimum_acceptable_return": minimum_acceptable_return,
        "annualized": annualize,
        "trading_days": trading_days if annualize else None,
        "observations": len(returns),
        "downside_observations": downside_obs,
    }
