"""Stock data fetching and metric calculation service."""
import yfinance as yf
import pandas as pd
from typing import Dict, Any, Tuple, List, Optional
from datetime import datetime, timedelta
from app.services.cache_service import get_cached_data, set_cached_data


def fetch_intraday_data(ticker: str) -> Optional[pd.DataFrame]:
    """
    Fetch current day's intraday data for a given ticker.
    
    Args:
        ticker: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
        
    Returns:
        DataFrame with intraday data for today, or None if not available
    """
    try:
        stock = yf.Ticker(ticker)
        today = datetime.now().date()
        
        # Try to get intraday data for today (1-minute intervals)
        # Use period='1d' to get today's data, interval='1m' for 1-minute bars
        intraday = stock.history(period='1d', interval='1m')
        
        if intraday.empty:
            return None
        
        # Check if the data is for today by comparing dates
        # Handle timezone-aware and timezone-naive indices
        if hasattr(intraday.index, 'date'):
            # Timezone-aware index
            intraday_dates = set(intraday.index.date)
        else:
            # Timezone-naive index
            intraday_dates = set([pd.Timestamp(d).date() for d in intraday.index])
        
        if today in intraday_dates:
            # Filter to only today's data
            if hasattr(intraday.index, 'date'):
                intraday_today = intraday[intraday.index.date == today]
            else:
                # Convert to date for comparison
                intraday_today = intraday[[pd.Timestamp(d).date() == today for d in intraday.index]]
            return intraday_today if not intraday_today.empty else None
        else:
            # Data might be from previous day if market is closed
            return None
    except Exception as e:
        # If intraday data fails, return None (not critical)
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
        stock = yf.Ticker(ticker)
        # Fetch past 2 years of data to enable proper SMA calculations
        end_date = datetime.now()
        start_date = end_date - timedelta(days=730)  # 2 years
        
        hist = stock.history(start=start_date, end=end_date)
        
        if hist.empty:
            raise ValueError(f"No data found for ticker: {ticker}")
        
        # Try to fetch intraday data for today
        intraday_today = fetch_intraday_data(ticker)
        
        if intraday_today is not None and not intraday_today.empty:
            # Get today's date
            today = datetime.now().date()
            
            # Remove today's daily data from historical data if it exists
            # (since we'll use intraday data instead for more accuracy)
            if hasattr(hist.index, 'date'):
                hist_dates = hist.index.date
                today_mask = [d == today for d in hist_dates]
            else:
                hist_dates = [pd.Timestamp(d).date() for d in hist.index]
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
    movement_in_stddev = price_change / std_dev
    
    is_positive = price_change >= 0
    
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


def get_stock_metrics(ticker: str) -> Dict[str, Any]:
    """
    Fetch stock data and calculate all required metrics.
    Uses cache if available and not expired (60 minutes).
    Fetches 2 years of data to enable proper SMA calculations.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Dictionary containing:
        - ticker: Stock ticker
        - sma_50: 50-day Simple Moving Average
        - sma_200: 200-day Simple Moving Average
        - devstep: Number of standard deviations from 50-day SMA
        - signal: Trading signal
        - current_price: Current stock price
        - dividend_yield: Dividend yield as a percentage
        - data_points: Number of data points fetched
        - cached: Boolean indicating if data came from cache
        - cache_timestamp: ISO timestamp of cache entry (if cached)
    """
    cached_result = None
    cache_timestamp = None
    
    # Try to get from cache first
    cached_data = get_cached_data(ticker)
    if cached_data:
        data, cache_timestamp = cached_data
        cached_result = True
    else:
        # Fetch from yfinance
        data = fetch_stock_data(ticker)
        # Cache the fetched data
        set_cached_data(ticker, data)
        cached_result = False
    
    # Calculate SMAs
    sma_50 = calculate_sma(data, 50)
    sma_200 = calculate_sma(data, 200)
    
    # Calculate devstep
    devstep = calculate_devstep(data, sma_50)
    
    # Calculate 5-day price movement in standard deviations
    movement_5day, is_price_positive = calculate_5day_price_movement(data, sma_50)
    
    # Calculate signal
    signal = calculate_signal(devstep)
    
    # Get current price
    current_price = float(data['Close'].iloc[-1])
    
    # Fetch dividend yield from yfinance
    dividend_yield = None
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        # dividendYield from yfinance is typically returned as a decimal fraction
        # (e.g., 0.0266 for 2.66%, or 0.0064 for 0.64%)
        # However, some data may be inconsistent and returned as a percentage
        # We use a heuristic: if converting to percentage gives unreasonable value (>20%),
        # treat original as already a percentage
        if 'dividendYield' in info and info['dividendYield'] is not None:
            raw_value = float(info['dividendYield'])
            
            # Try treating as decimal fraction first (standard yfinance format)
            as_percentage = raw_value * 100
            
            # If converted value is unreasonable (>20%), likely already a percentage
            # Most dividend yields are between 0% and 15%, very few exceed 20%
            if as_percentage > 20:
                # Value is likely already a percentage (e.g., 0.58 means 0.58%)
                dividend_yield = raw_value
            else:
                # Value is a decimal fraction (e.g., 0.0064 means 0.64%)
                dividend_yield = as_percentage
    except Exception:
        # If dividend yield cannot be fetched, leave it as None
        dividend_yield = None
    
    result = {
        "ticker": ticker.upper(),
        "sma_50": round(sma_50, 2),
        "sma_200": round(sma_200, 2),
        "devstep": round(devstep, 4),
        "signal": signal,
        "current_price": round(current_price, 2),
        "dividend_yield": round(dividend_yield, 2) if dividend_yield is not None else None,
        "movement_5day_stddev": round(movement_5day, 4),
        "is_price_positive_5day": is_price_positive,
        "data_points": len(data),
        "cached": cached_result
    }
    
    # Add cache_timestamp only if data was cached
    if cached_result and cache_timestamp:
        result["cache_timestamp"] = cache_timestamp.isoformat()
    
    return result


def get_multiple_stock_metrics(tickers: list) -> list:
    """
    Fetch stock metrics for multiple tickers.
    
    Args:
        tickers: List of stock ticker symbols
        
    Returns:
        List of dictionaries containing metrics for each ticker.
        Failed tickers will have an 'error' field instead of metrics.
    """
    results = []
    for ticker in tickers:
        ticker = ticker.strip().upper()
        if not ticker:
            continue
        
        try:
            metrics = get_stock_metrics(ticker)
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
    
    Args:
        ticker: Stock ticker symbol
        current_price: Current stock price
        
    Returns:
        Tuple of (expiration_date, options_by_strike)
        - expiration_date: The last expiration date within 90 days (or None)
        - options_by_strike: Dictionary mapping strike prices to dict with 'put' and 'call' data
    """
    try:
        stock = yf.Ticker(ticker)
        
        # Get all available expiration dates
        expirations = stock.options
        
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
        
        # Get options chain for the last expiration within 90 days
        opt_chain = stock.option_chain(last_expiration)
        
        # Filter strikes within 10% of current price
        price_range_low = current_price * 0.9  # 10% below
        price_range_high = current_price * 1.1  # 10% above
        
        options_by_strike = {}
        
        # Process calls
        if opt_chain.calls is not None and not opt_chain.calls.empty:
            calls_filtered = opt_chain.calls[
                (opt_chain.calls['strike'] >= price_range_low) & 
                (opt_chain.calls['strike'] <= price_range_high)
            ]
            for _, row in calls_filtered.iterrows():
                strike = round(float(row.get('strike', 0)), 2)
                if strike not in options_by_strike:
                    options_by_strike[strike] = {'put': None, 'call': None}
                implied_vol = row.get('impliedVolatility')
                options_by_strike[strike]['call'] = {
                    'contractSymbol': row.get('contractSymbol', ''),
                    'lastPrice': round(float(row.get('lastPrice', 0)), 2) if pd.notna(row.get('lastPrice')) else None,
                    'bid': round(float(row.get('bid', 0)), 2) if pd.notna(row.get('bid')) else None,
                    'ask': round(float(row.get('ask', 0)), 2) if pd.notna(row.get('ask')) else None,
                    'volume': int(row.get('volume', 0)) if pd.notna(row.get('volume')) else 0,
                    'openInterest': int(row.get('openInterest', 0)) if pd.notna(row.get('openInterest')) else 0,
                    'impliedVolatility': round(float(implied_vol) * 100, 2) if pd.notna(implied_vol) and implied_vol is not None else None,
                }
        
        # Process puts
        if opt_chain.puts is not None and not opt_chain.puts.empty:
            puts_filtered = opt_chain.puts[
                (opt_chain.puts['strike'] >= price_range_low) & 
                (opt_chain.puts['strike'] <= price_range_high)
            ]
            for _, row in puts_filtered.iterrows():
                strike = round(float(row.get('strike', 0)), 2)
                if strike not in options_by_strike:
                    options_by_strike[strike] = {'put': None, 'call': None}
                implied_vol = row.get('impliedVolatility')
                options_by_strike[strike]['put'] = {
                    'contractSymbol': row.get('contractSymbol', ''),
                    'lastPrice': round(float(row.get('lastPrice', 0)), 2) if pd.notna(row.get('lastPrice')) else None,
                    'bid': round(float(row.get('bid', 0)), 2) if pd.notna(row.get('bid')) else None,
                    'ask': round(float(row.get('ask', 0)), 2) if pd.notna(row.get('ask')) else None,
                    'volume': int(row.get('volume', 0)) if pd.notna(row.get('volume')) else 0,
                    'openInterest': int(row.get('openInterest', 0)) if pd.notna(row.get('openInterest')) else 0,
                    'impliedVolatility': round(float(implied_vol) * 100, 2) if pd.notna(implied_vol) and implied_vol is not None else None,
                }
        
        return (last_expiration, options_by_strike)
        
    except Exception as e:
        # If options data cannot be fetched, return empty
        import traceback
        print(f"Error fetching options data for {ticker}: {str(e)}")
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
        print(f"Error processing covered call returns: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return covered_calls

