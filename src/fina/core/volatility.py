import pandas as pd
import numpy as np
from fina.core.returns import compute_returns

class VolatilityError(Exception):
    """Custom exception for errors in volatility calculations."""
    pass
def validate_returns(returns: pd.Series | pd.DataFrame) -> pd.Series:
    """Validate input returns series for volatility calculations."""
    if isinstance(returns, pd.DataFrame):
        if returns.shape[1] != 1:
            raise VolatilityError("Input DataFrame returns must have exactly one column.")
        returns = returns.iloc[:, 0]
    elif not isinstance(returns, pd.Series):
        raise VolatilityError("Input returns must be a pandas Series or single-column DataFrame.")
    return returns.sort_index()

def compute_realized_volatility(
        returns: pd.Series,
        window: int | None = None,
        annualize: bool = True,
        trading_days: int = 252) -> dict:
    """Calculate realized by default volatility from a series of returns."""

    if window is None:
        vol = returns.std()
    else:
        vol = returns.rolling(window=window).std()
    if annualize:
        vol *= np.sqrt(trading_days)
    return {
        'volatility(s.d.)': vol,
        'volatility(variance)': vol ** 2,
        'annualized': annualize,
        'trading_days': trading_days if annualize else None,
        'observations': len(returns)
    }