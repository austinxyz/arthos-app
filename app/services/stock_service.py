"""Stock data fetching and metric calculation service."""
import pandas as pd
from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime, timedelta, date
import logging
from app.providers.factory import ProviderFactory
from app.providers.converters import stock_price_data_to_dataframe, aggregate_intraday_to_daily
from app.providers.exceptions import TickerNotFoundError, DataNotAvailableError

logger = logging.getLogger(__name__)


def fetch_intraday_data(ticker: str) -> Optional[pd.DataFrame]:
    """
    Fetch current day's intraday data for a given ticker.
    
    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
        
    Returns:
        DataFrame with intraday data for today, or None if not available
    """
    try:
        provider = ProviderFactory.get_default_provider()
        today = datetime.now().date()
        
        # Fetch intraday data for today
        intraday_data = provider.fetch_intraday_prices(ticker, today)
        
        if intraday_data is None or len(intraday_data) == 0:
            return None
        
        # Convert to DataFrame, preserving time components for intraday data
        return stock_price_data_to_dataframe(intraday_data, preserve_time=True)
    except Exception as e:
        # If intraday data fails, return None (not critical)
        logger.debug(f"Error fetching intraday data for {ticker}: {e}")
        return None


def fetch_stock_data(ticker: str) -> pd.DataFrame:
    """
    Fetch past 2 years of stock data for a given ticker, including current day's intraday data if available.
    
    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
        
    Returns:
        DataFrame with stock data including 'Close' prices
        If intraday data is available for today, it will be appended to the historical daily data
        
    Raises:
        ValueError: If ticker is invalid or data cannot be fetched
    """
    try:
        provider = ProviderFactory.get_default_provider()
        # Fetch past 2 years of data to enable proper SMA calculations
        end_date = date.today()
        start_date = end_date - timedelta(days=730)  # 2 years
        
        hist_data = provider.fetch_historical_prices(ticker, start_date, end_date)
        
        if not hist_data:
            raise ValueError(f"No data found for ticker: {ticker}")
        
        # Convert to DataFrame
        hist = stock_price_data_to_dataframe(hist_data)
        
        # Try to fetch intraday data for today
        intraday_today = fetch_intraday_data(ticker)
        
        if intraday_today is not None and not intraday_today.empty:
            # Get today's date
            today = date.today()
            
            # Remove today's daily data from historical data if it exists
            # (since we'll use intraday data instead for more accuracy)
            hist_dates = [pd.Timestamp(idx).date() if isinstance(idx, pd.Timestamp) else idx.date() for idx in hist.index]
            today_mask = [d == today for d in hist_dates]
            
            if any(today_mask):
                # Remove today's daily data
                hist = hist[~pd.Series(today_mask, index=hist.index)]
            
            # Combine historical daily data with today's intraday data
            # Intraday data will have more granular timestamps
            combined = pd.concat([hist, intraday_today])
            combined = combined.sort_index()
            
            return combined
        
        return hist
    except Exception as e:
        raise ValueError(f"Error fetching data for {ticker}: {str(e)}")


def calculate_sma(data: pd.DataFrame, window: int) -> float:
    """
    Calculate Simple Moving Average (SMA) for the given window.
    
    Uses only daily data points (excludes intraday data points) but includes
    today's close price if intraday data is available. This ensures consistency
    with chart calculations which include today's aggregated candle.
    
    Args:
        data: DataFrame with 'Close' prices (may include intraday data)
        window: Number of days for the moving average
        
    Returns:
        SMA value calculated from daily data, including today's close if available
    """
    from datetime import datetime
    
    # Separate daily data from intraday data
    today = datetime.now().date()
    daily_mask = []
    intraday_today = []
    
    for ts in data.index:
        ts_obj = pd.Timestamp(ts)
        # Normalize to timezone-naive if needed
        if ts_obj.tz is not None:
            ts_obj = ts_obj.tz_localize(None)
        # Check if it's a daily timestamp (at midnight) or before today
        if ts_obj.hour == 0 and ts_obj.minute == 0:
            daily_mask.append(True)
            intraday_today.append(False)
        elif ts_obj.date() < today:
            daily_mask.append(True)
            intraday_today.append(False)
        else:
            # Has time component and is today - this is intraday data
            daily_mask.append(False)
            intraday_today.append(True)
    
    # Get daily data (excluding today's daily data if it exists)
    daily_data = data[daily_mask] if any(daily_mask) else pd.DataFrame()
    
    # Get today's intraday data if available
    intraday_data = data[intraday_today] if any(intraday_today) else pd.DataFrame()
    
    # If we have intraday data for today, aggregate it into a daily candle
    # and add it to daily_data for SMA calculation
    if not intraday_data.empty:
        today_close = intraday_data['Close'].iloc[-1]  # Use last close price from intraday
        
        # Remove today's daily data if it exists (we'll use aggregated intraday instead)
        if not daily_data.empty:
            today_daily_mask = [pd.Timestamp(ts).date() == today for ts in daily_data.index]
            if any(today_daily_mask):
                daily_data = daily_data[~pd.Series(today_daily_mask, index=daily_data.index)]
        
        # Create today's aggregated candle
        today_timestamp = pd.Timestamp(today).replace(hour=0, minute=0, second=0, microsecond=0)
        # Ensure timezone-naive
        if today_timestamp.tz is not None:
            today_timestamp = today_timestamp.tz_localize(None)
        
        today_candle = pd.DataFrame([{
            'Close': today_close
        }], index=[today_timestamp])
        
        # Normalize daily_data index to timezone-naive before concatenating
        if not daily_data.empty:
            daily_data = daily_data.copy()
            normalized_index = []
            for ts in daily_data.index:
                ts_obj = pd.Timestamp(ts)
                if ts_obj.tz is not None:
                    normalized_index.append(ts_obj.tz_localize(None))
                else:
                    normalized_index.append(ts_obj)
            daily_data.index = pd.DatetimeIndex(normalized_index)
        
        # Add today's candle to daily data
        if not daily_data.empty:
            daily_data = pd.concat([daily_data, today_candle])
        else:
            daily_data = today_candle
        
        # Sort by date (all timestamps are now timezone-naive)
        daily_data = daily_data.sort_index()
    
    # If no daily data at all, use original data
    if daily_data.empty:
        daily_data = data
    
    if len(daily_data) < window:
        # If not enough data, use available data
        window = len(daily_data)
    
    if window == 0:
        return 0.0
    
    # Calculate SMA using the last 'window' daily data points (now including today if available)
    return daily_data['Close'].tail(window).mean()


def calculate_devstep(data: pd.DataFrame, sma_50: float) -> float:
    """
    Calculate the number of standard deviations the current price is from the 50-day SMA.
    
    Uses only daily data points for std_dev calculation to avoid skewing from intraday data.
    Uses the latest price (intraday if available) for current_price.
    
    Args:
        data: DataFrame with 'Close' prices (may include intraday data)
        sma_50: 50-day Simple Moving Average
    
    Returns:
        Number of standard deviations (devstep)
    """
    from datetime import datetime
    
    # Get current price (use latest, which could be intraday)
    current_price = data['Close'].iloc[-1]
    
    # Separate daily data from intraday data for std_dev calculation
    today = datetime.now().date()
    daily_mask = []
    
    for ts in data.index:
        ts_obj = pd.Timestamp(ts)
        # Normalize to timezone-naive if needed
        if ts_obj.tz is not None:
            ts_obj = ts_obj.tz_localize(None)
        # Check if it's a daily timestamp (at midnight) or before today
        if ts_obj.hour == 0 and ts_obj.minute == 0:
            daily_mask.append(True)
        elif ts_obj.date() < today:
            daily_mask.append(True)
        else:
            # Has time component and is today - this is intraday data
            daily_mask.append(False)
    
    daily_data = data[daily_mask] if any(daily_mask) else data
    
    # Calculate std_dev using only daily data points
    if len(daily_data) < 50:
        window = len(daily_data)
    else:
        window = 50
    
    if window == 0:
        return 0.0
    
    recent_daily_prices = daily_data['Close'].tail(window)
    std_dev = recent_daily_prices.std()
    
    if std_dev == 0:
        return 0.0
    
    devstep = (current_price - sma_50) / std_dev
    return devstep


def calculate_5day_price_movement(data: pd.DataFrame, sma_50: float) -> Tuple[float, bool]:
    """
    Calculate the 5-day price movement in terms of standard deviations.
    
    Uses only daily data points to find the price 5 trading days ago (not 5 data points ago).
    Uses the latest price (intraday if available) for current_price.
    Uses only daily data points for std_dev calculation.
    
    Args:
        data: DataFrame with 'Close' prices (may include intraday data)
        sma_50: 50-day Simple Moving Average
    
    Returns:
        Tuple of (movement_in_stddev, is_positive)
        - movement_in_stddev: Price movement over 5 trading days in standard deviations
        - is_positive: True if price moved up, False if price moved down
    """
    from datetime import datetime
    
    # Get current price (use latest, which could be intraday)
    current_price = data['Close'].iloc[-1]
    
    # Separate daily data from intraday data
    today = datetime.now().date()
    daily_mask = []
    
    for ts in data.index:
        ts_obj = pd.Timestamp(ts)
        # Normalize to timezone-naive if needed
        if ts_obj.tz is not None:
            ts_obj = ts_obj.tz_localize(None)
        # Check if it's a daily timestamp (at midnight) or before today
        if ts_obj.hour == 0 and ts_obj.minute == 0:
            daily_mask.append(True)
        elif ts_obj.date() < today:
            daily_mask.append(True)
        else:
            # Has time component and is today - this is intraday data
            daily_mask.append(False)
    
    daily_data = data[daily_mask] if any(daily_mask) else data
    
    # Need at least 6 daily data points (5 days ago + current day)
    if len(daily_data) < 6:
        return (0.0, True)
    
    # Get price from 5 trading days ago (using daily data only)
    # If we have intraday data for today, we want the price from 5 daily candles ago
    # If we don't have intraday data, we want the price from 6 daily candles ago (5 days before today)
    if any(not mask for mask in daily_mask):  # We have intraday data
        # Use the last 5 daily candles (excluding today's intraday)
        price_5days_ago = daily_data['Close'].iloc[-5]
    else:
        # No intraday data, use 6 days ago (5 trading days before today)
        price_5days_ago = daily_data['Close'].iloc[-6]
    
    # Calculate price change
    price_change = current_price - price_5days_ago
    
    # Calculate standard deviation for conversion using only daily data
    if len(daily_data) < 50:
        window = len(daily_data)
    else:
        window = 50
    
    if window == 0:
        return (0.0, True)
    
    recent_daily_prices = daily_data['Close'].tail(window)
    std_dev = recent_daily_prices.std()
    
    if std_dev == 0:
        return (0.0, True)
    
    # Convert price change to standard deviations
    movement_in_stddev = float(price_change / std_dev)
    
    # Ensure Python bool (not numpy bool) for JSON serialization
    is_positive = bool(price_change >= 0)
    
    return (movement_in_stddev, is_positive)


def calculate_signal(devstep: float) -> str:
    """
    Calculate trading signal based on devstep value.
    
    Args:
        devstep: Number of standard deviations from 50-day SMA
        
    Returns:
        Signal string: 'Neutral', 'Overbought', 'Extreme Overbought', 
                       'Oversold', or 'Extreme Oversold'
    """
    if devstep < -2:
        return "Extreme Oversold"
    elif devstep < -1:
        return "Oversold"
    elif devstep <= 1:
        return "Neutral"
    elif devstep <= 2:
        return "Overbought"
    else:
        return "Extreme Overbought"


def get_multiple_stock_metrics(tickers: list) -> list:
    """
    Fetch stock metrics for multiple tickers from database.
    
    Args:
        tickers: List of stock ticker symbols
        
    Returns:
        List of dictionaries containing metrics for each ticker.
        Failed tickers will have an 'error' field instead of metrics.
    """
    from app.services.stock_price_service import get_stock_metrics_from_db
    
    results = []
    for ticker in tickers:
        ticker = ticker.strip().upper()
        if not ticker:
            continue
        
        try:
            metrics = get_stock_metrics_from_db(ticker)
            results.append(metrics)
        except Exception as e:
            # Add error entry for failed ticker
            results.append({
                "ticker": ticker,
                "error": str(e)
            })
    
    return results


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
        
        # Get all available expiration dates
        try:
            expirations = provider.fetch_options_expirations(ticker)
        except DataNotAvailableError:
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
        except DataNotAvailableError:
            return (None, {})
        
        # Filter strikes within 10% of current price
        price_range_low = current_price * 0.9  # 10% below
        price_range_high = current_price * 1.1  # 10% above
        
        options_by_strike = {}
        
        # Process calls
        for call in opt_chain.calls:
            if price_range_low <= call.strike <= price_range_high:
                strike = round(call.strike, 2)
                if strike not in options_by_strike:
                    options_by_strike[strike] = {'put': None, 'call': None}
                options_by_strike[strike]['call'] = {
                    'contractSymbol': call.contract_symbol,
                    'lastPrice': round(call.last_price, 2) if call.last_price is not None else None,
                    'bid': round(call.bid, 2) if call.bid is not None else None,
                    'ask': round(call.ask, 2) if call.ask is not None else None,
                    'volume': call.volume if call.volume is not None else 0,
                    'openInterest': call.open_interest if call.open_interest is not None else 0,
                    'impliedVolatility': round(call.implied_volatility, 2) if call.implied_volatility is not None else None,
                    # Greeks from MarketData or other provider
                    'delta': round(call.delta, 4) if call.delta is not None else None,
                    'gamma': round(call.gamma, 5) if call.gamma is not None else None,
                    'theta': round(call.theta, 4) if call.theta is not None else None,
                    'vega': round(call.vega, 4) if call.vega is not None else None,
                    'rho': round(call.rho, 4) if call.rho is not None else None,
                }
        
        # Process puts
        for put in opt_chain.puts:
            if price_range_low <= put.strike <= price_range_high:
                strike = round(put.strike, 2)
                if strike not in options_by_strike:
                    options_by_strike[strike] = {'put': None, 'call': None}
                options_by_strike[strike]['put'] = {
                    'contractSymbol': put.contract_symbol,
                    'lastPrice': round(put.last_price, 2) if put.last_price is not None else None,
                    'bid': round(put.bid, 2) if put.bid is not None else None,
                    'ask': round(put.ask, 2) if put.ask is not None else None,
                    'volume': put.volume if put.volume is not None else 0,
                    'openInterest': put.open_interest if put.open_interest is not None else 0,
                    'impliedVolatility': round(put.implied_volatility, 2) if put.implied_volatility is not None else None,
                    # Greeks from MarketData or other provider
                    'delta': round(put.delta, 4) if put.delta is not None else None,
                    'gamma': round(put.gamma, 5) if put.gamma is not None else None,
                    'theta': round(put.theta, 4) if put.theta is not None else None,
                    'vega': round(put.vega, 4) if put.vega is not None else None,
                    'rho': round(put.rho, 4) if put.rho is not None else None,
                }
        
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


def calculate_covered_call_returns(options_data: Dict[float, Dict[str, Any]], current_price: float) -> List[Dict[str, Any]]:
    """
    Calculate covered call strategy returns for each strike price.
    
    Args:
        options_data: Dictionary mapping strike prices to put/call data
        current_price: Current stock price (used as purchase price)
        
    Returns:
        List of dictionaries containing covered call return calculations for each strike
    """
    covered_calls = []
    
    # Handle empty or None options_data
    if not options_data or not isinstance(options_data, dict):
        return covered_calls
    
    # Ensure current_price is valid
    if current_price is None or current_price <= 0:
        return covered_calls
    
    try:
        for strike in sorted(options_data.keys()):
            strike_data = options_data.get(strike)
            if not strike_data or not isinstance(strike_data, dict):
                continue
            
            # Only process strikes that have call options
            if strike_data.get('call') is None:
                continue
            
            call_data = strike_data['call']
            if not isinstance(call_data, dict):
                continue
            
            # Calculate call premium: max(Last Price, (Bid + Ask) / 2)
            last_price = call_data.get('lastPrice')
            if last_price is None or pd.isna(last_price):
                last_price = 0
            else:
                last_price = float(last_price)
            
            bid = call_data.get('bid')
            if bid is None or pd.isna(bid):
                bid = 0
            else:
                bid = float(bid)
            
            ask = call_data.get('ask')
            if ask is None or pd.isna(ask):
                ask = 0
            else:
                ask = float(ask)
            
            avg_bid_ask = (bid + ask) / 2 if (bid > 0 and ask > 0) else 0
            
            # Calculate call premium: max(Last Price, (Bid + Ask) / 2)
            if last_price > 0 and avg_bid_ask > 0:
                call_premium = max(last_price, avg_bid_ask)
            elif last_price > 0:
                call_premium = last_price
            elif avg_bid_ask > 0:
                call_premium = avg_bid_ask
            else:
                call_premium = 0
            
            if call_premium == 0:
                continue  # Skip if no valid premium
            
            # Calculate returns for exercised scenario
            # Total Return = Strike Price + Call Premium - Stock Purchase Price
            total_return_exercised = strike + call_premium - current_price
            total_return_pct_exercised = (total_return_exercised / current_price) * 100 if current_price > 0 else 0
            
            # Stock appreciation return % = (Strike Price - Stock Purchase Price) / Stock Purchase Price
            stock_appreciation_pct = ((strike - current_price) / current_price) * 100 if current_price > 0 else 0
            
            # Call premium return % = Call Premium / Stock Purchase Price
            call_premium_pct = (call_premium / current_price) * 100 if current_price > 0 else 0
            
            # Calculate returns for not exercised scenario
            # Total Return = Call Premium
            total_return_not_exercised = call_premium
            total_return_pct_not_exercised = (total_return_not_exercised / current_price) * 100 if current_price > 0 else 0
            
            covered_calls.append({
                'strike': strike,
                'callPremium': round(call_premium, 2),
                'totalReturnExercised': round(total_return_exercised, 2),
                'totalReturnPctExercised': round(total_return_pct_exercised, 2),
                'totalReturnNotExercised': round(total_return_not_exercised, 2),
                'totalReturnPctNotExercised': round(total_return_pct_not_exercised, 2),
                'stockAppreciationPct': round(stock_appreciation_pct, 2),
                'callPremiumPct': round(call_premium_pct, 2),
            })
    except Exception as e:
        # If there's an error processing options, log it and return what we have
        logger.error(f"Error processing covered call returns: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return covered_calls


def get_leaps_expirations(ticker: str) -> List[str]:
    """
    Get LEAPS expiration dates (Jan of next year or later).
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        List of expiration date strings (YYYY-MM-DD format) for LEAPS
    """
    try:
        provider = ProviderFactory.get_default_provider()
        try:
            expirations = provider.fetch_options_expirations(ticker)
        except DataNotAvailableError:
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
                continue
        
        # Sort by date
        leaps.sort(key=lambda x: datetime.strptime(x, '%Y-%m-%d'))
        return leaps
        
    except Exception as e:
        logger.error(f"Error fetching LEAPS expirations for {ticker}: {str(e)}")
        return []


def calculate_risk_reversal_strategies(ticker: str, current_price: float) -> Dict[str, List[Dict[str, Any]]]:
    """
    Calculate Risk Reversal strategies for LEAPS expirations.
    
    Algorithm based on risk_reversal.md specs:
    - Only LEAPS expiring Jan next year or later
    - Put strike: close to current price (90% to 130% of current price)
    - Call strike: close to or slightly higher than put strike
    - Ratios: 1:1, 1:2, Collar (1:1 or 1:2 with sold OTM call)
    - Net cost: as close to $0 as possible, max 3% of current price
    - Always use average of bid/ask prices (filter out missing quotes)
    
    Sorting priority:
    1. Put strike proximity to current price
    2. Call strike proximity to put strike
    3. Net cost closest to $0
    """
    strategies_by_expiration = {}
    
    try:
        provider = ProviderFactory.get_default_provider()
        leaps_expirations = get_leaps_expirations(ticker)
        
        logger.info(f"Risk Reversal for {ticker}: Found {len(leaps_expirations)} LEAPS expirations: {leaps_expirations}")
        
        if not leaps_expirations:
            logger.warning(f"Risk Reversal for {ticker}: No LEAPS expirations found")
            return strategies_by_expiration
        
        logger.info(f"Risk Reversal for {ticker}: Current price=${current_price:.2f}")
        
        today = date.today()
        
        for expiration in leaps_expirations:
            try:
                try:
                    opt_chain = provider.fetch_options_chain(ticker, expiration)
                except DataNotAvailableError:
                    logger.debug(f"Risk Reversal for {ticker} {expiration}: Options chain not available")
                    continue
                
                strategies = []
                
                if not opt_chain.puts or not opt_chain.calls:
                    logger.debug(f"Risk Reversal for {ticker} {expiration}: Missing puts or calls")
                    continue

                def get_mid_price(bid, ask) -> Optional[float]:
                    """Only use average of bid/ask. Filter out missing quotes."""
                    if bid is not None and ask is not None and bid > 0 and ask > 0:
                        return (float(bid) + float(ask)) / 2.0
                    return None

                # Build put options list (90% to 130% of current price)
                min_put_strike = current_price * 0.90
                max_put_strike = current_price * 1.30
                
                puts = []
                for p in opt_chain.puts:
                    if p.strike < min_put_strike or p.strike > max_put_strike:
                        continue
                    mid = get_mid_price(p.bid, p.ask)
                    if mid is None:
                        continue
                    puts.append({'strike': round(p.strike, 2), 'mid': mid, 'bid': p.bid, 'ask': p.ask})

                # Build call options list (within 30% of current price for now, will filter further)
                min_call_strike = current_price * 0.90
                max_call_strike = current_price * 1.50  # Allow higher for collar sold calls
                
                calls = []
                for c in opt_chain.calls:
                    if c.strike < min_call_strike or c.strike > max_call_strike:
                        continue
                    mid = get_mid_price(c.bid, c.ask)
                    if mid is None:
                        continue
                    calls.append({'strike': round(c.strike, 2), 'mid': mid, 'bid': c.bid, 'ask': c.ask})

                if not puts or not calls:
                    logger.debug(f"Risk Reversal for {ticker} {expiration}: No valid quotes after filtering")
                    continue

                exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
                days_to_exp = (exp_date - today).days
                cost_limit = current_price * 0.03

                # Sort puts by proximity to current price
                puts_sorted = sorted(puts, key=lambda p: abs(p['strike'] - current_price))

                # --- 1:1 strategies ---
                strategies_1_1 = []
                for put in puts_sorted:
                    # Calls should be at or above put strike
                    eligible_calls = [c for c in calls if c['strike'] >= put['strike']]
                    # Sort calls by proximity to put strike
                    eligible_calls_sorted = sorted(eligible_calls, key=lambda c: abs(c['strike'] - put['strike']))
                    
                    for call in eligible_calls_sorted[:10]:  # Limit combinations
                        net_cost = call['mid'] - put['mid']
                        if abs(net_cost) > cost_limit:
                            continue
                        cost_pct = (net_cost / current_price) * 100 if current_price > 0 else 0
                        put_risk = put['strike'] * 100
                        strategies_1_1.append({
                            'ratio': '1:1',
                            'put_strike': put['strike'],
                            'call_strike': call['strike'],
                            'put_bid': round(put['mid'], 2),
                            'call_ask': round(call['mid'], 2),
                            'put_breakeven': round(put['strike'] - put['mid'], 2),
                            'call_breakeven': round(call['strike'] + call['mid'], 2),
                            'strike_spread': round(abs(call['strike'] - put['strike']), 2),
                            'cost': round(net_cost, 2),
                            'cost_pct': round(cost_pct, 2),
                            'days_to_expiration': days_to_exp,
                            'put_risk': round(put_risk, 2),
                            'put_risk_formatted': f"{put_risk:,.2f}",
                            'expiration': expiration,
                            'put_proximity': abs(put['strike'] - current_price),
                            'call_proximity': abs(call['strike'] - put['strike']),
                        })

                # Sort 1:1 by: put proximity, call proximity to put, then net cost
                strategies_1_1.sort(key=lambda s: (s['put_proximity'], s['call_proximity'], abs(s['cost'])))
                strategies_1_1 = strategies_1_1[:5]

                # --- 1:2 strategies ---
                strategies_1_2 = []
                for put in puts_sorted:
                    eligible_calls = [c for c in calls if c['strike'] >= put['strike']]
                    eligible_calls_sorted = sorted(eligible_calls, key=lambda c: abs(c['strike'] - put['strike']))
                    
                    for call in eligible_calls_sorted[:10]:
                        net_cost = (2 * call['mid']) - put['mid']
                        if abs(net_cost) > cost_limit:
                            continue
                        cost_pct = (net_cost / current_price) * 100 if current_price > 0 else 0
                        put_risk = put['strike'] * 100
                        strategies_1_2.append({
                            'ratio': '1:2',
                            'put_strike': put['strike'],
                            'call_strike': call['strike'],
                            'put_bid': round(put['mid'], 2),
                            'call_ask': round(call['mid'], 2),
                            'put_breakeven': round(put['strike'] - put['mid'], 2),
                            'call_breakeven': round(call['strike'] + (net_cost / 2), 2),  # Adjusted for 2 calls
                            'strike_spread': round(abs(call['strike'] - put['strike']), 2),
                            'cost': round(net_cost, 2),
                            'cost_pct': round(cost_pct, 2),
                            'days_to_expiration': days_to_exp,
                            'put_risk': round(put_risk, 2),
                            'put_risk_formatted': f"{put_risk:,.2f}",
                            'expiration': expiration,
                            'put_proximity': abs(put['strike'] - current_price),
                            'call_proximity': abs(call['strike'] - put['strike']),
                        })

                strategies_1_2.sort(key=lambda s: (s['put_proximity'], s['call_proximity'], abs(s['cost'])))
                strategies_1_2 = strategies_1_2[:5]

                # --- Collar strategies (sell put, buy call(s), sell OTM call) ---
                strategies_collar = []
                for put in puts_sorted:
                    eligible_calls = [c for c in calls if c['strike'] >= put['strike']]
                    eligible_calls_sorted = sorted(eligible_calls, key=lambda c: abs(c['strike'] - put['strike']))
                    
                    for call in eligible_calls_sorted[:5]:
                        # Find OTM calls to sell (strikes higher than the bought call)
                        otm_calls = [c for c in calls if c['strike'] > call['strike'] * 1.10]  # At least 10% higher
                        otm_calls_sorted = sorted(otm_calls, key=lambda c: c['strike'])
                        
                        for sold_call in otm_calls_sorted[:3]:
                            # 1:1 Collar: sell put, buy 1 call, sell 1 OTM call
                            net_cost_1_1 = call['mid'] - put['mid'] - sold_call['mid']
                            if abs(net_cost_1_1) <= cost_limit:
                                cost_pct = (net_cost_1_1 / current_price) * 100 if current_price > 0 else 0
                                put_risk = put['strike'] * 100
                                strategies_collar.append({
                                    'ratio': 'Collar',
                                    'put_strike': put['strike'],
                                    'call_strike': call['strike'],
                                    'sold_call_strike': sold_call['strike'],
                                    'put_bid': round(put['mid'], 2),
                                    'call_ask': round(call['mid'], 2),
                                    'sold_call_bid': round(sold_call['mid'], 2),
                                    'put_breakeven': round(put['strike'] - put['mid'], 2),
                                    'call_breakeven': round(call['strike'] + net_cost_1_1, 2),
                                    'strike_spread': round(abs(call['strike'] - put['strike']), 2),
                                    'cost': round(net_cost_1_1, 2),
                                    'cost_pct': round(cost_pct, 2),
                                    'days_to_expiration': days_to_exp,
                                    'put_risk': round(put_risk, 2),
                                    'put_risk_formatted': f"{put_risk:,.2f}",
                                    'expiration': expiration,
                                    'put_proximity': abs(put['strike'] - current_price),
                                    'call_proximity': abs(call['strike'] - put['strike']),
                                    'collar_type': '1:1',
                                    'max_profit_strike': sold_call['strike'],
                                })

                            # 1:2 Collar: sell put, buy 2 calls, sell 2 OTM calls
                            net_cost_1_2 = (2 * call['mid']) - put['mid'] - (2 * sold_call['mid'])
                            if abs(net_cost_1_2) <= cost_limit:
                                cost_pct = (net_cost_1_2 / current_price) * 100 if current_price > 0 else 0
                                put_risk = put['strike'] * 100
                                strategies_collar.append({
                                    'ratio': 'Collar',
                                    'put_strike': put['strike'],
                                    'call_strike': call['strike'],
                                    'sold_call_strike': sold_call['strike'],
                                    'put_bid': round(put['mid'], 2),
                                    'call_ask': round(call['mid'], 2),
                                    'sold_call_bid': round(sold_call['mid'], 2),
                                    'put_breakeven': round(put['strike'] - put['mid'], 2),
                                    'call_breakeven': round(call['strike'] + (net_cost_1_2 / 2), 2),
                                    'strike_spread': round(abs(call['strike'] - put['strike']), 2),
                                    'cost': round(net_cost_1_2, 2),
                                    'cost_pct': round(cost_pct, 2),
                                    'days_to_expiration': days_to_exp,
                                    'put_risk': round(put_risk, 2),
                                    'put_risk_formatted': f"{put_risk:,.2f}",
                                    'expiration': expiration,
                                    'put_proximity': abs(put['strike'] - current_price),
                                    'call_proximity': abs(call['strike'] - put['strike']),
                                    'collar_type': '1:2',
                                    'max_profit_strike': sold_call['strike'],
                                })

                strategies_collar.sort(key=lambda s: (s['put_proximity'], s['call_proximity'], abs(s['cost'])))
                strategies_collar = strategies_collar[:5]

                # Combine all strategies
                strategies.extend(strategies_1_1 + strategies_1_2 + strategies_collar)
                
                # Find strategies closest to $0 and mark for highlighting
                if strategies:
                    closest_negative = None
                    closest_positive = None
                    closest_negative_abs = None
                    closest_positive_abs = None
                    
                    for strategy in strategies:
                        cost = strategy['cost']
                        if cost < 0:
                            abs_cost = abs(cost)
                            if closest_negative_abs is None or abs_cost < closest_negative_abs:
                                closest_negative = strategy
                                closest_negative_abs = abs_cost
                        elif cost > 0:
                            if closest_positive_abs is None or cost < closest_positive_abs:
                                closest_positive = strategy
                                closest_positive_abs = cost
                    
                    for strategy in strategies:
                        strategy['highlight'] = (
                            strategy == closest_negative or 
                            strategy == closest_positive or
                            strategy['cost'] == 0
                        )
                    
                    strategies_by_expiration[expiration] = strategies
                    
            except Exception as e:
                logger.error(f"Error processing Risk Reversal expiration {expiration} for {ticker}: {str(e)}")
                import traceback
                traceback.print_exc()
                continue
        
        logger.info(f"Risk Reversal for {ticker}: Total expirations with strategies: {len(strategies_by_expiration)}")
        if not strategies_by_expiration:
            logger.warning(
                f"Risk Reversal for {ticker}: No strategies found. Possible reasons: missing bid/ask quotes or no strikes in range."
            )
        
        return strategies_by_expiration
        
    except Exception as e:
        logger.error(f"Error calculating Risk Reversal strategies for {ticker}: {str(e)}")
        import traceback
        traceback.print_exc()
        return strategies_by_expiration

