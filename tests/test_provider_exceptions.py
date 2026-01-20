"""Tests for provider exceptions."""
import pytest
from app.providers.exceptions import (
    ProviderError,
    TickerNotFoundError,
    DataNotAvailableError
)


class TestProviderError:
    """Tests for ProviderError base exception."""

    def test_provider_error_is_exception(self):
        """Test that ProviderError is an Exception."""
        assert issubclass(ProviderError, Exception)

    def test_provider_error_can_be_raised(self):
        """Test that ProviderError can be raised."""
        with pytest.raises(ProviderError):
            raise ProviderError("Test error")

    def test_provider_error_message(self):
        """Test that ProviderError stores error message."""
        try:
            raise ProviderError("Custom error message")
        except ProviderError as e:
            assert str(e) == "Custom error message"


class TestTickerNotFoundError:
    """Tests for TickerNotFoundError."""

    def test_ticker_not_found_error_is_provider_error(self):
        """Test that TickerNotFoundError inherits from ProviderError."""
        assert issubclass(TickerNotFoundError, ProviderError)

    def test_ticker_not_found_error_can_be_raised(self):
        """Test that TickerNotFoundError can be raised."""
        with pytest.raises(TickerNotFoundError):
            raise TickerNotFoundError("Ticker INVALID not found")

    def test_ticker_not_found_error_message(self):
        """Test that TickerNotFoundError stores error message."""
        try:
            raise TickerNotFoundError("Ticker XYZ not found")
        except TickerNotFoundError as e:
            assert "XYZ" in str(e)

    def test_ticker_not_found_error_caught_as_provider_error(self):
        """Test that TickerNotFoundError can be caught as ProviderError."""
        with pytest.raises(ProviderError):
            raise TickerNotFoundError("Test")


class TestDataNotAvailableError:
    """Tests for DataNotAvailableError."""

    def test_data_not_available_error_is_provider_error(self):
        """Test that DataNotAvailableError inherits from ProviderError."""
        assert issubclass(DataNotAvailableError, ProviderError)

    def test_data_not_available_error_can_be_raised(self):
        """Test that DataNotAvailableError can be raised."""
        with pytest.raises(DataNotAvailableError):
            raise DataNotAvailableError("Data not available")

    def test_data_not_available_error_message(self):
        """Test that DataNotAvailableError stores error message."""
        try:
            raise DataNotAvailableError("Historical data not available for AAPL")
        except DataNotAvailableError as e:
            assert "AAPL" in str(e)

    def test_data_not_available_error_caught_as_provider_error(self):
        """Test that DataNotAvailableError can be caught as ProviderError."""
        with pytest.raises(ProviderError):
            raise DataNotAvailableError("Test")


class TestExceptionHierarchy:
    """Tests for exception hierarchy and polymorphism."""

    def test_all_custom_exceptions_caught_as_provider_error(self):
        """Test that all custom exceptions can be caught as ProviderError."""
        exceptions = [
            TickerNotFoundError("Ticker not found"),
            DataNotAvailableError("Data not available")
        ]

        for exception in exceptions:
            with pytest.raises(ProviderError):
                raise exception

    def test_specific_exception_types_can_be_distinguished(self):
        """Test that specific exception types can be distinguished."""
        def raise_ticker_not_found():
            raise TickerNotFoundError("Ticker not found")

        def raise_data_not_available():
            raise DataNotAvailableError("Data not available")

        # Can catch specifically
        with pytest.raises(TickerNotFoundError):
            raise_ticker_not_found()

        with pytest.raises(DataNotAvailableError):
            raise_data_not_available()

    def test_exception_handling_pattern(self):
        """Test a typical exception handling pattern."""
        def fetch_data(ticker: str, raise_type: str = None):
            """Mock function that raises different exceptions."""
            if raise_type == "not_found":
                raise TickerNotFoundError(f"Ticker {ticker} not found")
            elif raise_type == "no_data":
                raise DataNotAvailableError(f"Data for {ticker} not available")
            return {"ticker": ticker, "price": 150.0}

        # Normal case
        result = fetch_data("AAPL")
        assert result["ticker"] == "AAPL"

        # Ticker not found case
        try:
            fetch_data("INVALID", raise_type="not_found")
            assert False, "Should have raised exception"
        except TickerNotFoundError as e:
            assert "INVALID" in str(e)

        # Data not available case
        try:
            fetch_data("AAPL", raise_type="no_data")
            assert False, "Should have raised exception"
        except DataNotAvailableError as e:
            assert "AAPL" in str(e)

        # Generic provider error handling
        try:
            fetch_data("TEST", raise_type="no_data")
            assert False, "Should have raised exception"
        except ProviderError as e:
            # Can catch all provider errors generically
            assert isinstance(e, (TickerNotFoundError, DataNotAvailableError))
