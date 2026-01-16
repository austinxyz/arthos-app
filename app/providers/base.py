"""Abstract base class for stock data providers."""
from abc import ABC, abstractmethod
from typing import Optional, List
from datetime import date, datetime
from dataclasses import dataclass


@dataclass
class StockPriceData:
    """Standardized stock price data structure."""
    date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: Optional[datetime] = None  # Optional timestamp for intraday data (preserves time component)


@dataclass
class StockInfo:
    """Standardized stock information."""
    ticker: str
    current_price: Optional[float]
    dividend_amount: Optional[float]
    dividend_yield: Optional[float]
    next_earnings_date: Optional[date]
    is_earnings_date_estimate: Optional[bool]
    next_dividend_date: Optional[date] = None  # Ex-dividend date


@dataclass
class OptionQuote:
    """Standardized option quote data."""
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
    """Standardized options chain data."""
    expiration: str  # YYYY-MM-DD format
    calls: List[OptionQuote]
    puts: List[OptionQuote]


class StockDataProvider(ABC):
    """Abstract base class for stock data providers."""
    
    @abstractmethod
    def validate_ticker(self, ticker: str) -> bool:
        """
        Validate if a ticker exists and is valid.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            True if ticker is valid, False otherwise
        """
        pass
    
    @abstractmethod
    def fetch_historical_prices(
        self, 
        ticker: str, 
        start_date: date, 
        end_date: date
    ) -> List[StockPriceData]:
        """
        Fetch historical daily OHLC data.
        
        Args:
            ticker: Stock ticker symbol
            start_date: Start date (inclusive)
            end_date: End date (exclusive)
            
        Returns:
            List of StockPriceData objects, sorted by date ascending
            
        Raises:
            TickerNotFoundError: If ticker is invalid
            DataNotAvailableError: If data is not available for the date range
        """
        pass
    
    @abstractmethod
    def fetch_intraday_prices(
        self, 
        ticker: str, 
        target_date: date
    ) -> Optional[List[StockPriceData]]:
        """
        Fetch intraday data for a specific date.
        
        Args:
            ticker: Stock ticker symbol
            target_date: Date to fetch intraday data for
            
        Returns:
            List of StockPriceData objects (minute-by-minute), or None if not available
            Returns None if market is closed or data is not yet available
            
        Raises:
            TickerNotFoundError: If ticker is invalid
        """
        pass
    
    @abstractmethod
    def fetch_stock_info(self, ticker: str) -> StockInfo:
        """
        Fetch stock information (dividend, earnings, current price).
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            StockInfo object with available data
            
        Raises:
            TickerNotFoundError: If ticker is invalid
        """
        pass
    
    @abstractmethod
    def fetch_options_expirations(self, ticker: str) -> List[str]:
        """
        Fetch available options expiration dates.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            List of expiration dates in YYYY-MM-DD format, sorted ascending
            
        Raises:
            TickerNotFoundError: If ticker is invalid
            DataNotAvailableError: If options data is not available
        """
        pass
    
    @abstractmethod
    def fetch_options_chain(
        self, 
        ticker: str, 
        expiration: str
    ) -> OptionsChain:
        """
        Fetch options chain for a specific expiration.
        
        Args:
            ticker: Stock ticker symbol
            expiration: Expiration date in YYYY-MM-DD format
            
        Returns:
            OptionsChain object with calls and puts
            
        Raises:
            TickerNotFoundError: If ticker is invalid
            DataNotAvailableError: If options chain is not available for the expiration
        """
        pass
    
    def get_provider_name(self) -> str:
        """
        Return provider name for logging/debugging.
        
        Returns:
            Provider name string
        """
        return self.__class__.__name__
