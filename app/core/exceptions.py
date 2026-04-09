class TradingError(Exception):
    """Base application exception for trading runtime errors."""


class ConfigurationError(TradingError):
    """Raised when runtime configuration is invalid."""


class RiskCheckFailed(TradingError):
    """Raised when the risk engine blocks an order."""


class ExchangeAdapterError(TradingError):
    """Raised when an exchange adapter cannot satisfy a request."""
