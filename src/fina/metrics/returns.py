import pandas as pd
import numpy as np

class ReturnsError(Exception):
    """Custom exception for errors in returns calculations."""
    pass

def validate_prices(prices: pd.Series | pd.DataFrame) -> pd.Series:
    """
    Validate input prices series
    and calculate returns

    Assumptions:
    - Prices must be positive numbers
    - At least two price points are required
    - index must be sortables
    - Must not have null values

    """
    if isinstance(prices, pd.DataFrame):
        if prices.shape[1] != 1:
            raise ReturnsError("Input DataFrame must have exactly one column.")
        prices = prices.iloc[:, 0]
    elif not isinstance(prices, pd.Series):
        raise ReturnsError("Input prices must be a pandas Series or single-column DataFrame.")

    if len(prices) < 2:
        raise ReturnsError("At least two price points are required to calculate returns.")
    if (prices <= 0).any():
        raise ReturnsError("Prices must be strictly positive.")
    prices = prices.sort_index()

    if (prices.isnull().any()):
        raise ReturnsError("Prices must not contain null values.")
    
    return prices

def simple_returns(prices: pd.Series) -> pd.Series:
    """
    Calculate simple returns from a series of prices.
    """
    prices = validate_prices(prices)
    returns = prices.pct_change().dropna()
    return returns

def log_returns(prices: pd.Series) -> pd.Series:
    """
    Calculate log returns from a series of prices.
    """
    prices = validate_prices(prices)
    returns = np.log(prices / prices.shift(1))
    returns = pd.Series(returns, index=prices.index).dropna()
    return returns

def compute_returns(prices: pd.Series,
                    method: str = 'log'
) -> pd.Series | dict:
    """
    General returns interface
    Parameters:
    - prices: pd.Series of prices
    - method: 'log' or 'simple'
    Returns:
    - dict: keys are 'returns' and 'method', values are pd.Series and str respectively.
    - method: str specifies the type of returns calculated.
    - observation: int number of return observations calculated.
    """

    if method not in ['log', 'simple']:
        raise ReturnsError("Method must be either 'log' or 'simple'.")
    if method == 'log':
        returns = log_returns(prices)
    else:
        returns = simple_returns(prices)
    return {
        'returns': returns,
        'method': method,
        'observations': len(returns)
    }
