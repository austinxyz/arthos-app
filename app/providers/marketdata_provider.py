"""MarketData.app provider for options data with Greeks."""
import os
import requests
import logging
from typing import List, Optional, Dict, Any
from datetime import date, datetime, timedelta
from threading import Lock
from app.providers.base import (
    StockDataProvider, StockPriceData, StockInfo, 
    OptionQuote, OptionsChain
)
from app.providers.exceptions import TickerNotFoundError, DataNotAvailableError
from app.services.api_usage_tracker import record_api_call

logger = logging.getLogger(__name__)


class MarketDataProvider(StockDataProvider):
    """
    MarketData.app provider for options data with Greeks and IV.
    
    API usage limits are plan-dependent. This provider includes
    a daily circuit breaker when the upstream API returns 429.
    
    API Documentation: https://www.marketdata.app/docs/api
    """
    
    BASE_URL = "https://api.marketdata.app/v1"
    _rate_limited_utc_date: Optional[date] = None
    _rate_limit_lock = Lock()
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize MarketData provider.
        
        Args:
            api_key: MarketData API key. If not provided, uses MARKETDATA_API_KEY env var.
        """
        self.api_key = api_key or os.getenv('MARKETDATA_API_KEY')
        if not self.api_key:
            logger.warning("MarketData API key not configured. Set MARKETDATA_API_KEY environment variable.")
        
        self.headers = {
            "Accept": "application/json"
        }
        if self.api_key:
            self.headers["Authorization"] = f"Token {self.api_key}"

        # For paid plans, cached mode is significantly more credit-efficient
        # than live mode for options chains.
        self.options_chain_mode = os.getenv("MARKETDATA_OPTIONS_CHAIN_MODE", "cached").strip().lower()
        self.options_chain_maxage = os.getenv("MARKETDATA_OPTIONS_CHAIN_MAXAGE", "").strip()

    @classmethod
    def _is_rate_limited_today(cls) -> bool:
        """Check whether the MarketData rate limit was hit for the current UTC day."""
        today_utc = datetime.utcnow().date()
        with cls._rate_limit_lock:
            if cls._rate_limited_utc_date and cls._rate_limited_utc_date != today_utc:
                # Automatically reset circuit breaker on UTC day rollover.
                cls._rate_limited_utc_date = None
            return cls._rate_limited_utc_date == today_utc

    @classmethod
    def _mark_rate_limited_today(cls) -> None:
        """Mark current UTC day as rate-limited to short-circuit subsequent calls."""
        today_utc = datetime.utcnow().date()
        with cls._rate_limit_lock:
            if cls._rate_limited_utc_date != today_utc:
                cls._rate_limited_utc_date = today_utc
                logger.warning(
                    "MarketData API rate limit hit; enabling circuit breaker for UTC date %s",
                    today_utc.isoformat()
                )
    
    def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make an API request to MarketData.
        
        Args:
            endpoint: API endpoint path
            params: Query parameters
            
        Returns:
            JSON response as dict
            
        Raises:
            TickerNotFoundError: If ticker is not found
            DataNotAvailableError: If data is not available
        """
        url = f"{self.BASE_URL}{endpoint}"

        ticker = self._extract_ticker_from_endpoint(endpoint)

        if self._is_rate_limited_today():
            record_api_call("marketdata", endpoint, ticker=ticker, status="rate_limit_short_circuit")
            raise DataNotAvailableError("MarketData API rate limit exceeded (circuit breaker active for today)")
        
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=30)
            record_api_call("marketdata", endpoint, ticker=ticker, status=f"http_{response.status_code}")
            
            if response.status_code == 404:
                raise TickerNotFoundError(f"Ticker not found: {endpoint}")
            elif response.status_code == 401:
                raise DataNotAvailableError("MarketData API key invalid or missing")
            elif response.status_code == 429:
                self._mark_rate_limited_today()
                raise DataNotAvailableError("MarketData API rate limit exceeded")
            elif response.status_code not in (200, 203):
                raise DataNotAvailableError(f"MarketData API error: {response.status_code} - {response.text}")
            
            data = response.json()
            
            # Check for API-level errors
            if data.get('s') == 'error':
                error_msg = data.get('errmsg', 'Unknown error')
                if 'not found' in error_msg.lower() or 'no data' in error_msg.lower():
                    raise TickerNotFoundError(error_msg)
                raise DataNotAvailableError(error_msg)
            
            return data
            
        except requests.RequestException as e:
            record_api_call("marketdata", endpoint, ticker=ticker, status="request_exception")
            logger.error(f"MarketData API request failed: {e}")
            raise DataNotAvailableError(f"MarketData API request failed: {e}")

    @staticmethod
    def _extract_ticker_from_endpoint(endpoint: str) -> Optional[str]:
        """
        Best-effort ticker extraction from MarketData endpoint path.
        Expected endpoint patterns include:
        - /options/expirations/{ticker}/
        - /options/chain/{ticker}/
        - /stocks/quotes/{ticker}/
        - /stocks/candles/D/{ticker}/
        """
        try:
            parts = [p for p in endpoint.strip("/").split("/") if p]
            if not parts:
                return None

            # Most endpoints place ticker as the last segment.
            candidate = parts[-1].upper()
            if candidate not in {"D"} and candidate.isalnum():
                return candidate

            # Candles endpoint has interval segment before ticker.
            if len(parts) >= 4 and parts[0] == "stocks" and parts[1] == "candles":
                return parts[3].upper()
        except Exception:
            return None

        return None
    
    def validate_ticker(self, ticker: str) -> bool:
        """Validate if a ticker exists."""
        try:
            # Use stock quote endpoint to validate
            self._make_request(f"/stocks/quotes/{ticker.upper()}/")
            return True
        except (TickerNotFoundError, DataNotAvailableError):
            return False
    
    def fetch_historical_prices(
        self, 
        ticker: str, 
        start_date: date, 
        end_date: date
    ) -> List[StockPriceData]:
        """
        Fetch historical daily OHLC data.
        Note: MarketData is primarily for options. For stocks, yfinance may be better.
        """
        try:
            params = {
                "from": start_date.isoformat(),
                "to": end_date.isoformat()
            }
            data = self._make_request(f"/stocks/candles/D/{ticker.upper()}/", params)
            
            if data.get('s') != 'ok':
                raise DataNotAvailableError(f"No historical data for {ticker}")
            
            prices = []
            timestamps = data.get('t', [])
            opens = data.get('o', [])
            highs = data.get('h', [])
            lows = data.get('l', [])
            closes = data.get('c', [])
            volumes = data.get('v', [])
            
            for i, ts in enumerate(timestamps):
                price_date = datetime.fromtimestamp(ts).date()
                prices.append(StockPriceData(
                    date=price_date,
                    open=opens[i] if i < len(opens) else 0,
                    high=highs[i] if i < len(highs) else 0,
                    low=lows[i] if i < len(lows) else 0,
                    close=closes[i] if i < len(closes) else 0,
                    volume=int(volumes[i]) if i < len(volumes) else 0
                ))
            
            return sorted(prices, key=lambda x: x.date)
            
        except Exception as e:
            logger.error(f"Error fetching historical prices for {ticker}: {e}")
            raise
    
    def fetch_intraday_prices(
        self, 
        ticker: str, 
        target_date: date
    ) -> Optional[List[StockPriceData]]:
        """Fetch intraday data. Not implemented for MarketData - use yfinance."""
        return None
    
    def fetch_stock_info(self, ticker: str) -> StockInfo:
        """
        Fetch stock information.
        Note: MarketData is primarily for options. For fundamentals, yfinance may be better.
        """
        try:
            data = self._make_request(f"/stocks/quotes/{ticker.upper()}/")
            
            current_price = None
            if data.get('s') == 'ok' and data.get('last'):
                current_price = data['last'][0] if isinstance(data['last'], list) else data['last']
            
            return StockInfo(
                ticker=ticker.upper(),
                current_price=current_price,
                dividend_amount=None,
                dividend_yield=None,
                next_earnings_date=None,
                is_earnings_date_estimate=None,
                next_dividend_date=None
            )
        except Exception as e:
            logger.error(f"Error fetching stock info for {ticker}: {e}")
            raise TickerNotFoundError(f"Could not fetch stock info for {ticker}")
    
    def fetch_options_expirations(self, ticker: str) -> List[str]:
        """
        Fetch available options expiration dates.
        
        Args:
            ticker: Stock ticker symbol
            
        Returns:
            List of expiration dates in YYYY-MM-DD format
        """
        try:
            data = self._make_request(f"/options/expirations/{ticker.upper()}/")
            
            if data.get('s') != 'ok':
                raise DataNotAvailableError(f"No options expirations for {ticker}")
            
            expirations = data.get('expirations', [])
            
            # Convert to YYYY-MM-DD format if needed
            result = []
            for exp in expirations:
                if isinstance(exp, str):
                    # Already in string format
                    result.append(exp)
                elif isinstance(exp, (int, float)):
                    # Unix timestamp
                    result.append(datetime.fromtimestamp(exp).strftime('%Y-%m-%d'))
            
            return sorted(result)
            
        except (TickerNotFoundError, DataNotAvailableError):
            raise
        except Exception as e:
            logger.error(f"Error fetching options expirations for {ticker}: {e}")
            raise
    
    def fetch_options_chain(
        self, 
        ticker: str, 
        expiration: str,
        request_params: Optional[Dict[str, Any]] = None
    ) -> OptionsChain:
        """
        Fetch options chain with Greeks for a specific expiration.
        
        Args:
            ticker: Stock ticker symbol
            expiration: Expiration date in YYYY-MM-DD format
            
        Returns:
            OptionsChain with calls and puts including Greeks
        """
        try:
            params: Dict[str, Any] = {
                "expiration": expiration,
                "side": "both"  # Get both calls and puts
            }

            if self.options_chain_mode:
                params["mode"] = self.options_chain_mode
                if self.options_chain_mode == "cached" and self.options_chain_maxage:
                    params["maxage"] = self.options_chain_maxage

            # Callers can override defaults (e.g., strike filters).
            if request_params:
                params.update({k: v for k, v in request_params.items() if v is not None})

            data = self._make_request(f"/options/chain/{ticker.upper()}/", params)
            
            if data.get('s') != 'ok':
                raise DataNotAvailableError(f"No options chain for {ticker} expiring {expiration}")
            
            calls = []
            puts = []
            
            # Parse the response - MarketData returns arrays for each field
            option_symbols = data.get('optionSymbol', [])
            strikes = data.get('strike', [])
            sides = data.get('side', [])
            bids = data.get('bid', [])
            asks = data.get('ask', [])
            lasts = data.get('last', [])
            volumes = data.get('volume', [])
            open_interests = data.get('openInterest', [])
            ivs = data.get('iv', [])
            deltas = data.get('delta', [])
            gammas = data.get('gamma', [])
            thetas = data.get('theta', [])
            vegas = data.get('vega', [])
            rhos = data.get('rho', [])
            
            for i in range(len(option_symbols)):
                quote = OptionQuote(
                    contract_symbol=option_symbols[i] if i < len(option_symbols) else "",
                    strike=strikes[i] if i < len(strikes) else 0,
                    bid=bids[i] if i < len(bids) and bids[i] is not None else None,
                    ask=asks[i] if i < len(asks) and asks[i] is not None else None,
                    last_price=lasts[i] if i < len(lasts) and lasts[i] is not None else None,
                    volume=int(volumes[i]) if i < len(volumes) and volumes[i] is not None else None,
                    open_interest=int(open_interests[i]) if i < len(open_interests) and open_interests[i] is not None else None,
                    implied_volatility=ivs[i] * 100 if i < len(ivs) and ivs[i] is not None else None,  # Convert to percentage
                    delta=deltas[i] if i < len(deltas) and deltas[i] is not None else None,
                    gamma=gammas[i] if i < len(gammas) and gammas[i] is not None else None,
                    theta=thetas[i] if i < len(thetas) and thetas[i] is not None else None,
                    vega=vegas[i] if i < len(vegas) and vegas[i] is not None else None,
                    rho=rhos[i] if i < len(rhos) and rhos[i] is not None else None
                )
                
                side = sides[i] if i < len(sides) else ""
                if side.lower() == 'call':
                    calls.append(quote)
                elif side.lower() == 'put':
                    puts.append(quote)
            
            # Sort by strike
            calls.sort(key=lambda x: x.strike)
            puts.sort(key=lambda x: x.strike)
            
            return OptionsChain(
                expiration=expiration,
                calls=calls,
                puts=puts
            )
            
        except (TickerNotFoundError, DataNotAvailableError):
            raise
        except Exception as e:
            logger.error(f"Error fetching options chain for {ticker}: {e}")
            raise
    
    def fetch_option_quote(self, option_symbol: str) -> Optional[OptionQuote]:
        """
        Fetch a single option quote with Greeks.
        
        Args:
            option_symbol: OCC option symbol (e.g., 'AAPL250117C00150000')
            
        Returns:
            OptionQuote with Greeks or None if not found
        """
        try:
            data = self._make_request(f"/options/quotes/{option_symbol}/")
            
            if data.get('s') != 'ok':
                return None
            
            return OptionQuote(
                contract_symbol=data.get('optionSymbol', [option_symbol])[0],
                strike=data.get('strike', [0])[0],
                bid=data.get('bid', [None])[0],
                ask=data.get('ask', [None])[0],
                last_price=data.get('last', [None])[0],
                volume=int(data.get('volume', [0])[0]) if data.get('volume') else None,
                open_interest=int(data.get('openInterest', [0])[0]) if data.get('openInterest') else None,
                implied_volatility=data.get('iv', [None])[0] * 100 if data.get('iv', [None])[0] else None,
                delta=data.get('delta', [None])[0],
                gamma=data.get('gamma', [None])[0],
                theta=data.get('theta', [None])[0],
                vega=data.get('vega', [None])[0],
                rho=data.get('rho', [None])[0]
            )
            
        except Exception as e:
            logger.error(f"Error fetching option quote for {option_symbol}: {e}")
            return None
    
    def get_provider_name(self) -> str:
        """Return provider name."""
        return "MarketData.app"
