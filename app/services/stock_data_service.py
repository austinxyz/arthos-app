"""Stock data fetching service - raw data operations from providers."""
import pandas as pd
from typing import Tuple, Optional
from datetime import datetime, timedelta, date
import logging
from app.providers.factory import ProviderFactory
from app.providers.converters import stock_price_data_to_dataframe

logger = logging.getLogger(__name__)


def separate_daily_intraday(data: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Separate daily data from intraday data based on timestamp characteristics.

    Daily data: timestamps at midnight (00:00) or dates before today
    Intraday data: timestamps with time component on today's date

    Args:
        data: DataFrame with DateTimeIndex

    Returns:
        Tuple of (daily_data, intraday_data) DataFrames
    """
    today = datetime.now().date()
    daily_mask = []
    intraday_mask = []

    for ts in data.index:
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

    daily_data = data[daily_mask] if any(daily_mask) else pd.DataFrame()
    intraday_data = data[intraday_mask] if any(intraday_mask) else pd.DataFrame()

    return daily_data, intraday_data


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

        if hist_data is None or len(hist_data) == 0:
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
