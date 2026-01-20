"""Tests for stock data provider abstraction."""
import pytest
from datetime import date, datetime, timedelta
from app.providers.base import StockPriceData, StockInfo, OptionQuote, OptionsChain
from app.providers.yfinance_provider import YFinanceProvider
from app.providers.factory import ProviderFactory
from app.providers.exceptions import TickerNotFoundError, DataNotAvailableError


class TestYFinanceProvider:
    """Tests for YFinanceProvider."""
    
    def test_validate_ticker_valid(self):
        """Test validating a valid ticker."""
        provider = YFinanceProvider()
        assert provider.validate_ticker('AAPL') is True
        assert provider.validate_ticker('MSFT') is True
    
    def test_validate_ticker_invalid(self):
        """Test validating an invalid ticker."""
        provider = YFinanceProvider()
        assert provider.validate_ticker('INVALIDTICKER12345') is False
    
    def test_get_provider_name(self):
        """Test getting provider name."""
        provider = YFinanceProvider()
        assert provider.get_provider_name() == 'YFinanceProvider'
    
    def test_fetch_historical_prices(self):
        """Test fetching historical prices."""
        provider = YFinanceProvider()
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        prices = provider.fetch_historical_prices('AAPL', start_date, end_date)
        
        assert len(prices) > 0
        assert all(isinstance(p, StockPriceData) for p in prices)
        assert all(p.date >= start_date for p in prices)
        assert all(p.date < end_date for p in prices)
        # Verify data structure
        first_price = prices[0]
        assert isinstance(first_price.open, float)
        assert isinstance(first_price.high, float)
        assert isinstance(first_price.low, float)
        assert isinstance(first_price.close, float)
        assert isinstance(first_price.volume, int)
    
    def test_fetch_historical_prices_invalid_ticker(self):
        """Test fetching historical prices for invalid ticker."""
        provider = YFinanceProvider()
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        with pytest.raises(TickerNotFoundError):
            provider.fetch_historical_prices('INVALIDTICKER12345', start_date, end_date)
    
    def test_fetch_stock_info(self):
        """Test fetching stock info."""
        provider = YFinanceProvider()
        
        info = provider.fetch_stock_info('AAPL')
        
        assert isinstance(info, StockInfo)
        assert info.ticker == 'AAPL'
        assert info.current_price is not None
        assert info.current_price > 0
    
    def test_fetch_stock_info_invalid_ticker(self):
        """Test fetching stock info for invalid ticker."""
        provider = YFinanceProvider()
        
        with pytest.raises(TickerNotFoundError):
            provider.fetch_stock_info('INVALIDTICKER12345')
    
    def test_fetch_options_expirations(self):
        """Test fetching options expirations."""
        provider = YFinanceProvider()
        
        expirations = provider.fetch_options_expirations('AAPL')
        
        assert len(expirations) > 0
        assert all(isinstance(exp, str) for exp in expirations)
        # Verify format is YYYY-MM-DD
        for exp in expirations:
            datetime.strptime(exp, '%Y-%m-%d')  # Should not raise
    
    def test_fetch_options_expirations_no_options(self):
        """Test fetching options expirations for stock without options."""
        provider = YFinanceProvider()
        
        # Some stocks may not have options - this might raise DataNotAvailableError
        # or return empty list depending on the stock
        try:
            expirations = provider.fetch_options_expirations('BRK.A')
            # If it doesn't raise, should return empty list or raise
            if expirations:
                assert all(isinstance(exp, str) for exp in expirations)
        except DataNotAvailableError:
            # This is acceptable for stocks without options
            pass
    
    def test_fetch_options_chain(self):
        """Test fetching options chain."""
        provider = YFinanceProvider()
        
        # Get an expiration date first
        expirations = provider.fetch_options_expirations('AAPL')
        if not expirations:
            pytest.skip("No options expirations available for AAPL")
        
        expiration = expirations[0]
        chain = provider.fetch_options_chain('AAPL', expiration)
        
        assert isinstance(chain, OptionsChain)
        assert chain.expiration == expiration
        assert len(chain.calls) > 0 or len(chain.puts) > 0
        
        # Verify OptionQuote structure
        if chain.calls:
            call = chain.calls[0]
            assert isinstance(call, OptionQuote)
            assert isinstance(call.strike, float)
            assert call.strike > 0
    
    def test_fetch_intraday_prices(self):
        """Test fetching intraday prices."""
        provider = YFinanceProvider()
        today = date.today()
        
        # Intraday data may not be available (market closed, etc.)
        intraday = provider.fetch_intraday_prices('AAPL', today)
        
        # Should return None or list of StockPriceData
        if intraday is not None:
            assert len(intraday) > 0
            assert all(isinstance(p, StockPriceData) for p in intraday)
            assert all(p.date == today for p in intraday)


class TestProviderFactory:
    """Tests for ProviderFactory."""
    
    def test_get_provider_yfinance(self):
        """Test getting yfinance provider."""
        provider = ProviderFactory.get_provider('yfinance')
        assert isinstance(provider, YFinanceProvider)
    
    def test_get_provider_default(self):
        """Test getting default provider."""
        provider = ProviderFactory.get_default_provider()
        assert isinstance(provider, YFinanceProvider)
    
    def test_get_provider_unknown(self):
        """Test getting unknown provider."""
        with pytest.raises(ValueError, match="Unknown provider"):
            ProviderFactory.get_provider('unknown_provider')
    
    def test_get_default_provider_singleton(self):
        """Test that default provider is a singleton."""
        ProviderFactory.reset_default_provider()
        provider1 = ProviderFactory.get_default_provider()
        provider2 = ProviderFactory.get_default_provider()
        assert provider1 is provider2

    def test_get_options_provider_default(self):
        """Test getting options provider without MarketData API key."""
        import os
        # Ensure no MarketData key is set
        original_key = os.environ.pop('MARKETDATA_API_KEY', None)
        ProviderFactory.reset_options_provider()

        try:
            provider = ProviderFactory.get_options_provider()
            # Should fall back to default provider (yfinance)
            assert isinstance(provider, YFinanceProvider)
        finally:
            if original_key:
                os.environ['MARKETDATA_API_KEY'] = original_key

    def test_get_options_provider_singleton(self):
        """Test that options provider is a singleton."""
        ProviderFactory.reset_options_provider()
        provider1 = ProviderFactory.get_options_provider()
        provider2 = ProviderFactory.get_options_provider()
        assert provider1 is provider2

    def test_reset_all_providers(self):
        """Test resetting all providers."""
        # Get providers first
        ProviderFactory.get_default_provider()
        ProviderFactory.get_options_provider()

        # Reset all
        ProviderFactory.reset_all_providers()

        # Verify they are None
        assert ProviderFactory._default_provider is None
        assert ProviderFactory._options_provider is None

    def test_get_provider_case_insensitive(self):
        """Test that provider name is case insensitive."""
        provider1 = ProviderFactory.get_provider('YFINANCE')
        provider2 = ProviderFactory.get_provider('YFinance')
        provider3 = ProviderFactory.get_provider('yfinance')

        assert isinstance(provider1, YFinanceProvider)
        assert isinstance(provider2, YFinanceProvider)
        assert isinstance(provider3, YFinanceProvider)

    def test_get_provider_from_environment(self):
        """Test provider selection from environment variable."""
        import os
        original = os.environ.get('STOCK_DATA_PROVIDER')
        os.environ['STOCK_DATA_PROVIDER'] = 'yfinance'

        try:
            provider = ProviderFactory.get_provider()
            assert isinstance(provider, YFinanceProvider)
        finally:
            if original:
                os.environ['STOCK_DATA_PROVIDER'] = original
            else:
                os.environ.pop('STOCK_DATA_PROVIDER', None)
