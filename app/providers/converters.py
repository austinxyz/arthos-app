"""Data conversion utilities for provider data."""
import pandas as pd
from typing import List
from datetime import date
from app.providers.base import StockPriceData


def stock_price_data_to_dataframe(price_data: List[StockPriceData], preserve_time: bool = False) -> pd.DataFrame:
    """
    Convert list of StockPriceData to pandas DataFrame.
    
    Args:
        price_data: List of StockPriceData objects
        preserve_time: If True, preserves time components for intraday data using timestamp field.
                     If False (default), uses date only (for daily data).
        
    Returns:
        pandas DataFrame with date/datetime index and columns: Open, High, Low, Close, Volume
    """
    if not price_data:
        return pd.DataFrame()
    
    # Convert to list of dicts
    data_dicts = [
        {
            'Open': item.open,
            'High': item.high,
            'Low': item.low,
            'Close': item.close,
            'Volume': item.volume
        }
        for item in price_data
    ]
    
    # Create DataFrame
    df = pd.DataFrame(data_dicts)
    
    # Set date/datetime as index
    if preserve_time:
        # For intraday data, use timestamp if available, otherwise use date
        dates = []
        for item in price_data:
            if item.timestamp is not None:
                dates.append(pd.Timestamp(item.timestamp))
            else:
                dates.append(pd.Timestamp(item.date))
    else:
        # For daily data, use date only
        dates = [pd.Timestamp(item.date) for item in price_data]
    df.index = dates
    
    # Sort by date
    df = df.sort_index()
    
    return df


def aggregate_intraday_to_daily(intraday_data: List[StockPriceData]) -> StockPriceData:
    """
    Aggregate intraday data into a single daily data point.
    
    Args:
        intraday_data: List of StockPriceData objects (all for the same date)
        
    Returns:
        Single StockPriceData object with aggregated OHLC and total volume
    """
    if not intraday_data:
        raise ValueError("Cannot aggregate empty intraday data")
    
    # All entries should have the same date
    target_date = intraday_data[0].date
    
    # Aggregate OHLC
    open_price = intraday_data[0].open  # First open
    close_price = intraday_data[-1].close  # Last close
    high_price = max(item.high for item in intraday_data)
    low_price = min(item.low for item in intraday_data)
    total_volume = sum(item.volume for item in intraday_data)
    
    return StockPriceData(
        date=target_date,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=total_volume
    )
