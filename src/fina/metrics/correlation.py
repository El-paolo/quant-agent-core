"""
Asset correlation and beta analysis.

Functions:
  - correlation_matrix  — Pearson/Spearman/Kendall correlation matrix for
                          a multi-asset returns DataFrame.
  - rolling_correlation — Rolling pairwise correlation between two return series.
  - compute_beta        — Market beta, Jensen's alpha, R², and correlation for
                          a single asset vs. a market benchmark.

Formula reference:
  Beta  = Cov(asset, market) / Var(market)
  Alpha = mean(asset) - beta * mean(market)           (per-period, not annualized)
  R²    = correlation(asset, market) ** 2

Security notes:
  - No external data is fetched in this module.
  - The method parameter is validated against an explicit allowlist.
  - The window parameter is bounded to prevent memory exhaustion on very large
    inputs with an absurdly small window.
"""

import numpy as np
import pandas as pd

from fina.core.exceptions import MetricsError


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_METHODS = frozenset({"pearson", "spearman", "kendall"})
_MIN_WINDOW = 2


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _validate_returns_series(returns: object, name: str = "returns") -> pd.Series:
    if not isinstance(returns, pd.Series):
        raise MetricsError(
            f"'{name}' must be a pandas Series; got {type(returns).__name__}."
        )
    if len(returns) < 2:
        raise MetricsError(
            f"'{name}' must have at least 2 observations; got {len(returns)}."
        )
    if returns.isnull().any():
        raise MetricsError(
            f"'{name}' contains NaN values. Clean data before computing correlation."
        )
    result: pd.Series = returns
    return result


def _validate_returns_df(returns: object) -> pd.DataFrame:
    if not isinstance(returns, pd.DataFrame):
        raise MetricsError(
            f"'returns' must be a pandas DataFrame; got {type(returns).__name__}."
        )
    if returns.shape[1] < 2:
        raise MetricsError(
            "DataFrame must have at least 2 columns (assets) to compute a "
            f"correlation matrix; got {returns.shape[1]}."
        )
    if len(returns) < 2:
        raise MetricsError(
            f"DataFrame must have at least 2 rows; got {len(returns)}."
        )
    if returns.isnull().any().any():
        raise MetricsError(
            "Returns DataFrame contains NaN values. Clean data before computing "
            "the correlation matrix."
        )
    result: pd.DataFrame = returns
    return result


def _validate_method(method: str) -> None:
    if method not in _VALID_METHODS:
        raise MetricsError(
            f"Invalid method '{method}'. "
            f"Valid options: {sorted(_VALID_METHODS)}."
        )


def _validate_window(window: int, max_len: int) -> None:
    if not isinstance(window, int) or window < _MIN_WINDOW:
        raise MetricsError(
            f"'window' must be an integer >= {_MIN_WINDOW}; got {window!r}."
        )
    if window > max_len:
        raise MetricsError(
            f"'window' ({window}) exceeds the number of observations ({max_len})."
        )


def _align_series(
    a: pd.Series, b: pd.Series
) -> tuple[pd.Series, pd.Series]:
    """Align two series on their shared index, raising if alignment leaves < 2 rows."""
    a_aligned, b_aligned = a.align(b, join="inner")
    if len(a_aligned) < 2:
        raise MetricsError(
            "After aligning on a common index, fewer than 2 observations remain. "
            "Ensure both series share enough overlapping dates."
        )
    if a_aligned.isnull().any() or b_aligned.isnull().any():
        raise MetricsError(
            "Aligned series contain NaN values. Clean data before computing correlation."
        )
    result_a: pd.Series = a_aligned
    result_b: pd.Series = b_aligned
    return result_a, result_b


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def correlation_matrix(
    returns: pd.DataFrame,
    method: str = "pearson",
) -> pd.DataFrame:
    """
    Compute a pairwise correlation matrix for a multi-asset returns DataFrame.

    Args:
        returns: DataFrame where each column is an asset's return series.
                 Must have at least 2 columns and 2 rows, no NaN values.
        method:  Correlation method — ``"pearson"`` (linear), ``"spearman"``
                 (rank-based, robust to outliers), or ``"kendall"`` (concordance).
                 Default: ``"pearson"``.

    Returns:
        Square pd.DataFrame of shape (n_assets, n_assets) with correlation
        coefficients on [-1, 1]. Diagonal entries are always 1.0.

    Raises:
        MetricsError: On invalid input type, insufficient data, NaN values,
                      or unknown method.
    """
    returns = _validate_returns_df(returns)
    _validate_method(method)

    result: pd.DataFrame = returns.corr(method=method)
    return result


def rolling_correlation(
    returns_a: pd.Series,
    returns_b: pd.Series,
    window: int = 20,
) -> pd.Series:
    """
    Compute the rolling Pearson correlation between two return series.

    The two series are aligned on their shared index before rolling is applied,
    so mismatched calendars (e.g. equities vs. crypto) are handled gracefully.

    Args:
        returns_a: First return series.
        returns_b: Second return series.
        window:    Rolling window size (number of periods).  Must be >= 2 and
                   <= number of overlapping observations.

    Returns:
        pd.Series of rolling correlations with the same index as the aligned
        input.  The first ``window - 1`` values are NaN (insufficient history).

    Raises:
        MetricsError: On invalid types, NaN values, insufficient overlap,
                      or out-of-range window.
    """
    returns_a = _validate_returns_series(returns_a, "returns_a")
    returns_b = _validate_returns_series(returns_b, "returns_b")

    a, b = _align_series(returns_a, returns_b)
    _validate_window(window, len(a))

    result: pd.Series = a.rolling(window=window).corr(b)
    return result


def compute_beta(
    asset_returns: pd.Series,
    market_returns: pd.Series,
) -> dict:
    """
    Compute the market beta and related statistics for an asset vs. a benchmark.

    Uses ordinary least-squares in closed form:

        beta  = Cov(asset, market) / Var(market)
        alpha = mean(asset) - beta * mean(market)   (per-period)
        R²    = corr(asset, market)²

    Args:
        asset_returns:  Return series for the asset under analysis.
        market_returns: Return series for the market benchmark (e.g. SPY).

    Returns:
        dict with keys:
          - ``"beta"``            (float) — sensitivity to market moves
          - ``"alpha"``           (float) — per-period excess return vs. beta prediction
          - ``"correlation"``     (float) — Pearson correlation with the market
          - ``"r_squared"``       (float) — proportion of variance explained by market
          - ``"market_variance"`` (float) — variance of the market return series
          - ``"observations"``    (int)   — number of aligned observations used

    Raises:
        MetricsError: On invalid types, NaN values, insufficient overlap,
                      or zero market variance (undefined beta).
    """
    asset_returns = _validate_returns_series(asset_returns, "asset_returns")
    market_returns = _validate_returns_series(market_returns, "market_returns")

    asset, market = _align_series(asset_returns, market_returns)

    market_var: float = float(market.var())
    if market_var == 0:
        raise MetricsError(
            "Beta is undefined: market return series has zero variance."
        )

    cov_matrix = np.cov(asset.values, market.values, ddof=1)
    cov_asset_market: float = float(cov_matrix[0, 1])
    beta: float = cov_asset_market / market_var

    mean_asset: float = float(asset.mean())
    mean_market: float = float(market.mean())
    alpha: float = mean_asset - beta * mean_market

    correlation: float = float(asset.corr(market))
    r_squared: float = correlation ** 2

    return {
        "beta": beta,
        "alpha": alpha,
        "correlation": correlation,
        "r_squared": r_squared,
        "market_variance": market_var,
        "observations": len(asset),
    }
