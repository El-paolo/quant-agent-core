"""
Centralized custom exceptions for the FINA package.

All modules must raise these exceptions — never propagate raw library errors.
"""


class FetcherError(Exception):
    """Raised when data acquisition fails (network, bad ticker, empty response)."""


class MetricsError(Exception):
    """Base class for errors in any metrics computation."""


class ReturnsError(MetricsError):
    """Raised when returns calculation fails (bad input, insufficient data)."""


class VolatilityError(MetricsError):
    """Raised when volatility calculation fails (bad input, window too large)."""


class ValidationError(Exception):
    """Raised when input validation fails at any layer boundary."""


class BacktestError(MetricsError):
    """Raised when backtesting fails (insufficient data, invalid date ranges)."""


class ConfigError(Exception):
    """Raised when required configuration (env vars, settings) is missing or invalid."""
