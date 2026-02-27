import pandas as pd
import numpy as np


class ReturnsError(Exception):
    """Custom exception for errors in returns calculations."""
    pass

def validate_prices(prices: pd.Series) -> pd.Series:
    """
    Validate input prices series
    and calculate returns

    Assumptions:
    - Prices must be positive numbers
    - At least two price points are required
    - index must be sortables
    - Must not have null values

    """
    # The input is already expected to be a pandas Series due to the type hint.
    if len(prices) < 2:
        raise ReturnsError("At least two price points are required to calculate returns.")
    if (prices <= 0).any():
        raise ReturnsError("Prices must be strictly positive.")
    prices = prices.sort_index()

    if (prices.isnull().any()):
        raise ReturnsError("Prices must not contain null values.")
    
    return prices

    