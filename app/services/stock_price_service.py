"""Service for managing stock price data and attributes."""
import pandas as pd
import statistics
import logging
from sqlmodel import Session, select
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
from app.database import engine
from app.models.stock_price import StockPrice, StockAttributes
from app.providers.factory import ProviderFactory
from app.providers.converters import stock_price_data_to_dataframe, aggregate_intraday_to_daily
from app.providers.exceptions import TickerNotFoundError, DataNotAvailableError

logger = logging.getLogger(__name__)


def get_stock_attributes(ticker: str) -> Optional[StockAttributes]:
    """
    Get stock attributes for a ticker.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        StockAttributes if exists, None otherwise
    """
    with Session(engine) as session:
        attributes = session.get(StockAttributes, ticker.upper())
        return attributes


def update_stock_attributes(ticker: str, earliest_date: date, latest_date: date, 
                           dividend_amt: Optional[Decimal] = None, 
                           dividend_yield: Optional[Decimal] = None,
                           current_price: Optional[float] = None,
                           next_earnings_date: Optional[date] = None,
                           is_earnings_date_estimate: Optional[bool] = None,
                           next_dividend_date: Optional[date] = None):
    """
    Create or update stock attributes for a ticker.
    
    Args:
        ticker: Stock ticker symbol
        earliest_date: Earliest date with data
        latest_date: Latest date with data
        dividend_amt: Annual dividend amount (optional)
        dividend_yield: Dividend yield as percentage (optional)
        current_price: Current stock price (used to calculate dividend_yield if not provided)
        next_earnings_date: Next earnings announcement date (optional)
        is_earnings_date_estimate: Whether the earnings date is an estimate (optional)
        next_dividend_date: Next ex-dividend date (optional)
    """
    with Session(engine) as session:
        ticker_upper = ticker.upper()
        attributes = session.get(StockAttributes, ticker_upper)
        
        if attributes:
            # Update existing attributes
            attributes.earliest_date = min(attributes.earliest_date, earliest_date)
            attributes.latest_date = max(attributes.latest_date, latest_date)
            if dividend_amt is not None:
                attributes.dividend_amt = dividend_amt
            if dividend_yield is not None:
                attributes.dividend_yield = dividend_yield
            elif dividend_amt is not None and current_price is not None and current_price > 0:
                # Calculate dividend yield if not provided but dividend_amt and current_price are available
                attributes.dividend_yield = Decimal(str((float(dividend_amt) / current_price) * 100)).quantize(Decimal('0.0001'))
            # Update earnings date if provided
            if next_earnings_date is not None:
                attributes.next_earnings_date = next_earnings_date
                attributes.is_earnings_date_estimate = is_earnings_date_estimate
            # Update dividend date if provided
            if next_dividend_date is not None:
                attributes.next_dividend_date = next_dividend_date
        else:
            # Create new attributes
            # Calculate dividend_yield if dividend_amt and current_price are provided but dividend_yield is not
            if dividend_yield is None and dividend_amt is not None and current_price is not None and current_price > 0:
                dividend_yield = Decimal(str((float(dividend_amt) / current_price) * 100)).quantize(Decimal('0.0001'))
            
            attributes = StockAttributes(
                ticker=ticker_upper,
                earliest_date=earliest_date,
                latest_date=latest_date,
                dividend_amt=dividend_amt,
                dividend_yield=dividend_yield,
                next_earnings_date=next_earnings_date,
                is_earnings_date_estimate=is_earnings_date_estimate,
                next_dividend_date=next_dividend_date
            )
            session.add(attributes)
        
        session.commit()
        session.refresh(attributes)


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
        
        # Update latest_date in stock_attributes immediately after saving prices
        # This ensures latest_date is always current, even if dividend fetch fails later
        if latest_date is not None:
            # Get or create stock_attributes
            with Session(engine) as session:
                attributes = session.get(StockAttributes, ticker_upper)
                if attributes:
                    # Update latest_date if we have newer data
                    if latest_date > attributes.latest_date:
                        attributes.latest_date = latest_date
                    # Update earliest_date if we have older data
                    if earliest_date and earliest_date < attributes.earliest_date:
                        attributes.earliest_date = earliest_date
                    session.add(attributes)
                    session.commit()
                # If attributes don't exist yet, they will be created by fetch_and_save_stock_prices
                # after dividend information is fetched


def fetch_and_save_stock_prices(ticker: str) -> Tuple[pd.DataFrame, int]:
    """
    Fetch stock price data from data provider and save to database.
    Also updates stock attributes (dividend_amt, dividend_yield).
    Uses stock attributes to determine what data to fetch.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        Tuple of (DataFrame with fetched data, number of new records saved)
        
    Raises:
        ValueError: If ticker is invalid or data cannot be fetched
    """
    ticker_upper = ticker.upper()
    today = datetime.now().date()
    
    # Get data provider
    provider = ProviderFactory.get_default_provider()
    
    # Check stock attributes
    attributes = get_stock_attributes(ticker_upper)
    
    if attributes is None:
        # No watermark - fetch 2 years of data
        start_date = today - timedelta(days=730)
        end_date = today
        fetch_intraday = False
    else:
        # Stock attributes exist - fetch data after latest_date
        days_since_latest = (today - attributes.latest_date).days
        
        if days_since_latest == 0:
            # Latest date is today - fetch only current prices (intraday)
            start_date = None
            end_date = None
            fetch_intraday = True
        elif days_since_latest < 0:
            # Latest date is in the future (shouldn't happen, but handle gracefully)
            logger.warning(f"Stock {ticker_upper} has latest_date {attributes.latest_date} in the future. Today is {today}. Skipping fetch.")
            return pd.DataFrame(), 0
        else:
            # Fetch data from latest_date + 1 day to today
            # If latest_date + 1 is today, try intraday first, otherwise fetch historical
            next_date = attributes.latest_date + timedelta(days=1)
            
            if next_date == today:
                # Next date is today - try intraday first, fallback to daily
                start_date = None
                end_date = None
                fetch_intraday = True
            else:
                # Fetch historical data from next_date to today
                start_date = next_date
                end_date = today
                fetch_intraday = False
    
    try:
        
        if fetch_intraday:
            # Fetch only today's intraday data
            logger.info(f"Fetching intraday data for {ticker_upper} for today ({today})")
            
            # Try intraday first (minute-by-minute data)
            intraday_data = provider.fetch_intraday_prices(ticker_upper, today)
            
            if intraday_data is None or len(intraday_data) == 0:
                # No intraday data, try daily aggregated data for today
                # Note: This only works after market closes and data is finalized
                try:
                    hist_data = provider.fetch_historical_prices(ticker_upper, today, today + timedelta(days=1))
                    if not hist_data:
                        # No daily data for today - market may be closed or it's a weekend/holiday
                        # Try fetching recent days (last 5 days) as fallback
                        if attributes and attributes.latest_date < today:
                            logger.info(f"No daily data for today ({today}), trying recent days for {ticker_upper}")
                            # Fetch last 5 days
                            recent_start = today - timedelta(days=5)
                            hist_data = provider.fetch_historical_prices(ticker_upper, recent_start, today + timedelta(days=1))
                            if hist_data:
                                # Filter to only dates after latest_date
                                hist_data = [p for p in hist_data if p.date > attributes.latest_date]
                                if not hist_data:
                                    logger.info(f"No new data available for {ticker_upper} (all data already in database)")
                                    return pd.DataFrame(), 0
                            else:
                                logger.info(f"No data available for {ticker_upper} today (market may be closed)")
                                return pd.DataFrame(), 0
                        else:
                            logger.info(f"No data available for {ticker_upper} today (market may be closed)")
                            return pd.DataFrame(), 0
                    
                    # Convert to DataFrame
                    price_data = stock_price_data_to_dataframe(hist_data)
                except (TickerNotFoundError, DataNotAvailableError) as e:
                    logger.info(f"No data available for {ticker_upper} today: {e}")
                    return pd.DataFrame(), 0
            else:
                # Aggregate intraday data into daily OHLC
                daily_data = aggregate_intraday_to_daily(intraday_data)
                price_data = stock_price_data_to_dataframe([daily_data])
        else:
            # Fetch historical data using start/end dates
            logger.info(f"Fetching historical data for {ticker_upper} from {start_date} to {end_date}")
            
            try:
                hist_data = provider.fetch_historical_prices(ticker_upper, start_date, end_date)
            except DataNotAvailableError:
                # No new data available for the requested range
                # If we're trying to fetch today's data and it's not available, try recent days as fallback
                if start_date == today and attributes and attributes.latest_date < today:
                    logger.info(f"No data for today ({today}) using date range, trying recent days for {ticker_upper}")
                    # Fetch last 5 days
                    recent_start = today - timedelta(days=5)
                    try:
                        hist_data = provider.fetch_historical_prices(ticker_upper, recent_start, end_date + timedelta(days=1))
                        if hist_data:
                            # Filter to only dates after latest_date
                            hist_data = [p for p in hist_data if p.date > attributes.latest_date]
                            if not hist_data:
                                logger.info(f"No new data available for {ticker_upper} (all data already in database)")
                                return pd.DataFrame(), 0
                        else:
                            logger.info(f"No new data available for {ticker_upper} from {start_date} to {end_date} (market may be closed or no updates)")
                            return pd.DataFrame(), 0
                    except (TickerNotFoundError, DataNotAvailableError):
                        logger.info(f"No new data available for {ticker_upper} from {start_date} to {end_date} (market may be closed or no updates)")
                        return pd.DataFrame(), 0
                else:
                    # No new data available - this is normal when:
                    # 1. Market is closed (evenings, weekends, holidays)
                    # 2. No new data since last fetch
                    logger.info(f"No new data available for {ticker_upper} from {start_date} to {end_date} (market may be closed or no updates)")
                    return pd.DataFrame(), 0
            
            # Convert to DataFrame
            price_data = stock_price_data_to_dataframe(hist_data)
            
            # Try to fetch intraday data for today if available
            intraday_today = provider.fetch_intraday_prices(ticker_upper, today)
            
            if intraday_today is not None and len(intraday_today) > 0:
                # Aggregate intraday data for today
                daily_today = aggregate_intraday_to_daily(intraday_today)
                today_df = stock_price_data_to_dataframe([daily_today])
                
                # Remove today's daily data from price_data if it exists
                if not price_data.empty:
                    price_data_dates = [pd.Timestamp(idx).date() if isinstance(idx, pd.Timestamp) else idx.date() for idx in price_data.index]
                    today_mask = [d == today for d in price_data_dates]
                    if any(today_mask):
                        price_data = price_data[~pd.Series(today_mask, index=price_data.index)]
                
                # Add aggregated today's data
                price_data = pd.concat([price_data, today_df]).sort_index()
        
        # Count records before saving
        records_before = 0
        if attributes:
            with Session(engine) as session:
                statement = select(StockPrice).where(StockPrice.ticker == ticker_upper)
                records_before = len(session.exec(statement).all())
        
        # Save to database - only proceed if we have data to save
        if price_data.empty:
            # No new data available - this is normal when:
            # 1. Market is closed (evenings, weekends, holidays)
            # 2. No new data since last fetch
            # 3. Date range is in the future
            logger.info(f"No new price data available for {ticker_upper} (this is normal when market is closed)")
            # Even if no new data, ensure stock_attributes exists (for first-time entries)
            if attributes is None:
                # Create minimal stock_attributes entry if it doesn't exist
                # This handles the case where validation passed but no data was available
                today = datetime.now().date()
                update_stock_attributes(ticker_upper, today, today)
            return pd.DataFrame(), 0
        
        # Save prices - this also updates latest_date in stock_attributes immediately
        save_stock_prices(ticker_upper, price_data)
        
        # Count records after saving
        with Session(engine) as session:
            statement = select(StockPrice).where(StockPrice.ticker == ticker_upper)
            records_after = len(session.exec(statement).all())
        
        new_records = records_after - records_before
        
        # Only create/update stock_attributes after successful data save
        # Get date range from saved prices
        price_dates = [pd.Timestamp(idx).date() if isinstance(idx, pd.Timestamp) else idx.date() for idx in price_data.index]
        earliest_date = min(price_dates)
        latest_date = max(price_dates)
        
        # If attributes exist, update date range to include existing data
        if attributes:
            earliest_date = min(attributes.earliest_date, earliest_date)
            latest_date = max(attributes.latest_date, latest_date)
        
        # Fetch and update dividend information from provider
        try:
            stock_info = provider.fetch_stock_info(ticker_upper)
            
            dividend_amt = None
            dividend_yield = None
            current_price = None
            next_earnings_date = None
            is_earnings_date_estimate = None
            next_dividend_date = None
            
            # Get current price from latest saved data or from provider
            if not price_data.empty:
                current_price = float(price_data['Close'].iloc[-1])
            else:
                current_price = stock_info.current_price
            
            # Get dividend amount
            if stock_info.dividend_amount is not None:
                dividend_amt = Decimal(str(stock_info.dividend_amount)).quantize(Decimal('0.0001'))
            
            # Get dividend yield
            if stock_info.dividend_yield is not None:
                dividend_yield = Decimal(str(stock_info.dividend_yield)).quantize(Decimal('0.0001'))
            elif dividend_amt is not None and current_price is not None and current_price > 0:
                # Calculate dividend yield from dividend amount and current price
                dividend_yield = Decimal(str((float(dividend_amt) / current_price) * 100)).quantize(Decimal('0.0001'))
            
            # Get earnings date (already converted to date by provider)
            next_earnings_date = stock_info.next_earnings_date
            is_earnings_date_estimate = stock_info.is_earnings_date_estimate
            
            # Get next dividend date (ex-dividend date)
            next_dividend_date = stock_info.next_dividend_date
            
            # Create or update stock attributes with all information (only after successful data save)
            update_stock_attributes(
                ticker_upper, 
                earliest_date, 
                latest_date,
                dividend_amt=dividend_amt,
                dividend_yield=dividend_yield,
                current_price=current_price,
                next_earnings_date=next_earnings_date,
                is_earnings_date_estimate=is_earnings_date_estimate,
                next_dividend_date=next_dividend_date
            )
        except Exception as e:
            # Log error but don't fail the price data save
            # Still create stock_attributes with date range even if dividend fetch fails
            logger.warning(f"Could not update dividend information for {ticker_upper}: {e}")
            update_stock_attributes(
                ticker_upper, 
                earliest_date, 
                latest_date
            )
        
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
    
    # Get dividend yield, earnings date, and dividend date from stock_attributes table (not from data provider)
    dividend_yield = None
    next_earnings_date = None
    is_earnings_date_estimate = None
    next_dividend_date = None
    try:
        attributes = get_stock_attributes(ticker)
        if attributes:
            if attributes.dividend_yield is not None:
                dividend_yield = float(attributes.dividend_yield)
            next_earnings_date = attributes.next_earnings_date
            is_earnings_date_estimate = attributes.is_earnings_date_estimate
            next_dividend_date = attributes.next_dividend_date
    except Exception:
        pass
    
    return {
        "ticker": ticker.upper(),
        "sma_50": round(sma_50, 2) if sma_50 is not None else None,
        "sma_200": round(sma_200, 2) if sma_200 is not None else None,
        "devstep": round(devstep, 4),
        "signal": signal,
        "current_price": round(current_price, 2),
        "dividend_yield": round(dividend_yield, 2) if dividend_yield is not None else None,
        "next_earnings_date": next_earnings_date,
        "is_earnings_date_estimate": is_earnings_date_estimate,
        "next_dividend_date": next_dividend_date,
        "movement_5day_stddev": round(movement_5day, 4),
        "is_price_positive_5day": bool(is_price_positive),
        "data_points": len(prices)
    }
