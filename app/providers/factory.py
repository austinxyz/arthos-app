"""Factory for creating stock data providers."""
from app.providers.base import StockDataProvider
from app.providers.yfinance_provider import YFinanceProvider
from typing import Optional
import os

import logging

logger = logging.getLogger(__name__)


class ProviderFactory:
    """Factory for creating stock data providers."""
    
    _default_provider: Optional[StockDataProvider] = None
    _options_provider: Optional[StockDataProvider] = None
    
    @staticmethod
    def get_provider(provider_name: Optional[str] = None) -> StockDataProvider:
        """
        Get a stock data provider instance.
        
        Args:
            provider_name: Name of provider ('yfinance', 'marketdata', etc.)
                          If None, uses default from environment or 'yfinance'
        
        Returns:
            StockDataProvider instance
            
        Raises:
            ValueError: If provider name is unknown
        """
        if provider_name is None:
            provider_name = os.getenv('STOCK_DATA_PROVIDER', 'yfinance')
        
        provider_name = provider_name.lower()
        
        if provider_name == 'yfinance':
            return YFinanceProvider()
        elif provider_name == 'marketdata':
            from app.providers.marketdata_provider import MarketDataProvider
            return MarketDataProvider()
        else:
            raise ValueError(f"Unknown provider: {provider_name}")
    
    @staticmethod
    def get_default_provider() -> StockDataProvider:
        """
        Get or create the default provider instance (singleton pattern).
        Used for stock data (prices, fundamentals).
        
        Returns:
            Default StockDataProvider instance
        """
        if ProviderFactory._default_provider is None:
            ProviderFactory._default_provider = ProviderFactory.get_provider()
            logger.info(f"Initialized default provider: {ProviderFactory._default_provider.get_provider_name()}")
        return ProviderFactory._default_provider
    
    @staticmethod
    def get_options_provider() -> StockDataProvider:
        """
        Get the provider for options data with Greeks.
        Uses MarketData.app if API key is configured, otherwise falls back to yfinance.
        
        Returns:
            StockDataProvider instance for options data
        """
        if ProviderFactory._options_provider is None:
            # Check if MarketData API key is configured
            marketdata_key = os.getenv('MARKETDATA_API_KEY')
            if marketdata_key:
                from app.providers.marketdata_provider import MarketDataProvider
                ProviderFactory._options_provider = MarketDataProvider(marketdata_key)
                logger.info("Initialized MarketData.app as options provider")
            else:
                # Fall back to default provider (yfinance)
                ProviderFactory._options_provider = ProviderFactory.get_default_provider()
                logger.info("MarketData API key not configured, using yfinance for options")
        return ProviderFactory._options_provider
    
    @staticmethod
    def reset_default_provider():
        """Reset the default provider (useful for testing)."""
        ProviderFactory._default_provider = None
    
    @staticmethod
    def reset_options_provider():
        """Reset the options provider (useful for testing)."""
        ProviderFactory._options_provider = None
    
    @staticmethod
    def reset_all_providers():
        """Reset all providers (useful for testing)."""
        ProviderFactory._default_provider = None
        ProviderFactory._options_provider = None