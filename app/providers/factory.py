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
    
    @staticmethod
    def get_provider(provider_name: Optional[str] = None) -> StockDataProvider:
        """
        Get a stock data provider instance.
        
        Args:
            provider_name: Name of provider ('yfinance', 'alpha_vantage', etc.)
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
        # Future: elif provider_name == 'alpha_vantage':
        #     return AlphaVantageProvider()
        else:
            raise ValueError(f"Unknown provider: {provider_name}")
    
    @staticmethod
    def get_default_provider() -> StockDataProvider:
        """
        Get or create the default provider instance (singleton pattern).
        
        Returns:
            Default StockDataProvider instance
        """
        if ProviderFactory._default_provider is None:
            ProviderFactory._default_provider = ProviderFactory.get_provider()
            logger.info(f"Initialized default provider: {ProviderFactory._default_provider.get_provider_name()}")
        return ProviderFactory._default_provider
    
    @staticmethod
    def reset_default_provider():
        """Reset the default provider (useful for testing)."""
        ProviderFactory._default_provider = None
