"""yfinance implementation of StockDataProvider."""
import yfinance as yf
import pandas as pd
import warnings
import sys
from io import StringIO
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from decimal import Decimal

from app.providers.base import (
    StockDataProvider,
    StockPriceData,
    StockInfo,
    OptionQuote,
    OptionsChain,
)
from app.providers.exceptions import TickerNotFoundError, DataNotAvailableError

import logging

logger = logging.getLogger(__name__)


class YFinanceProvider(StockDataProvider):
    """yfinance implementation of StockDataProvider."""
    
    def _suppress_stderr(self):
        """Context manager to suppress yfinance stderr warnings."""
        class StderrSuppressor:
            def __init__(self):
                self.old_stderr = None
            
            def __enter__(self):
                self.old_stderr = sys.stderr
                sys.stderr = StringIO()
                return self
            
            def __exit__(self, exc_type, exc_val, exc_tb):
                sys.stderr = self.old_stderr
        
        return StderrSuppressor()
    
    def validate_ticker(self, ticker: str) -> bool:
        """Validate if a ticker exists and is valid."""
        try:
            with self._suppress_stderr():
                stock = yf.Ticker(ticker.upper())
                # Try to fetch basic info to validate ticker
                info = stock.info
                # If info is empty or has no symbol, ticker is invalid
                if not info or 'symbol' not in info:
                    return False
                return True
        except Exception as e:
            logger.debug(f"Ticker validation failed for {ticker}: {e}")
            return False
    
    def fetch_historical_prices(
        self, 
        ticker: str, 
        start_date: date, 
        end_date: date
    ) -> List[StockPriceData]:
        """Fetch historical daily OHLC data."""
        ticker_upper = ticker.upper()
        
        # First validate ticker exists
        if not self.validate_ticker(ticker_upper):
            raise TickerNotFoundError(f"Ticker {ticker_upper} not found or invalid")
        
        try:
            with self._suppress_stderr():
                stock = yf.Ticker(ticker_upper)
                start_datetime = datetime.combine(start_date, datetime.min.time())
                end_datetime = datetime.combine(end_date, datetime.min.time())
                
                hist = stock.history(start=start_datetime, end=end_datetime)
            
            if hist.empty:
                raise DataNotAvailableError(
                    f"No historical data available for {ticker_upper} from {start_date} to {end_date}"
                )
            
            # Normalize index to timezone-naive if needed
            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)
            
            # Convert to list of StockPriceData
            result = []
            for idx, row in hist.iterrows():
                # Convert index to date
                if isinstance(idx, pd.Timestamp):
                    price_date = idx.date()
                else:
                    price_date = pd.Timestamp(idx).date()
                
                result.append(StockPriceData(
                    date=price_date,
                    open=float(row['Open']),
                    high=float(row['High']),
                    low=float(row['Low']),
                    close=float(row['Close']),
                    volume=int(row['Volume']) if pd.notna(row['Volume']) else 0
                ))
            
            return result
            
        except DataNotAvailableError:
            raise
        except Exception as e:
            logger.error(f"Error fetching historical prices for {ticker_upper}: {e}")
            raise TickerNotFoundError(f"Failed to fetch data for ticker {ticker_upper}: {str(e)}")
    
    def fetch_intraday_prices(
        self, 
        ticker: str, 
        target_date: date
    ) -> Optional[List[StockPriceData]]:
        """Fetch intraday data for a specific date."""
        ticker_upper = ticker.upper()
        
        try:
            with self._suppress_stderr():
                stock = yf.Ticker(ticker_upper)
                # Fetch intraday data (1-minute intervals)
                intraday = stock.history(period='1d', interval='1m')
            
            if intraday.empty:
                return None
            
            # Normalize index to timezone-naive if needed
            if intraday.index.tz is not None:
                intraday.index = intraday.index.tz_localize(None)
            
            # Check if data is for target_date
            intraday_dates = set()
            for d in intraday.index:
                ts = pd.Timestamp(d)
                if ts.tz is not None:
                    ts = ts.tz_localize(None)
                intraday_dates.add(ts.date())
            
            if target_date not in intraday_dates:
                # Data is not for target_date (might be from previous day)
                return None
            
            # Filter to only target_date data
            filtered_data = []
            for idx, row in intraday.iterrows():
                ts = pd.Timestamp(idx)
                if ts.tz is not None:
                    ts = ts.tz_localize(None)
                if ts.date() == target_date:
                    filtered_data.append((ts, row))
            
            if not filtered_data:
                return None
            
            # Convert to list of StockPriceData (minute-by-minute)
            # Preserve timestamp for intraday data to maintain time components
            result = []
            for ts, row in filtered_data:
                result.append(StockPriceData(
                    date=target_date,  # All entries have same date
                    open=float(row['Open']),
                    high=float(row['High']),
                    low=float(row['Low']),
                    close=float(row['Close']),
                    volume=int(row['Volume']) if pd.notna(row['Volume']) else 0,
                    timestamp=ts  # Preserve timestamp for intraday data
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching intraday prices for {ticker_upper}: {e}")
            # Return None instead of raising - intraday data may not be available
            return None
    
    def fetch_stock_info(self, ticker: str) -> StockInfo:
        """Fetch stock information (dividend, earnings, current price)."""
        ticker_upper = ticker.upper()
        
        try:
            with self._suppress_stderr():
                stock = yf.Ticker(ticker_upper)
                info = stock.info
            
            if not info or 'symbol' not in info:
                raise TickerNotFoundError(f"Ticker {ticker_upper} not found")
            
            # Extract current price
            current_price = None
            if 'currentPrice' in info and info['currentPrice'] is not None:
                current_price = float(info['currentPrice'])
            elif 'regularMarketPrice' in info and info['regularMarketPrice'] is not None:
                current_price = float(info['regularMarketPrice'])
            
            # Extract dividend amount
            dividend_amount = None
            if 'dividendRate' in info and info['dividendRate'] is not None:
                dividend_amount = float(info['dividendRate'])
            
            # Extract dividend yield
            # yfinance returns dividendYield as a percentage (e.g., 2.43 means 2.43%)
            dividend_yield = None
            if 'dividendYield' in info and info['dividendYield'] is not None:
                dividend_yield = float(info['dividendYield'])
            elif dividend_amount is not None and current_price is not None and current_price > 0:
                # Calculate dividend yield from dividend amount and current price
                dividend_yield = (dividend_amount / current_price) * 100
            
            # Extract earnings date
            next_earnings_date = None
            is_earnings_date_estimate = None
            
            earnings_timestamp = info.get('earningsTimestamp')
            if earnings_timestamp is not None:
                try:
                    # Convert Unix timestamp to date
                    earnings_datetime = datetime.fromtimestamp(earnings_timestamp)
                    earnings_date = earnings_datetime.date()
                    
                    # Only use future earnings dates
                    today = date.today()
                    if earnings_date >= today:
                        next_earnings_date = earnings_date
                        is_earnings_date_estimate = info.get('isEarningsDateEstimate', False)
                except (ValueError, TypeError, OSError) as e:
                    logger.debug(f"Error parsing earnings timestamp for {ticker_upper}: {e}")
            
            # Extract ex-dividend date
            next_dividend_date = None
            ex_div_timestamp = info.get('exDividendDate')
            if ex_div_timestamp is not None:
                try:
                    # Convert Unix timestamp to date
                    ex_div_datetime = datetime.fromtimestamp(ex_div_timestamp)
                    next_dividend_date = ex_div_datetime.date()
                except (ValueError, TypeError, OSError) as e:
                    logger.debug(f"Error parsing exDividendDate for {ticker_upper}: {e}")
            
            return StockInfo(
                ticker=ticker_upper,
                current_price=current_price,
                dividend_amount=dividend_amount,
                dividend_yield=dividend_yield,
                next_earnings_date=next_earnings_date,
                is_earnings_date_estimate=is_earnings_date_estimate,
                next_dividend_date=next_dividend_date
            )
            
        except TickerNotFoundError:
            raise
        except Exception as e:
            logger.error(f"Error fetching stock info for {ticker_upper}: {e}")
            raise TickerNotFoundError(f"Failed to fetch info for ticker {ticker_upper}: {str(e)}")
    
    def fetch_options_expirations(self, ticker: str) -> List[str]:
        """Fetch available options expiration dates."""
        ticker_upper = ticker.upper()
        
        try:
            with self._suppress_stderr():
                stock = yf.Ticker(ticker_upper)
                expirations = stock.options
            
            if not expirations:
                raise DataNotAvailableError(f"No options data available for {ticker_upper}")
            
            # Return sorted list of expiration dates (already in YYYY-MM-DD format)
            return sorted(expirations)
            
        except DataNotAvailableError:
            raise
        except Exception as e:
            logger.error(f"Error fetching options expirations for {ticker_upper}: {e}")
            raise TickerNotFoundError(f"Failed to fetch options expirations for ticker {ticker_upper}: {str(e)}")
    
    def fetch_options_chain(
        self, 
        ticker: str, 
        expiration: str,
        request_params: Optional[Dict[str, Any]] = None
    ) -> OptionsChain:
        """Fetch options chain for a specific expiration."""
        ticker_upper = ticker.upper()
        
        try:
            with self._suppress_stderr():
                stock = yf.Ticker(ticker_upper)
                opt_chain = stock.option_chain(expiration)
            
            # Convert calls DataFrame to list of OptionQuote
            calls = []
            if opt_chain.calls is not None and not opt_chain.calls.empty:
                for _, row in opt_chain.calls.iterrows():
                    # yfinance returns IV as decimal (0.25 = 25%), convert to percentage
                    iv_raw = row.get('impliedVolatility')
                    iv = float(iv_raw) * 100 if pd.notna(iv_raw) else None
                    calls.append(OptionQuote(
                        contract_symbol=str(row.get('contractSymbol', '')),
                        strike=float(row.get('strike', 0)),
                        bid=float(row.get('bid')) if pd.notna(row.get('bid')) else None,
                        ask=float(row.get('ask')) if pd.notna(row.get('ask')) else None,
                        last_price=float(row.get('lastPrice')) if pd.notna(row.get('lastPrice')) else None,
                        volume=int(row.get('volume')) if pd.notna(row.get('volume')) else None,
                        open_interest=int(row.get('openInterest')) if pd.notna(row.get('openInterest')) else None,
                        implied_volatility=iv,
                        # yfinance doesn't provide Greeks - they will be None
                        delta=None,
                        gamma=None,
                        theta=None,
                        vega=None,
                        rho=None
                    ))
            
            # Convert puts DataFrame to list of OptionQuote
            puts = []
            if opt_chain.puts is not None and not opt_chain.puts.empty:
                for _, row in opt_chain.puts.iterrows():
                    # yfinance returns IV as decimal (0.25 = 25%), convert to percentage
                    iv_raw = row.get('impliedVolatility')
                    iv = float(iv_raw) * 100 if pd.notna(iv_raw) else None
                    puts.append(OptionQuote(
                        contract_symbol=str(row.get('contractSymbol', '')),
                        strike=float(row.get('strike', 0)),
                        bid=float(row.get('bid')) if pd.notna(row.get('bid')) else None,
                        ask=float(row.get('ask')) if pd.notna(row.get('ask')) else None,
                        last_price=float(row.get('lastPrice')) if pd.notna(row.get('lastPrice')) else None,
                        volume=int(row.get('volume')) if pd.notna(row.get('volume')) else None,
                        open_interest=int(row.get('openInterest')) if pd.notna(row.get('openInterest')) else None,
                        implied_volatility=iv,
                        # yfinance doesn't provide Greeks - they will be None
                        delta=None,
                        gamma=None,
                        theta=None,
                        vega=None,
                        rho=None
                    ))
            
            if not calls and not puts:
                raise DataNotAvailableError(
                    f"No options chain data available for {ticker_upper} expiration {expiration}"
                )
            
            return OptionsChain(
                expiration=expiration,
                calls=calls,
                puts=puts
            )
            
        except DataNotAvailableError:
            raise
        except Exception as e:
            logger.error(f"Error fetching options chain for {ticker_upper} {expiration}: {e}")
            raise DataNotAvailableError(
                f"Failed to fetch options chain for {ticker_upper} expiration {expiration}: {str(e)}"
            )

    def fetch_option_quote(self, option_symbol: str) -> Optional[OptionQuote]:
        """
        Fetch a single option quote by OCC symbol via a full chain lookup.

        yfinance does not support single-contract endpoints, so this fetches
        the entire options chain for the contract's expiration and returns the
        matching contract. Greeks will always be None (yfinance does not supply them).

        Args:
            option_symbol: OCC option symbol (e.g. 'NFLX281215P00105000')

        Returns:
            OptionQuote or None if no matching contract is found
        """
        from app.utils.option_symbol import parse_option_symbol

        try:
            parsed = parse_option_symbol(option_symbol)
        except ValueError as e:
            logger.error(f"Invalid option symbol '{option_symbol}': {e}")
            return None

        expiration_str = parsed["expiration"].strftime("%Y-%m-%d")
        option_type = parsed["option_type"]  # 'call' or 'put'

        try:
            chain = self.fetch_options_chain(parsed["ticker"], expiration_str)
        except Exception as e:
            logger.error(f"Could not fetch chain for {option_symbol}: {e}")
            return None

        contracts = chain.calls if option_type == "call" else chain.puts
        for quote in contracts:
            if quote.contract_symbol == option_symbol:
                return quote

        logger.warning(f"Contract '{option_symbol}' not found in yfinance chain for {expiration_str}")
        return None
