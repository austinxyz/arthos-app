"""Service for managing stock price data and watermarks."""
import yfinance as yf
import pandas as pd
import statistics
from sqlmodel import Session, select
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
from app.database import engine
from app.models.stock_price import StockPrice, StockPriceWatermark


def get_watermark(ticker: str) -> Optional[StockPriceWatermark]:
    """
    Get watermark for a ticker.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        StockPriceWatermark if exists, None otherwise
    """
    with Session(engine) as session:
        watermark = session.get(StockPriceWatermark, ticker.upper())
        return watermark


def update_watermark(ticker: str, earliest_date: date, latest_date: date):
    """
    Create or update watermark for a ticker.
    
    Args:
        ticker: Stock ticker symbol
        earliest_date: Earliest date with data
        latest_date: Latest date with data
    """
    with Session(engine) as session:
        ticker_upper = ticker.upper()
        watermark = session.get(StockPriceWatermark, ticker_upper)
        
        if watermark:
            # Update existing watermark
            watermark.earliest_date = min(watermark.earliest_date, earliest_date)
            watermark.latest_date = max(watermark.latest_date, latest_date)
        else:
            # Create new watermark
            watermark = StockPriceWatermark(
                ticker=ticker_upper,
                earliest_date=earliest_date,
                latest_date=latest_date
            )
            session.add(watermark)
        
        session.commit()
        session.refresh(watermark)


def save_stock_prices(ticker: str, price_data: pd.DataFrame):
    """
    Save stock price data to database with moving averages.
    Only saves daily data (not intraday).
    Calculates 50-day and 200-day moving averages based on close prices.
    
    Args:
        ticker: Stock ticker symbol
        price_data: DataFrame with OHLC data, indexed by date
    """
    if price_data.empty:
        return
    
    ticker_upper = ticker.upper()
    today = datetime.now().date()
    earliest_date = None
    latest_date = None
    
    # Get all existing data for this ticker to calculate moving averages for NEW dates only
    with Session(engine) as session:
        statement = select(StockPrice).where(StockPrice.ticker == ticker_upper).order_by(StockPrice.price_date)
        existing_prices = session.exec(statement).all()
    
    # Build a set of existing dates to identify which dates are new
    existing_dates = {price.price_date for price in existing_prices}
    
    # Build a DataFrame with all data (existing + new) for moving average calculation
    # We need all historical data to correctly calculate MAs for new dates
    all_data = []
    
    # Add existing data (for MA calculation context)
    for existing_price in existing_prices:
        all_data.append({
            'date': existing_price.price_date,
            'close': float(existing_price.close_price)
        })
    
    # Identify new dates and add their data
    new_dates = []
    for idx, row in price_data.iterrows():
        # Convert index to date (handle timezone-aware timestamps)
        if isinstance(idx, pd.Timestamp):
            ts = idx
            # Convert to timezone-naive if needed
            if ts.tz is not None:
                ts = ts.tz_localize(None)
            price_date = ts.date()
        elif hasattr(idx, 'date'):
            price_date = idx.date()
        else:
            ts = pd.Timestamp(idx)
            if ts.tz is not None:
                ts = ts.tz_localize(None)
            price_date = ts.date()
        
        # Skip intraday data (only save daily data)
        if isinstance(idx, pd.Timestamp):
            ts = idx
            if ts.tz is not None:
                ts = ts.tz_localize(None)
            if ts.hour != 0:
                continue
        
        # Check if this date is new
        if price_date not in existing_dates:
            new_dates.append(price_date)
            all_data.append({
                'date': price_date,
                'close': float(row['Close'])
            })
    
    # Sort by date
    all_data.sort(key=lambda x: x['date'])
    
    # Create DataFrame for moving average calculation
    if all_data:
        ma_df = pd.DataFrame(all_data)
        ma_df.set_index('date', inplace=True)
        ma_df.sort_index(inplace=True)
        
        # Calculate moving averages
        ma_df['dma_50'] = ma_df['close'].rolling(window=50, min_periods=1).mean()
        ma_df['dma_200'] = ma_df['close'].rolling(window=200, min_periods=1).mean()
    else:
        ma_df = pd.DataFrame()
    
    # Now save/update only the new price data with moving averages
    # Existing records are NOT updated (immutable)
    with Session(engine) as session:
        for idx, row in price_data.iterrows():
            # Convert index to date (handle timezone-aware timestamps)
            if isinstance(idx, pd.Timestamp):
                ts = idx
                # Convert to timezone-naive if needed
                if ts.tz is not None:
                    ts = ts.tz_localize(None)
                price_date = ts.date()
            elif hasattr(idx, 'date'):
                price_date = idx.date()
            else:
                ts = pd.Timestamp(idx)
                if ts.tz is not None:
                    ts = ts.tz_localize(None)
                price_date = ts.date()
            
            # Skip intraday data (only save daily data)
            if isinstance(idx, pd.Timestamp):
                ts = idx
                if ts.tz is not None:
                    ts = ts.tz_localize(None)
                if ts.hour != 0:
                    continue
            
            # Extract OHLC values
            open_price = Decimal(str(row['Open'])).quantize(Decimal('0.0001'))
            close_price = Decimal(str(row['Close'])).quantize(Decimal('0.0001'))
            high_price = Decimal(str(row['High'])).quantize(Decimal('0.0001'))
            low_price = Decimal(str(row['Low'])).quantize(Decimal('0.0001'))
            
            # Check if record exists
            existing = session.get(StockPrice, (price_date, ticker_upper))
            
            if existing:
                # Update existing record - but ONLY update prices, NOT moving averages
                # Moving averages for past days are immutable
                existing.open_price = open_price
                existing.close_price = close_price
                existing.high_price = high_price
                existing.low_price = low_price
                # Do NOT update dma_50 and dma_200 for existing records
            else:
                # Create new record - calculate moving averages for new dates only
                dma_50 = None
                dma_200 = None
                if not ma_df.empty and price_date in ma_df.index:
                    dma_50_val = ma_df.loc[price_date, 'dma_50']
                    dma_200_val = ma_df.loc[price_date, 'dma_200']
                    if pd.notna(dma_50_val):
                        dma_50 = Decimal(str(dma_50_val)).quantize(Decimal('0.0001'))
                    if pd.notna(dma_200_val):
                        dma_200 = Decimal(str(dma_200_val)).quantize(Decimal('0.0001'))
                
                stock_price = StockPrice(
                    price_date=price_date,
                    ticker=ticker_upper,
                    open_price=open_price,
                    close_price=close_price,
                    high_price=high_price,
                    low_price=low_price,
                    dma_50=dma_50,
                    dma_200=dma_200
                )
                session.add(stock_price)
            
            # Track date range
            if earliest_date is None or price_date < earliest_date:
                earliest_date = price_date
            if latest_date is None or price_date > latest_date:
                latest_date = price_date
        
        session.commit()
        
        # Update watermark
        if earliest_date and latest_date:
            update_watermark(ticker_upper, earliest_date, latest_date)


def fetch_and_save_stock_prices(ticker: str) -> Tuple[pd.DataFrame, int]:
    """
    Fetch stock price data from yfinance and save to database.
    Uses watermark to determine what data to fetch.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Tuple of (DataFrame with fetched data, number of new records saved)
        
    Raises:
        ValueError: If ticker is invalid or data cannot be fetched
    """
    ticker_upper = ticker.upper()
    today = datetime.now().date()
    
    # Check watermark
    watermark = get_watermark(ticker_upper)
    
    if watermark is None:
        # No watermark - fetch 2 years of data
        start_date = datetime.now() - timedelta(days=730)
        end_date = datetime.now()
        fetch_intraday = False
    else:
        # Watermark exists - fetch data after latest_date
        if watermark.latest_date >= today:
            # Latest date is today - fetch only current prices (intraday)
            start_date = None
            end_date = None
            fetch_intraday = True
        else:
            # Fetch data from latest_date + 1 day to today
            start_date = datetime.combine(watermark.latest_date + timedelta(days=1), datetime.min.time())
            end_date = datetime.now()
            fetch_intraday = False
    
    try:
        stock = yf.Ticker(ticker_upper)
        
        if fetch_intraday:
            # Fetch only today's intraday data
            intraday = stock.history(period='1d', interval='1m')
            
            # Normalize index to timezone-naive if needed
            if not intraday.empty and intraday.index.tz is not None:
                intraday.index = intraday.index.tz_localize(None)
            
            if intraday.empty:
                # No intraday data, try daily data for today
                hist = stock.history(start=today, end=today + timedelta(days=1))
                if hist.empty:
                    return pd.DataFrame(), 0
                # Normalize index to timezone-naive if needed
                if hist.index.tz is not None:
                    hist.index = hist.index.tz_localize(None)
                price_data = hist
            else:
                # Aggregate intraday data into daily OHLC
                today_open = intraday['Open'].iloc[0]
                today_close = intraday['Close'].iloc[-1]
                today_high = intraday['High'].max()
                today_low = intraday['Low'].min()
                
                # Create a DataFrame with today's aggregated data (timezone-naive)
                price_data = pd.DataFrame([{
                    'Open': today_open,
                    'High': today_high,
                    'Low': today_low,
                    'Close': today_close,
                    'Volume': intraday['Volume'].sum()
                }], index=[pd.Timestamp(today).tz_localize(None)])
        else:
            # Fetch historical data
            hist = stock.history(start=start_date, end=end_date)
            
            if hist.empty:
                return pd.DataFrame(), 0
            
            # Normalize index to timezone-naive if needed
            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)
            
            # Try to fetch intraday data for today if available
            intraday_today = stock.history(period='1d', interval='1m')
            
            # Normalize index to timezone-naive if needed
            if not intraday_today.empty and intraday_today.index.tz is not None:
                intraday_today.index = intraday_today.index.tz_localize(None)
            
            if not intraday_today.empty:
                # Check if intraday data is for today
                # Handle timezone-aware and timezone-naive timestamps
                intraday_dates = set()
                for d in intraday_today.index:
                    ts = pd.Timestamp(d)
                    # Convert to timezone-naive if needed
                    if ts.tz is not None:
                        ts = ts.tz_localize(None)
                    intraday_dates.add(ts.date())
                
                if today in intraday_dates:
                    # Aggregate intraday data for today
                    today_open = intraday_today['Open'].iloc[0]
                    today_close = intraday_today['Close'].iloc[-1]
                    today_high = intraday_today['High'].max()
                    today_low = intraday_today['Low'].min()
                    
                    # Remove today's daily data from hist if it exists
                    # Normalize hist index to timezone-naive for comparison
                    hist_dates = []
                    for d in hist.index:
                        ts = pd.Timestamp(d)
                        if ts.tz is not None:
                            ts = ts.tz_localize(None)
                        hist_dates.append(ts.date())
                    
                    today_mask = [d == today for d in hist_dates]
                    if any(today_mask):
                        hist = hist[~pd.Series(today_mask, index=hist.index)]
                    
                    # Normalize hist index to timezone-naive before concatenating
                    if hist.index.tz is not None:
                        hist.index = hist.index.tz_localize(None)
                    
                    # Add aggregated today's data (timezone-naive)
                    today_df = pd.DataFrame([{
                        'Open': today_open,
                        'High': today_high,
                        'Low': today_low,
                        'Close': today_close,
                        'Volume': intraday_today['Volume'].sum()
                    }], index=[pd.Timestamp(today).tz_localize(None)])
                    price_data = pd.concat([hist, today_df]).sort_index()
                else:
                    price_data = hist
            else:
                price_data = hist
            
            # Ensure price_data index is timezone-naive
            if price_data.index.tz is not None:
                price_data.index = price_data.index.tz_localize(None)
        
        # Count records before saving
        records_before = 0
        if watermark:
            with Session(engine) as session:
                statement = select(StockPrice).where(StockPrice.ticker == ticker_upper)
                records_before = len(session.exec(statement).all())
        
        # Save to database
        save_stock_prices(ticker_upper, price_data)
        
        # Count records after saving
        with Session(engine) as session:
            statement = select(StockPrice).where(StockPrice.ticker == ticker_upper)
            records_after = len(session.exec(statement).all())
        
        new_records = records_after - records_before
        
        return price_data, new_records
        
    except Exception as e:
        raise ValueError(f"Error fetching data for {ticker}: {str(e)}")


def get_stock_prices_from_db(ticker: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> list:
    """
    Get stock prices from database.
    
    Args:
        ticker: Stock ticker symbol
        start_date: Optional start date filter
        end_date: Optional end date filter
        
    Returns:
        List of StockPrice objects
    """
    with Session(engine) as session:
        statement = select(StockPrice).where(StockPrice.ticker == ticker.upper())
        
        if start_date:
            statement = statement.where(StockPrice.price_date >= start_date)
        if end_date:
            statement = statement.where(StockPrice.price_date <= end_date)
        
        statement = statement.order_by(StockPrice.price_date.desc())
        
        prices = session.exec(statement).all()
        return list(prices)


def get_stock_prices_as_dataframe(ticker: str, start_date: Optional[date] = None, end_date: Optional[date] = None) -> pd.DataFrame:
    """
    Get stock prices from database as a pandas DataFrame.
    
    Args:
        ticker: Stock ticker symbol
        start_date: Optional start date filter
        end_date: Optional end date filter
        
    Returns:
        DataFrame with OHLC data and moving averages, indexed by date
    """
    prices = get_stock_prices_from_db(ticker, start_date, end_date)
    
    if not prices:
        return pd.DataFrame()
    
    # Build DataFrame from database records
    data = []
    for price in prices:
        data.append({
            'Open': float(price.open_price),
            'High': float(price.high_price),
            'Low': float(price.low_price),
            'Close': float(price.close_price),
            'dma_50': float(price.dma_50) if price.dma_50 else None,
            'dma_200': float(price.dma_200) if price.dma_200 else None
        })
    
    # Create DataFrame with date index
    dates = [price.price_date for price in prices]
    df = pd.DataFrame(data, index=pd.DatetimeIndex(dates))
    
    # Sort by date (ascending)
    df = df.sort_index()
    
    return df


def get_stock_metrics_from_db(ticker: str) -> Dict[str, Any]:
    """
    Get stock metrics from stock_price table.
    Calculates metrics based on stored price data.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Dictionary containing:
        - ticker: Stock ticker
        - sma_50: 50-day Simple Moving Average (from dma_50 field)
        - sma_200: 200-day Simple Moving Average (from dma_200 field)
        - devstep: Number of standard deviations from 50-day SMA
        - signal: Trading signal
        - current_price: Current stock price (latest close_price)
        - movement_5day_stddev: 5-day price movement in standard deviations
        - is_price_positive_5day: Whether price moved up in last 5 days
        - data_points: Number of data points
        
    Raises:
        ValueError: If no data found for ticker
    """
    # Get all price data from database
    prices = get_stock_prices_from_db(ticker)
    
    if not prices:
        raise ValueError(f"No price data found for ticker: {ticker}")
    
    # Sort by date (ascending)
    prices_sorted = sorted(prices, key=lambda p: p.price_date)
    
    # Get latest price data
    latest_price = prices_sorted[-1]
    current_price = float(latest_price.close_price)
    
    # Get SMA values from latest record
    sma_50 = float(latest_price.dma_50) if latest_price.dma_50 else None
    sma_200 = float(latest_price.dma_200) if latest_price.dma_200 else None
    
    # If SMAs are not available, calculate from close prices
    if sma_50 is None or sma_200 is None:
        close_prices = [float(p.close_price) for p in prices_sorted]
        if len(close_prices) >= 50:
            sma_50 = sum(close_prices[-50:]) / 50
        elif len(close_prices) > 0:
            sma_50 = sum(close_prices) / len(close_prices)
        
        if len(close_prices) >= 200:
            sma_200 = sum(close_prices[-200:]) / 200
        elif len(close_prices) > 0:
            sma_200 = sum(close_prices) / len(close_prices)
    
    # Calculate devstep (standard deviations from SMA 50)
    if sma_50 is not None:
        # Get last 50 close prices for std dev calculation
        recent_prices = [float(p.close_price) for p in prices_sorted[-50:]] if len(prices_sorted) >= 50 else [float(p.close_price) for p in prices_sorted]
        
        if len(recent_prices) > 1:
            std_dev = statistics.stdev(recent_prices)
            if std_dev > 0:
                devstep = (current_price - sma_50) / std_dev
            else:
                devstep = 0.0
        else:
            devstep = 0.0
    else:
        devstep = 0.0
    
    # Calculate signal
    from app.services.stock_service import calculate_signal
    signal = calculate_signal(devstep)
    
    # Calculate 5-day price movement
    movement_5day = 0.0
    is_price_positive = True
    
    if len(prices_sorted) >= 6:
        # Get price from 5 trading days ago (need at least 6 days: today + 5 days ago)
        price_5days_ago = float(prices_sorted[-6].close_price)
        price_change = current_price - price_5days_ago
        
        # Calculate std dev for conversion
        recent_prices = [float(p.close_price) for p in prices_sorted[-50:]] if len(prices_sorted) >= 50 else [float(p.close_price) for p in prices_sorted]
        if len(recent_prices) > 1:
            std_dev = statistics.stdev(recent_prices)
            if std_dev > 0:
                movement_5day = price_change / std_dev
            is_price_positive = price_change >= 0
    elif len(prices_sorted) >= 2:
        # Use first available price if less than 6 days
        price_earliest = float(prices_sorted[0].close_price)
        price_change = current_price - price_earliest
        is_price_positive = price_change >= 0
    
    # Fetch dividend yield from yfinance (still from yfinance)
    dividend_yield = None
    try:
        import yfinance as yf
        stock = yf.Ticker(ticker.upper())
        info = stock.info
        if 'dividendYield' in info and info['dividendYield'] is not None:
            raw_value = float(info['dividendYield'])
            as_percentage = raw_value * 100
            if as_percentage > 20:
                dividend_yield = raw_value
            else:
                dividend_yield = as_percentage
    except Exception:
        dividend_yield = None
    
    return {
        "ticker": ticker.upper(),
        "sma_50": round(sma_50, 2) if sma_50 is not None else None,
        "sma_200": round(sma_200, 2) if sma_200 is not None else None,
        "devstep": round(devstep, 4),
        "signal": signal,
        "current_price": round(current_price, 2),
        "dividend_yield": round(dividend_yield, 2) if dividend_yield is not None else None,
        "movement_5day_stddev": round(movement_5day, 4),
        "is_price_positive_5day": bool(is_price_positive),
        "data_points": len(prices)
    }
