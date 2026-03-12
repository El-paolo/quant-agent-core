import pandas as pd
import numpy as np
from scipy.stats import norm
from fina.metrics.returns import compute_returns

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
    
    result: pd.Series = returns.sort_index()
    
    return result
def realized_volatility(
        returns: pd.Series,
        annualize: bool = True,
        trading_days: int = 252) -> dict:
    """Calculate realized by default volatility from a series of returns."""

    vol = returns.std()

    if annualize:
        vol *= np.sqrt(trading_days)
    return {
        'volatility(s.d.)': vol,
        'volatility(variance)': vol ** 2,
        'annualized': annualize,
        'trading_days': trading_days if annualize else None,
        'observations': len(returns)
    }

def rolling_volatility(
        returns: pd.Series,
        window: int ,
        annualize: bool = True,
        trading_days: int = 252) -> pd.DataFrame:
    
    """Calculate rolling realized volatility - returns a pd.Dataframe with the full time series"""
    returns = validate_returns(returns)
    if window >= len(returns):
        raise VolatilityError(
            f"Window must be smaller than the number of observations({len(returns)})."
        )
    vol = returns.rolling(window=window).std()
    if annualize:
        vol *= np.sqrt(trading_days)

    result = pd.DataFrame({
        'volatility': vol,
        'volatilty(variance)':vol ** 2
    })

    result.attrs = {
        'window': window,
        'annualized': annualize,
        'trading_days': trading_days if annualize else None
    }
    return result