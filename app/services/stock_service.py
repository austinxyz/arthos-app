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
    
    Args:
        ticker: Stock ticker symbol
        current_price: Current stock price
        
    Returns:
        Tuple of (expiration_date, options_by_strike)
        - expiration_date: The last expiration date within 90 days (or None)
        - options_by_strike: Dictionary mapping strike prices to dict with 'put' and 'call' data
    """
    try:
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
                    'impliedVolatility': round(call.implied_volatility * 100, 2) if call.implied_volatility is not None else None,
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
                    'impliedVolatility': round(put.implied_volatility * 100, 2) if put.implied_volatility is not None else None,
                }
        
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
    Calculate simplified risk reversal strategies for LEAPS expirations.
    Strategy:
      - 1:1: Sell 1 put, buy 1 call (strikes closest to current price)
      - 1:2: Sell 1 put, buy 2 calls (higher strikes to reduce call premium)
    
    Rules:
      - Minimize out-of-pocket cost (prefer lower net cost, negative is best)
      - 1:1 uses strikes closest to current price
      - 1:2 uses higher put strikes and higher call strikes
      - Return at most 5 pairs per ratio per expiration
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
        
        # Get current date for days to expiration calculation
        today = date.today()
        
        for expiration in leaps_expirations:
            try:
                try:
                    opt_chain = provider.fetch_options_chain(ticker, expiration)
                except DataNotAvailableError:
                    logger.debug(f"Risk Reversal for {ticker} {expiration}: Options chain not available")
                    continue
                
                strategies = []
                
                # Require options with valid bid/ask so we can compute mid prices
                if not opt_chain.puts or not opt_chain.calls:
                    logger.debug(f"Risk Reversal for {ticker} {expiration}: Missing puts or calls")
                    continue

                def mid_price(bid, ask) -> Optional[float]:
                    if bid is None or ask is None:
                        return None
                    if bid <= 0 or ask <= 0:
                        return None
                    return (float(bid) + float(ask)) / 2.0

                puts = []
                for p in opt_chain.puts:
                    mid = mid_price(p.bid, p.ask)
                    if mid is None:
                        continue
                    puts.append({'strike': round(p.strike, 2), 'mid': mid})

                calls = []
                for c in opt_chain.calls:
                    mid = mid_price(c.bid, c.ask)
                    if mid is None:
                        continue
                    calls.append({'strike': round(c.strike, 2), 'mid': mid})

                if not puts or not calls:
                    logger.debug(f"Risk Reversal for {ticker} {expiration}: No valid quotes after filtering")
                    continue

                exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
                days_to_exp = (exp_date - today).days

                # --- 1:1 strategies (closest strikes) ---
                puts_near = sorted(puts, key=lambda p: abs(p['strike'] - current_price))[:10]
                calls_near = sorted(calls, key=lambda c: abs(c['strike'] - current_price))[:10]

                strategies_1_1 = []
                if calls_near:
                    for put in puts_near:
                        call = min(calls_near, key=lambda c: abs(c['strike'] - put['strike']))
                        net_cost = call['mid'] - put['mid']
                        cost_pct = (net_cost / current_price) * 100 if current_price > 0 else 0
                        put_risk = put['strike'] * 100
                        strategies_1_1.append({
                            'strategy': f"{ticker.upper()} {expiration} Sell 1 ${put['strike']:.2f} put and Buy 1 ${call['strike']:.2f} call",
                            'cost': round(net_cost, 2),
                            'cost_pct': round(cost_pct, 2),
                            'put_risk': round(put_risk, 2),
                            'put_risk_formatted': f"{put_risk:,.2f}",
                            'put_strike': put['strike'],
                            'call_strike': call['strike'],
                            'put_bid': round(put['mid'], 2),
                            'call_ask': round(call['mid'], 2),
                            'put_breakeven': round(put['strike'] - put['mid'], 2),
                            'call_breakeven': round(call['strike'] + call['mid'], 2),
                            'strike_spread': round(abs(call['strike'] - put['strike']), 2),
                            'days_to_expiration': days_to_exp,
                            'expiration': expiration,
                            'ratio': '1:1'
                        })

                # Prioritize lowest out-of-pocket cost, then closest strikes
                strategies_1_1.sort(
                    key=lambda s: (s['cost'], abs(s['put_strike'] - current_price), abs(s['call_strike'] - current_price))
                )
                strategies_1_1 = strategies_1_1[:5]

                # --- 1:2 strategies (closest strikes, minimize out-of-pocket) ---
                puts_near_1_2 = sorted(puts, key=lambda p: abs(p['strike'] - current_price))
                calls_near_1_2 = sorted(calls, key=lambda c: abs(c['strike'] - current_price))

                # Prefer strikes at or above current price; fallback to overall nearest if none
                puts_near_1_2 = [p for p in puts_near_1_2 if p['strike'] >= current_price] or puts_near_1_2
                calls_near_1_2 = [c for c in calls_near_1_2 if c['strike'] >= current_price] or calls_near_1_2

                strategies_1_2 = []
                for put in puts_near_1_2[:10]:
                    for call in calls_near_1_2[:12]:
                        # Keep call strike at or above put strike for 1:2 shape
                        if call['strike'] < put['strike']:
                            continue
                        net_cost = (2 * call['mid']) - put['mid']
                        cost_pct = (net_cost / current_price) * 100 if current_price > 0 else 0
                        put_risk = put['strike'] * 100
                        strike_distance = abs(put['strike'] - current_price) + abs(call['strike'] - current_price)

                        strategies_1_2.append({
                            'strategy': f"{ticker.upper()} {expiration} Sell 1 ${put['strike']:.2f} put and Buy 2 ${call['strike']:.2f} calls",
                            'cost': round(net_cost, 2),
                            'cost_pct': round(cost_pct, 2),
                            'put_risk': round(put_risk, 2),
                            'put_risk_formatted': f"{put_risk:,.2f}",
                            'put_strike': put['strike'],
                            'call_strike': call['strike'],
                            'put_bid': round(put['mid'], 2),
                            'call_ask': round(call['mid'], 2),
                            'put_breakeven': round(put['strike'] - put['mid'], 2),
                            'call_breakeven': round(call['strike'] + call['mid'], 2),
                            'strike_spread': round(abs(call['strike'] - put['strike']), 2),
                            'days_to_expiration': days_to_exp,
                            'expiration': expiration,
                            'ratio': '1:2',
                            '_distance': strike_distance
                        })

                # Prioritize closest strikes first, then lowest cost
                strategies_1_2.sort(key=lambda s: (s['_distance'], s['cost']))
                strategies_1_2 = strategies_1_2[:5]

                # Cleanup internal helper key
                for strategy in strategies_1_2:
                    strategy.pop('_distance', None)

                strategies.extend(strategies_1_1 + strategies_1_2)
                
                # Find strategies closest to $0 (one negative, one positive) and mark them for highlighting
                if strategies:
                    closest_negative = None
                    closest_positive = None
                    closest_negative_abs = None
                    closest_positive_abs = None
                    
                    for strategy in strategies:
                        cost = strategy['cost']
                        if cost < 0:
                            # Negative cost - find the one closest to $0 (smallest absolute value)
                            abs_cost = abs(cost)
                            if closest_negative_abs is None or abs_cost < closest_negative_abs:
                                closest_negative = strategy
                                closest_negative_abs = abs_cost
                        elif cost > 0:
                            # Positive cost - find the one closest to $0 (smallest positive)
                            if closest_positive_abs is None or cost < closest_positive_abs:
                                closest_positive = strategy
                                closest_positive_abs = cost
                    
                    # Mark the closest strategies for highlighting
                    for strategy in strategies:
                        strategy['highlight'] = (
                            strategy == closest_negative or 
                            strategy == closest_positive or
                            strategy['cost'] == 0
                        )
                    
                    strategies_by_expiration[expiration] = strategies
                    
            except Exception as e:
                logger.error(f"Error processing expiration {expiration} for {ticker}: {str(e)}")
                import traceback
                traceback.print_exc()
                continue
        
        logger.info(f"Risk Reversal for {ticker}: Total expirations with strategies: {len(strategies_by_expiration)}")
        if not strategies_by_expiration:
            logger.warning(
                f"Risk Reversal for {ticker}: No strategies found. Possible reasons: missing bid/ask quotes or no strikes near/above current price."
            )
        
        return strategies_by_expiration
        
    except Exception as e:
        logger.error(f"Error calculating risk reversal strategies for {ticker}: {str(e)}")
        import traceback
        traceback.print_exc()
        return strategies_by_expiration

