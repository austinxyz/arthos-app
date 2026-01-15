"""Service for preparing stock chart data."""
import pandas as pd
from typing import Dict, Any, List
from datetime import datetime, timedelta
from app.services.stock_price_service import get_stock_prices_as_dataframe


def get_stock_chart_data(ticker: str) -> Dict[str, Any]:
    """
    Get stock data formatted for candlestick chart with SMA lines and STD dev bands.
    Reads data from stock_price table (not from data provider cache).
    Displays the last 365 days on the chart.
    
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
    # Get data from stock_price table
    data = get_stock_prices_as_dataframe(ticker)
    
    if data.empty:
        raise ValueError(f"No price data found for ticker: {ticker}")
    
    # Ensure we have the required columns
    if not all(col in data.columns for col in ['Open', 'High', 'Low', 'Close']):
        raise ValueError(f"Incomplete data for ticker: {ticker}")
    
    # Sort by date to ensure chronological order
    data = data.sort_index()
    
    # Use stored moving averages if available, otherwise calculate
    if 'dma_50' in data.columns and 'dma_200' in data.columns:
        # Use stored moving averages from database
        data['SMA_50'] = data['dma_50']
        data['SMA_200'] = data['dma_200']
    else:
        # Calculate rolling SMAs if not stored
        data['SMA_50'] = data['Close'].rolling(window=50, min_periods=50).mean()
        data['SMA_200'] = data['Close'].rolling(window=200, min_periods=200).mean()
    
    # Calculate rolling standard deviation for 50-day window (needed for std bands)
    data['STD_50'] = data['Close'].rolling(window=50, min_periods=50).std()
    
    # Calculate STD dev bands around SMA 50
    data['SMA_50_plus_1std'] = data['SMA_50'] + data['STD_50']
    data['SMA_50_plus_2std'] = data['SMA_50'] + (2 * data['STD_50'])
    data['SMA_50_plus_3std'] = data['SMA_50'] + (3 * data['STD_50'])
    data['SMA_50_minus_1std'] = data['SMA_50'] - data['STD_50']
    data['SMA_50_minus_2std'] = data['SMA_50'] - (2 * data['STD_50'])
    data['SMA_50_minus_3std'] = data['SMA_50'] - (3 * data['STD_50'])
    
    # Data from database is already daily data (no intraday)
    # Filter to show last 365 days
    display_data = data.tail(365)
    
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
    
    # Get current values from the most recent data point
    current_price = float(data['Close'].iloc[-1])
    
    # Get the last non-null SMA values from data
    sma_50_values = data['SMA_50'].dropna()
    sma_200_values = data['SMA_200'].dropna()
    
    if len(sma_50_values) > 0:
        sma_50_current = float(sma_50_values.iloc[-1])
    else:
        # Fallback: calculate from close prices
        if len(data) >= 50:
            sma_50_current = float(data['Close'].tail(50).mean())
        else:
            sma_50_current = float(data['Close'].mean())
    
    if len(sma_200_values) > 0:
        sma_200_current = float(sma_200_values.iloc[-1])
    else:
        # Fallback: calculate from close prices
        if len(data) >= 200:
            sma_200_current = float(data['Close'].tail(200).mean())
        else:
            sma_200_current = float(data['Close'].mean())
    
    # Get timestamp of the latest data point (for display in metrics)
    latest_timestamp = data.index[-1]
    try:
        if isinstance(latest_timestamp, pd.Timestamp):
            # Normalize to timezone-naive if needed
            if latest_timestamp.tz is not None:
                latest_timestamp = latest_timestamp.tz_localize(None)
            # Format timestamp for display (daily data - show just the date)
            current_data_timestamp = latest_timestamp.strftime('%Y-%m-%d')
        else:
            # Convert to Timestamp if it's not already
            ts_obj = pd.Timestamp(latest_timestamp)
            if ts_obj.tz is not None:
                ts_obj = ts_obj.tz_localize(None)
            current_data_timestamp = ts_obj.strftime('%Y-%m-%d')
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

