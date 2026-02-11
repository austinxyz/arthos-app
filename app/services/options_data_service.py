"""Options data fetching and processing service."""
from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime, timedelta
import logging
from app.providers.factory import ProviderFactory
from app.services.options_cache_service import get_cached_options_data, cache_options_data

logger = logging.getLogger(__name__)


def build_option_dict(option) -> Dict[str, Any]:
    """
    Build a standardized dictionary from an OptionQuote object.

    Args:
        option: OptionQuote object with strike, bid, ask, etc.

    Returns:
        Dictionary with option data formatted for API response
    """
    return {
        'contractSymbol': option.contract_symbol,
        'lastPrice': round(option.last_price, 2) if option.last_price is not None else None,
        'bid': round(option.bid, 2) if option.bid is not None else None,
        'ask': round(option.ask, 2) if option.ask is not None else None,
        'volume': option.volume if option.volume is not None else 0,
        'openInterest': option.open_interest if option.open_interest is not None else 0,
        'impliedVolatility': round(option.implied_volatility, 2) if option.implied_volatility is not None else None,
        'delta': round(option.delta, 4) if option.delta is not None else None,
        'gamma': round(option.gamma, 5) if option.gamma is not None else None,
        'theta': round(option.theta, 4) if option.theta is not None else None,
        'vega': round(option.vega, 4) if option.vega is not None else None,
        'rho': round(option.rho, 4) if option.rho is not None else None,
    }


def process_options_chain(opt_chain, price_range_low: float, price_range_high: float) -> Dict[float, Dict[str, Any]]:
    """
    Process an options chain into a dictionary organized by strike price.

    Args:
        opt_chain: OptionsChain object with calls and puts
        price_range_low: Minimum strike price to include
        price_range_high: Maximum strike price to include

    Returns:
        Dictionary mapping strike prices to {'put': dict, 'call': dict}
    """
    options_by_strike = {}

    # Process calls
    for call in opt_chain.calls:
        if price_range_low <= call.strike <= price_range_high:
            strike = round(call.strike, 2)
            if strike not in options_by_strike:
                options_by_strike[strike] = {'put': None, 'call': None}
            options_by_strike[strike]['call'] = build_option_dict(call)

    # Process puts
    for put in opt_chain.puts:
        if price_range_low <= put.strike <= price_range_high:
            strike = round(put.strike, 2)
            if strike not in options_by_strike:
                options_by_strike[strike] = {'put': None, 'call': None}
            options_by_strike[strike]['put'] = build_option_dict(put)

    return options_by_strike
def get_options_data(ticker: str, current_price: float) -> Tuple[Optional[str], Dict[float, Dict[str, Any]]]:
    """
    Fetch options data for a stock with expiration within 90 days and strikes within 10% of current price.
    Returns data organized by strike price for straddle display.
    
    Uses the options provider (MarketData.app if configured) to get Greeks with the data.
    Implements caching to reduce API calls (free tier has 100 calls/day limit).
    
    Args:
        ticker: Stock ticker symbol
        current_price: Current stock price
        
    Returns:
        Tuple of (expiration_date, options_by_strike)
        - expiration_date: The last expiration date within 90 days (or None)
        - options_by_strike: Dictionary mapping strike prices to dict with 'put' and 'call' data
    """
    from app.services.options_cache_service import (
        get_cached_options_data, cache_options_data, 
        calculate_atm_iv, update_stock_iv_metrics
    )
    
    try:
        # Use options provider for Greeks support (MarketData if configured, else yfinance)
        # Fallback to default provider if get_options_provider doesn't exist (for backwards compatibility)
        if hasattr(ProviderFactory, 'get_options_provider'):
            provider = ProviderFactory.get_options_provider()
        else:
            provider = ProviderFactory.get_default_provider()
        
        # Track if we need to fallback to yfinance due to rate limits
        use_fallback = False
        
        # Get all available expiration dates
        try:
            expirations = provider.fetch_options_expirations(ticker)
        except DataNotAvailableError as e:
            # Check if this is a rate limit error
            if "rate limit" in str(e).lower():
                logger.warning(f"MarketData rate limit hit for {ticker}, falling back to yfinance")
                use_fallback = True
                # Retry with yfinance
                from app.providers.yfinance_provider import YFinanceProvider
                provider = YFinanceProvider()
                try:
                    expirations = provider.fetch_options_expirations(ticker)
                except DataNotAvailableError:
                    return (None, {})
            else:
                return (None, {})
        
        if not expirations:
            return (None, {})
        
        # Find the last expiration date within 90 days
        now = datetime.now()
        max_date = now + timedelta(days=90)
        last_expiration = None
        
        for exp_str in expirations:
            try:
                exp_date = datetime.strptime(exp_str, '%Y-%m-%d')
                # Must be in the future and within 90 days
                if now < exp_date <= max_date:
                    if last_expiration is None or exp_date > datetime.strptime(last_expiration, '%Y-%m-%d'):
                        last_expiration = exp_str
            except ValueError:
                continue
        
        if not last_expiration:
            return (None, {})
        
        # Check cache first
        cached = get_cached_options_data(ticker, last_expiration)
        if cached:
            expiration, options_data = cached
            # Still update IV metrics from cached data
            atm_iv = calculate_atm_iv(options_data, current_price)
            if atm_iv is not None:
                update_stock_iv_metrics(ticker, atm_iv)
            return (expiration, options_data)
        
        # Get options chain for the last expiration within 90 days
        try:
            opt_chain = provider.fetch_options_chain(ticker, last_expiration)
        except DataNotAvailableError as e:
            # Check if this is a rate limit error and we haven't already fallen back
            if "rate limit" in str(e).lower() and not use_fallback:
                logger.warning(f"MarketData rate limit hit for {ticker} options chain, falling back to yfinance")
                use_fallback = True
                # Retry with yfinance
                from app.providers.yfinance_provider import YFinanceProvider
                provider = YFinanceProvider()
                try:
                    opt_chain = provider.fetch_options_chain(ticker, last_expiration)
                except DataNotAvailableError:
                    return (None, {})
            else:
                return (None, {})
        
        # Filter strikes within 10% of current price and process options
        price_range_low = current_price * 0.9  # 10% below
        price_range_high = current_price * 1.1  # 10% above

        options_by_strike = process_options_chain(opt_chain, price_range_low, price_range_high)

        # Cache the options data
        cache_options_data(ticker, last_expiration, options_by_strike)
        
        # Calculate and update ATM IV metrics
        atm_iv = calculate_atm_iv(options_by_strike, current_price)
        if atm_iv is not None:
            update_stock_iv_metrics(ticker, atm_iv)
        
        return (last_expiration, options_by_strike)
        
    except Exception as e:
        # If options data cannot be fetched, return empty
        import traceback
        logger.error(f"Error fetching options data for {ticker}: {str(e)}")
        traceback.print_exc()
        return (None, {})


def get_all_options_data(ticker: str, current_price: float, days_limit: int = 90) -> List[Tuple[str, Dict[float, Dict[str, Any]]]]:
    """
    Fetch options data for all expirations within the specified days limit.
    Returns data organized by expiration date and strike price.

    Args:
        ticker: Stock ticker symbol
        current_price: Current stock price
        days_limit: Maximum days from now to include expirations (default 90)

    Returns:
        List of tuples (expiration_date_str, options_by_strike)
    """
    from app.services.options_cache_service import get_cached_options_data, cache_options_data

    result = []

    try:
        # Use options provider for data
        if hasattr(ProviderFactory, 'get_options_provider'):
            provider = ProviderFactory.get_options_provider()
        else:
            provider = ProviderFactory.get_default_provider()

        use_fallback = False

        # Get all available expiration dates
        try:
            expirations = provider.fetch_options_expirations(ticker)
        except DataNotAvailableError as e:
            if "rate limit" in str(e).lower():
                logger.warning(f"MarketData rate limit hit for {ticker}, falling back to yfinance")
                use_fallback = True
                from app.providers.yfinance_provider import YFinanceProvider
                provider = YFinanceProvider()
                try:
                    expirations = provider.fetch_options_expirations(ticker)
                except DataNotAvailableError:
                    return []
            else:
                return []

        if not expirations:
            return []

        # Filter expirations within days_limit
        now = datetime.now()
        max_date = now + timedelta(days=days_limit)
        valid_expirations = []

        for exp_str in expirations:
            try:
                exp_date = datetime.strptime(exp_str, '%Y-%m-%d')
                if now < exp_date <= max_date:
                    valid_expirations.append(exp_str)
            except ValueError:
                continue

        if not valid_expirations:
            return []

        # Strikes within 30% of current price (as per spec)
        price_range_low = current_price * 0.7  # 30% below
        price_range_high = current_price * 1.3  # 30% above

        # Fetch options for each expiration
        for expiration in valid_expirations:
            # Check cache first
            cached = get_cached_options_data(ticker, expiration)
            if cached:
                _, options_data = cached
                result.append((expiration, options_data))
                continue

            # Fetch from provider
            try:
                opt_chain = provider.fetch_options_chain(ticker, expiration)
            except DataNotAvailableError as e:
                if "rate limit" in str(e).lower() and not use_fallback:
                    logger.warning(f"MarketData rate limit hit for {ticker} options chain, falling back to yfinance")
                    use_fallback = True
                    from app.providers.yfinance_provider import YFinanceProvider
                    provider = YFinanceProvider()
                    try:
                        opt_chain = provider.fetch_options_chain(ticker, expiration)
                    except DataNotAvailableError:
                        continue
                else:
                    continue

            options_by_strike = process_options_chain(opt_chain, price_range_low, price_range_high)

            # Cache the options data
            cache_options_data(ticker, expiration, options_by_strike)

            result.append((expiration, options_by_strike))

    except Exception as e:
        logger.error(f"Error fetching all options data for {ticker}: {str(e)}")
        import traceback
        traceback.print_exc()

    return result
def get_leaps_expirations(ticker: str) -> List[str]:
    """
    Get LEAPS expiration dates (Jan of next year or later).
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        List of expiration date strings (YYYY-MM-DD format) for LEAPS
    """
    try:
        # Use options provider (MarketData if available, else yfinance)
        if hasattr(ProviderFactory, 'get_options_provider'):
            provider = ProviderFactory.get_options_provider()
        else:
            provider = ProviderFactory.get_default_provider()
            
        try:
            expirations = provider.fetch_options_expirations(ticker)
        except DataNotAvailableError as e:
            # Check if this is a rate limit error
            if "rate limit" in str(e).lower():
                logger.warning(f"MarketData rate limit hit for {ticker} LEAPS, falling back to yfinance")
                # Retry with yfinance
                from app.providers.yfinance_provider import YFinanceProvider
                provider = YFinanceProvider()
                try:
                    expirations = provider.fetch_options_expirations(ticker)
                except DataNotAvailableError:
                    return []
            else:
                return []
        
        if not expirations:
            return []
        
        now = datetime.now()
        next_year = now.year + 1
        leaps = []
        
        for exp_str in expirations:
            try:
                exp_date = datetime.strptime(exp_str, '%Y-%m-%d')
                # Include Jan of next year or any date in future years
                # For next year: include January or later months
                # For years beyond next year: include all months
                if exp_date.year >= next_year:
                    if exp_date.year == next_year:
                        # For next year, include January or later
                        if exp_date.month >= 1:
                            leaps.append(exp_str)
                    else:
                        # For years beyond next year, include all months
                        leaps.append(exp_str)
            except ValueError:
