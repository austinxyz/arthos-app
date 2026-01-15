# Refactoring Plan: Stock Data Provider Abstraction

## Executive Summary

This plan outlines a refactoring strategy to abstract stock data fetching from yfinance, enabling support for multiple data providers (yfinance, Alpha Vantage, Polygon, etc.) while keeping business logic provider-agnostic.

## Current State Analysis

### yfinance Usage Locations

1. **`app/services/stock_price_service.py`**
   - Fetches historical daily OHLC data
   - Fetches intraday data (1-minute bars)
   - Fetches dividend information (`stock.info['dividendRate']`, `stock.info['dividendYield']`)
   - Fetches earnings data (`stock.info['earningsTimestamp']`, `stock.info['isEarningsDateEstimate']`)
   - Handles timezone normalization
   - Suppresses stderr warnings

2. **`app/services/stock_service.py`**
   - Fetches historical stock data (`stock.history()`)
   - Fetches intraday data (`stock.history(period='1d', interval='1m')`)
   - Fetches options data (`stock.options`, `stock.option_chain()`)
   - Calculates risk reversal strategies (depends on options data)

3. **`app/services/rr_watchlist_service.py`**
   - Fetches options chain for specific expiration (`stock.option_chain(expiration)`)
   - Extracts bid/ask prices from options

4. **`app/services/scheduler_service.py`**
   - Fetches options chain for RR history updates
   - Similar to rr_watchlist_service

5. **`app/services/watchlist_service.py`**
   - Validates ticker existence using yfinance

### Data Types Fetched

1. **Stock Price Data**
   - Historical daily OHLC (Open, High, Low, Close, Volume)
   - Intraday data (1-minute bars)
   - Date ranges and timezone handling

2. **Stock Information**
   - Dividend amount and yield
   - Earnings date and estimate flag
   - Current price

3. **Options Data**
   - Expiration dates
   - Options chain (calls and puts)
   - Strike prices
   - Bid/ask prices
   - Volume, open interest
   - Implied volatility
   - Contract symbols

## Design Principles

1. **Separation of Concerns**: Business logic should not know about data providers
2. **Open/Closed Principle**: Open for extension (new providers), closed for modification
3. **Dependency Inversion**: High-level modules depend on abstractions, not concretions
4. **Provider-Specific Features**: Handle gracefully when a provider doesn't support a feature
5. **Backward Compatibility**: Maintain existing functionality during migration
6. **Testability**: Easy to mock providers for testing

## Proposed Architecture

### 1. Abstract Base Class / Protocol

Create `app/providers/base.py` with an abstract base class defining the interface:

```python
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any
from datetime import date, datetime
import pandas as pd
from dataclasses import dataclass

@dataclass
class StockPriceData:
    """Standardized stock price data structure"""
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int

@dataclass
class StockInfo:
    """Standardized stock information"""
    ticker: str
    current_price: Optional[float]
    dividend_amount: Optional[float]
    dividend_yield: Optional[float]
    next_earnings_date: Optional[date]
    is_earnings_date_estimate: Optional[bool]

@dataclass
class OptionQuote:
    """Standardized option quote data"""
    contract_symbol: str
    strike: float
    bid: Optional[float]
    ask: Optional[float]
    last_price: Optional[float]
    volume: Optional[int]
    open_interest: Optional[int]
    implied_volatility: Optional[float]

@dataclass
class OptionsChain:
    """Standardized options chain data"""
    expiration: str  # YYYY-MM-DD format
    calls: List[OptionQuote]
    puts: List[OptionQuote]

class StockDataProvider(ABC):
    """Abstract base class for stock data providers"""
    
    @abstractmethod
    def validate_ticker(self, ticker: str) -> bool:
        """Validate if a ticker exists and is valid"""
        pass
    
    @abstractmethod
    def fetch_historical_prices(
        self, 
        ticker: str, 
        start_date: date, 
        end_date: date
    ) -> List[StockPriceData]:
        """Fetch historical daily OHLC data"""
        pass
    
    @abstractmethod
    def fetch_intraday_prices(
        self, 
        ticker: str, 
        target_date: date
    ) -> Optional[List[StockPriceData]]:
        """Fetch intraday data for a specific date"""
        pass
    
    @abstractmethod
    def fetch_stock_info(self, ticker: str) -> StockInfo:
        """Fetch stock information (dividend, earnings, current price)"""
        pass
    
    @abstractmethod
    def fetch_options_expirations(self, ticker: str) -> List[str]:
        """Fetch available options expiration dates (YYYY-MM-DD format)"""
        pass
    
    @abstractmethod
    def fetch_options_chain(
        self, 
        ticker: str, 
        expiration: str
    ) -> OptionsChain:
        """Fetch options chain for a specific expiration"""
        pass
    
    def get_provider_name(self) -> str:
        """Return provider name for logging/debugging"""
        return self.__class__.__name__
```

### 2. yfinance Implementation

Create `app/providers/yfinance_provider.py` implementing the abstract class:

```python
from app.providers.base import (
    StockDataProvider, 
    StockPriceData, 
    StockInfo, 
    OptionsChain, 
    OptionQuote
)
import yfinance as yf
import pandas as pd
from datetime import date, datetime
from typing import Optional, List
import warnings
import sys
from io import StringIO

class YFinanceProvider(StockDataProvider):
    """yfinance implementation of StockDataProvider"""
    
    def validate_ticker(self, ticker: str) -> bool:
        # Implementation
        pass
    
    def fetch_historical_prices(self, ticker: str, start_date: date, end_date: date) -> List[StockPriceData]:
        # Implementation with stderr suppression
        pass
    
    # ... other methods
```

### 3. Provider Factory

Create `app/providers/factory.py` for provider selection:

```python
from app.providers.base import StockDataProvider
from app.providers.yfinance_provider import YFinanceProvider
from typing import Optional
import os

class ProviderFactory:
    """Factory for creating stock data providers"""
    
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
        """
        if provider_name is None:
            provider_name = os.getenv('STOCK_DATA_PROVIDER', 'yfinance')
        
        if provider_name == 'yfinance':
            return YFinanceProvider()
        # Future: elif provider_name == 'alpha_vantage':
        #     return AlphaVantageProvider()
        else:
            raise ValueError(f"Unknown provider: {provider_name}")
    
    @staticmethod
    def get_default_provider() -> StockDataProvider:
        """Get or create the default provider instance (singleton pattern)"""
        if ProviderFactory._default_provider is None:
            ProviderFactory._default_provider = ProviderFactory.get_provider()
        return ProviderFactory._default_provider
```

### 4. Service Layer Refactoring

Refactor services to use the provider abstraction:

**Before:**
```python
import yfinance as yf
stock = yf.Ticker(ticker)
hist = stock.history(start=start_date, end=end_date)
```

**After:**
```python
from app.providers.factory import ProviderFactory
provider = ProviderFactory.get_default_provider()
price_data = provider.fetch_historical_prices(ticker, start_date, end_date)
```

### 5. Data Conversion Layer

Create helper functions to convert provider data to pandas DataFrames (for backward compatibility with existing code):

```python
# app/providers/converters.py
def stock_price_data_to_dataframe(price_data: List[StockPriceData]) -> pd.DataFrame:
    """Convert list of StockPriceData to pandas DataFrame"""
    # Implementation
    pass
```

## Migration Strategy

### Phase 1: Foundation (Non-Breaking)
1. Create `app/providers/` directory structure
2. Implement abstract base class with all method signatures
3. Implement `YFinanceProvider` with full functionality
4. Create provider factory
5. Add unit tests for provider abstraction

### Phase 2: Service Migration (Incremental)
1. Refactor `stock_price_service.py`:
   - Replace direct yfinance calls with provider calls
   - Convert provider data to pandas DataFrames for existing code
   - Maintain backward compatibility
2. Refactor `stock_service.py`:
   - Replace options fetching with provider calls
   - Update risk reversal calculations to use provider data
3. Refactor `rr_watchlist_service.py`:
   - Replace options chain fetching
4. Refactor `scheduler_service.py`:
   - Replace options chain fetching
5. Refactor `watchlist_service.py`:
   - Replace ticker validation

### Phase 3: Testing & Validation
1. Run all existing tests to ensure no regressions
2. Add integration tests for provider abstraction
3. Test with multiple providers (when available)
4. Performance testing

### Phase 4: Future Providers
1. Add Alpha Vantage provider (example)
2. Add provider selection logic (e.g., fallback if primary fails)
3. Add provider-specific feature detection

## File Structure

```
app/
├── providers/
│   ├── __init__.py
│   ├── base.py              # Abstract base class and data classes
│   ├── yfinance_provider.py # yfinance implementation
│   ├── factory.py           # Provider factory
│   ├── converters.py        # Data conversion utilities
│   └── exceptions.py        # Provider-specific exceptions
├── services/
│   ├── stock_price_service.py  # Refactored to use providers
│   ├── stock_service.py        # Refactored to use providers
│   └── ...
└── ...
```

## Key Design Decisions

### 1. Data Transfer Objects (DTOs)
- Use dataclasses for standardized data structures
- Ensures consistent data format across providers
- Makes it easy to add new providers

### 2. Provider Factory Pattern
- Centralized provider creation
- Easy to switch providers via environment variable
- Singleton pattern for default provider (performance)

### 3. Backward Compatibility
- Convert provider data to pandas DataFrames where needed
- Existing business logic continues to work
- Gradual migration path

### 4. Error Handling
- Provider-specific exceptions
- Graceful degradation when features aren't available
- Logging for debugging

### 5. Provider-Specific Features
- Some providers may not support all features
- Use Optional types and None checks
- Document provider capabilities

## Testing Strategy

1. **Unit Tests**
   - Test abstract base class interface
   - Test YFinanceProvider implementation
   - Test provider factory
   - Test data converters

2. **Integration Tests**
   - Test service layer with provider abstraction
   - Test end-to-end data flow
   - Test error handling

3. **Mock Tests**
   - Mock providers for business logic tests
   - Test provider switching logic

## Benefits

1. **Flexibility**: Easy to add new data providers
2. **Testability**: Easy to mock providers for testing
3. **Maintainability**: Clear separation of concerns
4. **Scalability**: Can support multiple providers simultaneously
5. **Reliability**: Can implement fallback logic if primary provider fails

## Risks & Mitigation

1. **Risk**: Breaking existing functionality during migration
   - **Mitigation**: Incremental migration, comprehensive testing, backward compatibility layer

2. **Risk**: Performance overhead from abstraction
   - **Mitigation**: Use singleton pattern, minimal data conversion overhead

3. **Risk**: Provider API changes
   - **Mitigation**: Encapsulate provider-specific logic, version provider implementations

## Implementation Checklist

- [ ] Create `app/providers/` directory
- [ ] Implement abstract base class (`base.py`)
- [ ] Implement YFinanceProvider
- [ ] Create provider factory
- [ ] Create data converters
- [ ] Refactor `stock_price_service.py`
- [ ] Refactor `stock_service.py`
- [ ] Refactor `rr_watchlist_service.py`
- [ ] Refactor `scheduler_service.py`
- [ ] Refactor `watchlist_service.py`
- [ ] Update tests
- [ ] Add integration tests
- [ ] Update documentation

## Future Enhancements

1. **Multi-Provider Support**
   - Fallback logic if primary provider fails
   - Provider selection based on data availability
   - Load balancing across providers

2. **Caching Layer**
   - Cache provider responses
   - Reduce API calls
   - Improve performance

3. **Provider Health Monitoring**
   - Track provider availability
   - Automatic failover
   - Performance metrics

4. **Configuration Management**
   - Provider-specific configuration
   - API keys management
   - Rate limiting configuration
