"""Service for preparing stock chart data."""
import pandas as pd
from typing import Dict, Any, List
from app.services.stock_service import fetch_stock_data, calculate_sma
from app.services.cache_service import get_cached_data, set_cached_data
from datetime import datetime


def get_stock_chart_data(ticker: str) -> Dict[str, Any]:
    """
    Get stock data formatted for candlestick chart with SMA lines and STD dev bands.
    Fetches 2 years of data but only displays the last 365 days on the chart.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Dictionary containing:
        - ticker: Stock ticker
        - dates: List of date strings (ISO format) - last 365 days
        - candlestick_data: List of dicts with [date, open, high, low, close] - last 365 days
        - sma_50: List of [date, sma_50_value] pairs - last 365 days
        - sma_200: List of [date, sma_200_value] pairs - last 365 days
        - std_bands: Dictionary with std dev bands (1std_upper, 1std_lower, 2std_upper, 2std_lower)
        - current_price: Current stock price
        - sma_50_current: Current 50-day SMA
        - sma_200_current: Current 200-day SMA
        
    Raises:
        ValueError: If ticker is invalid or data cannot be fetched
    """
    # Try to get from cache first
    # We need at least 565 days of data (365 for display + 200 for SMA calculation)
    cached_data = get_cached_data(ticker)
    if cached_data:
        data, _ = cached_data
        # Check if cached data has enough days for proper SMA calculations
        # We need at least 565 days (365 display + 200 for SMA 200 calculation)
        if len(data) < 565:
            # Cached data doesn't have enough days, fetch fresh data
            data = fetch_stock_data(ticker)
            # Cache the fetched data
            set_cached_data(ticker, data)
    else:
        # Fetch from yfinance
        data = fetch_stock_data(ticker)
        # Cache the fetched data
        set_cached_data(ticker, data)
    
    # Ensure we have the required columns
    if not all(col in data.columns for col in ['Open', 'High', 'Low', 'Close']):
        raise ValueError(f"Incomplete data for ticker: {ticker}")
    
    # Sort by date to ensure chronological order
    data = data.sort_index()
    
    # Calculate rolling SMAs and standard deviations for all data
    data['SMA_50'] = data['Close'].rolling(window=50, min_periods=50).mean()
    data['SMA_200'] = data['Close'].rolling(window=200, min_periods=200).mean()
    
    # Calculate rolling standard deviation for 50-day window
    data['STD_50'] = data['Close'].rolling(window=50, min_periods=50).std()
    
    # Calculate STD dev bands around SMA 50
    data['SMA_50_plus_1std'] = data['SMA_50'] + data['STD_50']
    data['SMA_50_plus_2std'] = data['SMA_50'] + (2 * data['STD_50'])
    data['SMA_50_plus_3std'] = data['SMA_50'] + (3 * data['STD_50'])
    data['SMA_50_minus_1std'] = data['SMA_50'] - data['STD_50']
    data['SMA_50_minus_2std'] = data['SMA_50'] - (2 * data['STD_50'])
    data['SMA_50_minus_3std'] = data['SMA_50'] - (3 * data['STD_50'])
    
    # Separate daily data from intraday data for chart display
    # We'll aggregate today's intraday data into a daily candle and show it on the chart
    today = datetime.now().date()
    
    # Normalize index to timezone-naive for consistent comparison
    # This handles cases where index might be timezone-aware or have mixed timezones
    data_normalized = data.copy()
    if isinstance(data.index, pd.DatetimeIndex):
        if data.index.tz is not None:
            # Convert timezone-aware to timezone-naive
            data_normalized.index = data.index.tz_localize(None)
        else:
            # Already timezone-naive, but ensure all values are properly normalized
            data_normalized.index = pd.to_datetime(data.index, utc=False)
    
    # Separate daily data from intraday data
    # Daily data: timestamps at midnight or dates before today
    # Intraday data: timestamps from today with time components
    daily_mask = []
    intraday_mask = []
    for ts in data_normalized.index:
        ts_obj = pd.Timestamp(ts)
        # Normalize to timezone-naive if needed
        if ts_obj.tz is not None:
            ts_obj = ts_obj.tz_localize(None)
        # Check if it's a daily timestamp (at midnight) or before today
        if ts_obj.hour == 0 and ts_obj.minute == 0:
            daily_mask.append(True)
            intraday_mask.append(False)
        elif ts_obj.date() < today:
            daily_mask.append(True)
            intraday_mask.append(False)
        else:
            # Has time component and is today - this is intraday data
            daily_mask.append(False)
            intraday_mask.append(True)
    
    daily_data = data_normalized[daily_mask] if any(daily_mask) else pd.DataFrame()
    intraday_today = data_normalized[intraday_mask] if any(intraday_mask) else pd.DataFrame()
    
    # Normalize daily_data index to timezone-naive before aggregating
    if not daily_data.empty:
        daily_data = daily_data.copy()
        normalized_daily_timestamps = []
        for ts in daily_data.index:
            ts_obj = pd.Timestamp(ts)
            if ts_obj.tz is not None:
                normalized_daily_timestamps.append(ts_obj.tz_localize(None))
            else:
                normalized_daily_timestamps.append(ts_obj)
        daily_data.index = pd.DatetimeIndex(normalized_daily_timestamps)
    
    # Aggregate today's intraday data into a daily candle
    if not intraday_today.empty:
        # Create aggregated daily candle for today (timezone-naive timestamp)
        today_timestamp = pd.Timestamp(today).replace(hour=0, minute=0, second=0, microsecond=0)
        # Ensure it's timezone-naive
        if today_timestamp.tz is not None:
            today_timestamp = today_timestamp.tz_localize(None)
        
        # Remove today's daily data if it exists (we'll use aggregated intraday instead)
        if not daily_data.empty:
            today_daily_mask = [pd.Timestamp(ts).date() == today for ts in daily_data.index]
            if any(today_daily_mask):
                daily_data = daily_data[~pd.Series(today_daily_mask, index=daily_data.index)]
        
        # Calculate SMA/STD values from daily_data only (excluding today)
        # This ensures we use the last 50/200 daily candles, not intraday data points
        sma_50_value = None
        std_50_value = None
        sma_200_value = None
        
        if not daily_data.empty:
            # Calculate SMA_50 from last 50 daily candles (excluding today)
            if len(daily_data) >= 50:
                recent_50_daily = daily_data['Close'].tail(50)
                sma_50_value = recent_50_daily.mean()
                std_50_value = recent_50_daily.std()
            elif len(daily_data) > 0:
                # Use available daily data if less than 50 days
                sma_50_value = daily_data['Close'].mean()
                std_50_value = daily_data['Close'].std()
            
            # Calculate SMA_200 from last 200 daily candles (excluding today)
            if len(daily_data) >= 200:
                recent_200_daily = daily_data['Close'].tail(200)
                sma_200_value = recent_200_daily.mean()
            elif len(daily_data) > 0:
                # Use available daily data if less than 200 days
                sma_200_value = daily_data['Close'].mean()
        
        # Create aggregated daily candle for today
        today_close = intraday_today['Close'].iloc[-1]
        today_candle_data = {
            'Open': intraday_today['Open'].iloc[0],
            'High': intraday_today['High'].max(),
            'Low': intraday_today['Low'].min(),
            'Close': today_close,
            'Volume': intraday_today['Volume'].sum(),
            'Dividends': 0.0,
            'Stock Splits': 0.0,
            'SMA_50': sma_50_value,
            'SMA_200': sma_200_value,
            'STD_50': std_50_value
        }
        
        # Calculate STD bands if we have SMA_50 and STD_50
        if sma_50_value is not None and std_50_value is not None:
            today_candle_data['SMA_50_plus_1std'] = sma_50_value + std_50_value
            today_candle_data['SMA_50_plus_2std'] = sma_50_value + (2 * std_50_value)
            today_candle_data['SMA_50_plus_3std'] = sma_50_value + (3 * std_50_value)
            today_candle_data['SMA_50_minus_1std'] = sma_50_value - std_50_value
            today_candle_data['SMA_50_minus_2std'] = sma_50_value - (2 * std_50_value)
            today_candle_data['SMA_50_minus_3std'] = sma_50_value - (3 * std_50_value)
        else:
            today_candle_data['SMA_50_plus_1std'] = None
            today_candle_data['SMA_50_plus_2std'] = None
            today_candle_data['SMA_50_plus_3std'] = None
            today_candle_data['SMA_50_minus_1std'] = None
            today_candle_data['SMA_50_minus_2std'] = None
            today_candle_data['SMA_50_minus_3std'] = None
        
        today_candle = pd.DataFrame([today_candle_data], index=[today_timestamp])
        
        # Add today's aggregated candle to daily data
        if not daily_data.empty:
            daily_data = pd.concat([daily_data, today_candle])
        else:
            daily_data = today_candle
        
        # Sort by date to ensure chronological order
        daily_data = daily_data.sort_index()
        
        # Recalculate rolling SMAs and standard deviations for daily_data (now including today)
        # This ensures the rolling window calculation is correct using only daily candles
        daily_data['SMA_50'] = daily_data['Close'].rolling(window=50, min_periods=50).mean()
        daily_data['SMA_200'] = daily_data['Close'].rolling(window=200, min_periods=200).mean()
        daily_data['STD_50'] = daily_data['Close'].rolling(window=50, min_periods=50).std()
        
        # Recalculate STD dev bands
        daily_data['SMA_50_plus_1std'] = daily_data['SMA_50'] + daily_data['STD_50']
        daily_data['SMA_50_plus_2std'] = daily_data['SMA_50'] + (2 * daily_data['STD_50'])
        daily_data['SMA_50_plus_3std'] = daily_data['SMA_50'] + (3 * daily_data['STD_50'])
        daily_data['SMA_50_minus_1std'] = daily_data['SMA_50'] - daily_data['STD_50']
        daily_data['SMA_50_minus_2std'] = daily_data['SMA_50'] - (2 * daily_data['STD_50'])
        daily_data['SMA_50_minus_3std'] = daily_data['SMA_50'] - (3 * daily_data['STD_50'])
    
    # Ensure the index is timezone-naive (should already be, but double-check)
    if not daily_data.empty:
        daily_data = daily_data.copy()
        normalized_timestamps = []
        for ts in daily_data.index:
            ts_obj = pd.Timestamp(ts)
            # Convert to timezone-naive if it's timezone-aware
            if ts_obj.tz is not None:
                normalized_timestamps.append(ts_obj.tz_localize(None))
            else:
                normalized_timestamps.append(ts_obj)
        daily_data.index = pd.DatetimeIndex(normalized_timestamps)
    
    # Filter daily data to show from Jan 1, 2025 onwards (or last 365 days)
    # Index is now guaranteed to be timezone-naive
    jan_1_2025 = pd.Timestamp('2025-01-01')  # Timezone-naive by default
    data_from_jan_1 = daily_data[daily_data.index >= jan_1_2025]
    
    if len(data_from_jan_1) > 0:
        # We have data from Jan 1, 2025, show up to 365 days from that point
        display_data = data_from_jan_1.head(365)
    else:
        # Jan 1, 2025 data not available (might be future date or no trading day), show last 365 days
        display_data = daily_data.tail(365)
    
    # Prepare candlestick data (last 365 days)
    candlestick_data = []
    dates = []
    
    for date, row in display_data.iterrows():
        date_str = date.strftime('%Y-%m-%d')
        dates.append(date_str)
        candlestick_data.append({
            'x': date_str,
            'open': float(row['Open']),
            'high': float(row['High']),
            'low': float(row['Low']),
            'close': float(row['Close'])
        })
    
    # Prepare SMA data (last 365 days)
    sma_50_data = []
    sma_200_data = []
    
    # Prepare STD dev bands data (last 365 days)
    std_1_upper = []
    std_1_lower = []
    std_2_upper = []
    std_2_lower = []
    std_3_upper = []
    std_3_lower = []
    
    for i, (date, row) in enumerate(display_data.iterrows()):
        date_str = date.strftime('%Y-%m-%d')
        
        # SMA values
        sma_50 = float(row['SMA_50']) if pd.notna(row['SMA_50']) else None
        sma_200 = float(row['SMA_200']) if pd.notna(row['SMA_200']) else None
        
        sma_50_data.append({
            'x': date_str,
            'y': sma_50
        })
        sma_200_data.append({
            'x': date_str,
            'y': sma_200
        })
        
        # STD dev bands (only if SMA_50 is available)
        if pd.notna(row['SMA_50']):
            std_1_upper.append({
                'x': date_str,
                'y': float(row['SMA_50_plus_1std']) if pd.notna(row['SMA_50_plus_1std']) else None
            })
            std_1_lower.append({
                'x': date_str,
                'y': float(row['SMA_50_minus_1std']) if pd.notna(row['SMA_50_minus_1std']) else None
            })
            std_2_upper.append({
                'x': date_str,
                'y': float(row['SMA_50_plus_2std']) if pd.notna(row['SMA_50_plus_2std']) else None
            })
            std_2_lower.append({
                'x': date_str,
                'y': float(row['SMA_50_minus_2std']) if pd.notna(row['SMA_50_minus_2std']) else None
            })
            std_3_upper.append({
                'x': date_str,
                'y': float(row['SMA_50_plus_3std']) if pd.notna(row['SMA_50_plus_3std']) else None
            })
            std_3_lower.append({
                'x': date_str,
                'y': float(row['SMA_50_minus_3std']) if pd.notna(row['SMA_50_minus_3std']) else None
            })
        else:
            std_1_upper.append({'x': date_str, 'y': None})
            std_1_lower.append({'x': date_str, 'y': None})
            std_2_upper.append({'x': date_str, 'y': None})
            std_2_lower.append({'x': date_str, 'y': None})
            std_3_upper.append({'x': date_str, 'y': None})
            std_3_lower.append({'x': date_str, 'y': None})
    
    # Get current values
    # Use the most recent data point which could be intraday data for today
    current_price = float(data['Close'].iloc[-1])
    
    # Use the last value from the rolling SMA calculation (which uses daily data only)
    # This ensures consistency with what's shown on the chart
    if not daily_data.empty:
        # Get the last non-null SMA values from daily_data
        sma_50_values = daily_data['SMA_50'].dropna()
        sma_200_values = daily_data['SMA_200'].dropna()
        
        if len(sma_50_values) > 0:
            sma_50_current = float(sma_50_values.iloc[-1])
        else:
            # Fallback to calculate_sma if no rolling values available
            sma_50_current = calculate_sma(data, 50)
        
        if len(sma_200_values) > 0:
            sma_200_current = float(sma_200_values.iloc[-1])
        else:
            # Fallback to calculate_sma if no rolling values available
            sma_200_current = calculate_sma(data, 200)
    else:
        # Fallback if no daily data
        sma_50_current = calculate_sma(data, 50)
        sma_200_current = calculate_sma(data, 200)
    
    # Get timestamp of the latest data point (for display in metrics)
    # Use the original data (which includes intraday) to get the most recent timestamp
    latest_timestamp = data.index[-1]
    try:
        if isinstance(latest_timestamp, pd.Timestamp):
            # Normalize to timezone-naive if needed
            if latest_timestamp.tz is not None:
                latest_timestamp = latest_timestamp.tz_localize(None)
            # Format timestamp for display
            if latest_timestamp.hour == 0 and latest_timestamp.minute == 0:
                # Daily data - show just the date
                current_data_timestamp = latest_timestamp.strftime('%Y-%m-%d')
            else:
                # Intraday data - show date and time
                current_data_timestamp = latest_timestamp.strftime('%Y-%m-%d %H:%M:%S')
        else:
            # Convert to Timestamp if it's not already
            ts_obj = pd.Timestamp(latest_timestamp)
            if ts_obj.tz is not None:
                ts_obj = ts_obj.tz_localize(None)
            if ts_obj.hour == 0 and ts_obj.minute == 0:
                current_data_timestamp = ts_obj.strftime('%Y-%m-%d')
            else:
                current_data_timestamp = ts_obj.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        # Fallback to string representation
        current_data_timestamp = str(latest_timestamp)
    
    return {
        "ticker": ticker.upper(),
        "dates": dates,
        "candlestick_data": candlestick_data,
        "sma_50": sma_50_data,
        "sma_200": sma_200_data,
        "std_bands": {
            "std_1_upper": std_1_upper,
            "std_1_lower": std_1_lower,
            "std_2_upper": std_2_upper,
            "std_2_lower": std_2_lower,
            "std_3_upper": std_3_upper,
            "std_3_lower": std_3_lower
        },
        "current_price": round(current_price, 2),
        "sma_50_current": round(sma_50_current, 2),
        "sma_200_current": round(sma_200_current, 2),
        "current_data_timestamp": current_data_timestamp
    }

