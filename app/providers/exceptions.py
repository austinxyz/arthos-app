"""Custom exceptions for stock data providers."""


class ProviderError(Exception):
    """Base exception for all provider-related errors."""
    pass


class TickerNotFoundError(ProviderError):
    """Raised when a ticker is not found or invalid."""
    pass


class DataNotAvailableError(ProviderError):
    """Raised when requested data is not available from the provider."""
    pass
