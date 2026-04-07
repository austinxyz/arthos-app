"""Service for managing stock price data and attributes."""
import pandas as pd
import statistics
import logging
from sqlmodel import Session, select
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional, Tuple, Dict, Any
from zoneinfo import ZoneInfo
from app.database import engine
from app.models.stock_price import StockPrice, StockAttributes
from app.providers.factory import ProviderFactory
from app.providers.converters import stock_price_data_to_dataframe, aggregate_intraday_to_daily
from app.providers.exceptions import TickerNotFoundError, DataNotAvailableError

logger = logging.getLogger(__name__)

# Use Eastern Time for all date calculations (where the US stock market operates)
# This ensures consistent behavior regardless of server timezone (e.g., Railway uses UTC)
ET_TIMEZONE = ZoneInfo("America/New_York")


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


def save_stock_prices(ticker: str, price_data: pd.DataFrame, iv_data: Optional[Dict[date, float]] = None):
    """
    Save stock price data to database with moving averages and IV.
    Only saves daily data (not intraday).
    Calculates 50-day and 200-day moving averages based on close prices.
    
    Args:
        ticker: Stock ticker symbol
        price_data: DataFrame with OHLC data, indexed by date
        iv_data: Optional dictionary mapping date to IV value (percentage)
    """
    if price_data.empty:
        return
    
    ticker_upper = ticker.upper()
    today = datetime.now(ET_TIMEZONE).date()
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
            
            # Get IV for this date if available
            iv_value = None
            if iv_data and price_date in iv_data:
                iv_value = Decimal(str(round(iv_data[price_date], 4))).quantize(Decimal('0.0001'))
            
            # Check if record exists
            existing = session.get(StockPrice, (price_date, ticker_upper))
            
            if existing:
                # Update existing record - but ONLY update prices and IV, NOT moving averages
                # Moving averages for past days are immutable
                existing.open_price = open_price
                existing.close_price = close_price
                existing.high_price = high_price
                existing.low_price = low_price
                # Update IV if provided (allows updating IV for existing dates)
                if iv_value is not None:
                    existing.iv = iv_value
                # Do NOT update dma_50 and dma_200 for existing records
            else:
                # Create new record - calculate moving averages for new dates only
                dma_50 = None
                dma_200 = None
                if not ma_df.empty and price_date in ma_df.index:
                    # Use iloc[0] to handle potential duplicate dates and ensure we get a scalar
                    dma_50_val = ma_df.loc[price_date, 'dma_50']
                    dma_200_val = ma_df.loc[price_date, 'dma_200']
                    # Handle case where loc returns a Series (duplicates) vs scalar
                    if isinstance(dma_50_val, pd.Series):
                        dma_50_val = dma_50_val.iloc[-1]  # Take the last (most recent) value
                    if isinstance(dma_200_val, pd.Series):
                        dma_200_val = dma_200_val.iloc[-1]  # Take the last (most recent) value
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
                    dma_200=dma_200,
                    iv=iv_value
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


def purge_stock_prices(ticker: str) -> int:
    """
    Delete all stored price rows for a ticker and reset stock_attributes date range.

    Used before a full re-fetch (force refresh or split detected) so that all
    historical data is replaced with fresh split-adjusted values from the provider.

    Args:
        ticker: Stock ticker symbol

    Returns:
        Number of price rows deleted
    """
    ticker_upper = ticker.upper()
    with Session(engine) as session:
        rows = session.exec(select(StockPrice).where(StockPrice.ticker == ticker_upper)).all()
        count = len(rows)
        for row in rows:
            session.delete(row)

        # Reset date range on stock_attributes so fetch_and_save falls into the
        # "new stock" branch and re-fetches 2 years of history.
        attributes = session.get(StockAttributes, ticker_upper)
        if attributes:
            session.delete(attributes)

        session.commit()

    logger.info(f"Purged {count} price rows and stock_attributes for {ticker_upper}")
    return count


def check_for_splits(ticker: str, since_date: date) -> bool:
    """
    Check whether yfinance reports any stock splits for ticker after since_date.

    Args:
        ticker: Stock ticker symbol
        since_date: Only splits strictly after this date are considered

    Returns:
        True if at least one split occurred after since_date, False otherwise
    """
    try:
        import yfinance as yf
        splits = yf.Ticker(ticker.upper()).splits
        if splits is None or splits.empty:
            return False
        # splits index is tz-aware; normalise to date for comparison
        for split_ts in splits.index:
            split_date = split_ts.date() if hasattr(split_ts, 'date') else split_ts
            if split_date > since_date:
                logger.info(f"Split detected for {ticker}: ratio={splits[split_ts]:.4g} on {split_date}")
                return True
        return False
    except Exception as e:
        logger.warning(f"Could not check splits for {ticker}: {e}")
        return False


def fetch_and_save_stock_prices(
    ticker: str,
    include_options_iv: bool = True,
    force_purge: bool = False,
) -> Tuple[pd.DataFrame, int]:
    """
    Fetch stock price data from data provider and save to database.
    Also updates stock attributes (dividend_amt, dividend_yield).

    Process:
    1. If force_purge=True, or a stock split is detected since latest_date,
       purge all existing price rows so a full 2-year re-fetch is performed.
    2. Fetch historical data if there's a gap (today > latest_date + 1)
    3. Always fetch intraday data for today

    Args:
        ticker: Stock ticker symbol
        include_options_iv: If True, fetch options data to compute/update ATM IV metrics.
        force_purge: If True, delete all stored prices before fetching (used by Force
                     Refresh on the debug page to guarantee split-adjusted history).

    Returns:
        Tuple of (DataFrame with fetched data, number of new records saved)

    Raises:
        ValueError: If ticker is invalid or data cannot be fetched
    """
    ticker_upper = ticker.upper()
    today = datetime.now(ET_TIMEZONE).date()

    logger.info(f"="*60)
    logger.info(f"FETCH_AND_SAVE_STOCK_PRICES: Starting for {ticker_upper}")
    logger.info(f"  Today (ET): {today}, force_purge={force_purge}")
    logger.info(f"="*60)

    # Get data provider
    provider = ProviderFactory.get_default_provider()
    logger.debug(f"  Provider: {type(provider).__name__}")

    # Check stock attributes to determine if we have existing data
    attributes = get_stock_attributes(ticker_upper)
    if attributes:
        # Keep info logs concise; full model repr includes large insights payloads.
        logger.info("  Stock attributes found")
        logger.debug(f"  Stock attributes: {attributes}")
        logger.info(f"    - earliest_date: {attributes.earliest_date}")
        logger.info(f"    - latest_date: {attributes.latest_date}")
        logger.info(f"    - gap_days: {(today - attributes.latest_date).days}")
    else:
        logger.info("  Stock attributes: none")

    # ========================================================================
    # STEP 0: Purge existing data if requested or a split is detected
    # ========================================================================
    if attributes is not None:
        if force_purge:
            logger.info(f"  force_purge=True — purging all price data for {ticker_upper}")
            purge_stock_prices(ticker_upper)
            attributes = None  # treat as new stock so full history is re-fetched
        elif check_for_splits(ticker_upper, attributes.latest_date):
            logger.info(f"  Split detected — purging stale pre-split prices for {ticker_upper}")
            purge_stock_prices(ticker_upper)
            attributes = None

    all_price_data = []

    # ========================================================================
    # STEP 1: Fetch historical data if there's a gap
    # ========================================================================
    logger.info(f"--- STEP 1: Historical Data Fetch ---")

    if attributes is None:
        # New stock - fetch 2 years of historical data
        start_date = today - timedelta(days=730)
        end_date = today + timedelta(days=1)  # +1 because yfinance end is exclusive
        logger.info(f"  New stock - fetching 2 years of historical data")
        logger.info(f"  Date range: {start_date} to {end_date} (end is exclusive)")
        
        try:
            logger.debug(f"  Calling provider.fetch_historical_prices({ticker_upper}, {start_date}, {end_date})...")
            hist_data = provider.fetch_historical_prices(ticker_upper, start_date, end_date)
            logger.info(f"  Provider returned: {type(hist_data)}, len={len(hist_data) if hist_data else 0}")
            
            if hist_data is not None and len(hist_data) > 0:
                # Log first and last records
                logger.info(f"  First record date: {hist_data[0].date}")
                logger.info(f"  Last record date: {hist_data[-1].date}")
                all_price_data.extend(hist_data)
                logger.info(f"  ✓ Added {len(hist_data)} historical records to all_price_data")
            else:
                logger.warning(f"  ✗ No historical data returned (hist_data is None or empty)")
        except (TickerNotFoundError, DataNotAvailableError) as e:
            logger.warning(f"  ✗ Exception fetching historical data: {type(e).__name__}: {e}")
        except Exception as e:
            logger.error(f"  ✗ Unexpected exception fetching historical data: {type(e).__name__}: {e}")
            import traceback
            logger.error(f"  Traceback: {traceback.format_exc()}")
    
    elif (today - attributes.latest_date).days > 1:
        # Gap exists - fetch from latest_date + 1 to today
        gap_days = (today - attributes.latest_date).days
        logger.info(f"  Gap of {gap_days} days detected (latest_date: {attributes.latest_date})")
        
        start_date = attributes.latest_date + timedelta(days=1)
        logger.debug(f"  Initial start_date: {start_date} (weekday: {start_date.weekday()})")
        
        # Skip weekends: if start_date is Saturday (5) or Sunday (6), move to Monday
        while start_date.weekday() >= 5:
            logger.debug(f"  Skipping weekend day {start_date}")
            start_date += timedelta(days=1)
        logger.info(f"  After weekend skip, start_date: {start_date}")
        
        # Only fetch if start_date <= today
        if start_date <= today:
            end_date = today + timedelta(days=1)  # +1 because yfinance end is exclusive
            logger.info(f"  Date range: {start_date} to {end_date} (end is exclusive)")
            
            try:
                logger.debug(f"  Calling provider.fetch_historical_prices({ticker_upper}, {start_date}, {end_date})...")
                hist_data = provider.fetch_historical_prices(ticker_upper, start_date, end_date)
                logger.info(f"  Provider returned: {type(hist_data)}, len={len(hist_data) if hist_data else 0}")
                
                if hist_data is not None and len(hist_data) > 0:
                    logger.info(f"  First record date: {hist_data[0].date}")
                    logger.info(f"  Last record date: {hist_data[-1].date}")
                    all_price_data.extend(hist_data)
                    logger.info(f"  ✓ Added {len(hist_data)} historical records to all_price_data")
                else:
                    logger.warning(f"  ✗ No historical data returned (holidays/weekends)")
            except DataNotAvailableError as e:
                logger.warning(f"  ✗ DataNotAvailableError: {e}")
            except Exception as e:
                logger.error(f"  ✗ Unexpected exception: {type(e).__name__}: {e}")
                import traceback
                logger.error(f"  Traceback: {traceback.format_exc()}")
        else:
            logger.info(f"  Start date {start_date} > today {today}, skipping historical fetch")
    
    else:
        # No gap (latest_date is yesterday or today) - skip historical fetch
        logger.info(f"  No gap detected (latest_date: {attributes.latest_date}), skipping historical fetch")
    
    # ========================================================================
    # STEP 2: Always fetch intraday data for today
    # ========================================================================
    logger.info(f"--- STEP 2: Intraday Data Fetch ---")
    logger.info(f"  Fetching intraday data for today ({today})")
    
    try:
        logger.debug(f"  Calling provider.fetch_intraday_prices({ticker_upper}, {today})...")
        intraday_data = provider.fetch_intraday_prices(ticker_upper, today)
        logger.info(f"  Provider returned: {type(intraday_data)}, len={len(intraday_data) if intraday_data else 0}")
        
        if intraday_data is not None and len(intraday_data) > 0:
            logger.info(f"  First intraday record: date={intraday_data[0].date}")
            logger.info(f"  Last intraday record: date={intraday_data[-1].date}")
            
            # Aggregate intraday data into daily OHLC
            logger.debug(f"  Aggregating intraday data to daily OHLC...")
            daily_today = aggregate_intraday_to_daily(intraday_data)
            logger.info(f"  Aggregated: date={daily_today.date}, open={daily_today.open}, close={daily_today.close}")
            
            all_price_data.append(daily_today)
            logger.info(f"  ✓ Added aggregated intraday data to all_price_data")
        else:
            logger.warning(f"  ✗ No intraday data available (market may be closed)")
    except Exception as e:
        logger.error(f"  ✗ Exception fetching intraday data: {type(e).__name__}: {e}")
        import traceback
        logger.error(f"  Traceback: {traceback.format_exc()}")
    
    # ========================================================================
    # Combine and save data
    # ========================================================================
    logger.info(f"--- STEP 3: Combine and Save ---")
    logger.info(f"  all_price_data length: {len(all_price_data)}")
    
    if all_price_data:
        for i, pd_item in enumerate(all_price_data[:5]):  # Log first 5 items
            logger.debug(f"  all_price_data[{i}]: date={pd_item.date}, close={pd_item.close}")
        if len(all_price_data) > 5:
            logger.debug(f"  ... and {len(all_price_data) - 5} more items")
    
    if not all_price_data:
        logger.warning(f"  ✗ No price data to save for {ticker_upper}")
        # Even if no new data, ensure stock_attributes exists (for first-time entries)
        if attributes is None:
            logger.info(f"  Creating minimal stock_attributes entry")
            update_stock_attributes(ticker_upper, today, today)
        return pd.DataFrame(), 0
    
    # Convert to DataFrame
    logger.debug(f"  Converting to DataFrame...")
    price_data = stock_price_data_to_dataframe(all_price_data)
    logger.info(f"  DataFrame shape: {price_data.shape}")
    logger.info(f"  DataFrame index (dates): {list(price_data.index[:5])}...")
    logger.info(f"  DataFrame columns: {list(price_data.columns)}")
    
    # Calculate IV for today's date (if we have price data for today)
    iv_data = {}
    
    # Check if we're saving data for today
    price_dates = [pd.Timestamp(idx).date() if isinstance(idx, pd.Timestamp) else idx.date() for idx in price_data.index]
    if include_options_iv and today in price_dates:
        # Calculate IV from options data for today
        try:
            from app.services.stock_service import get_options_data
            from app.services.options_cache_service import calculate_atm_iv
            
            # Get current price from latest data
            current_price = float(price_data['Close'].iloc[-1]) if not price_data.empty else None
            
            if current_price:
                # Fetch options data (will use cache if available)
                options_expiration, options_data = get_options_data(ticker_upper, current_price)
                
                if options_data:
                    # Calculate ATM IV
                    atm_iv = calculate_atm_iv(options_data, current_price)
                    if atm_iv is not None:
                        iv_data[today] = atm_iv
                        logger.info(f"Calculated IV for {ticker_upper} on {today}: {atm_iv:.2f}%")
        except Exception as e:
            # Log but don't fail the price save if IV calculation fails
            logger.warning(f"Could not calculate IV for {ticker_upper} on {today}: {e}")
    elif not include_options_iv:
        logger.debug(f"Skipping options IV calculation for {ticker_upper} (include_options_iv=False)")
    
    # Count records before saving
    records_before = 0
    if attributes:
        with Session(engine) as session:
            statement = select(StockPrice).where(StockPrice.ticker == ticker_upper)
            records_before = len(session.exec(statement).all())
    
    # Save prices with IV data - this also updates latest_date in stock_attributes immediately
    save_stock_prices(ticker_upper, price_data, iv_data if iv_data else None)
    
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


def compute_and_save_trading_metrics(ticker: str) -> None:
    """
    Compute trading metrics (devstep, signal, movement_5day_stddev, stddev_50d) and save to stock_attributes.

    This function is called by the scheduler after price data is saved. It uses the
    existing calculation logic but stores the results in stock_attributes for fast
    watchlist queries.

    Args:
        ticker: Stock ticker symbol
    """
    ticker_upper = ticker.upper()

    # Get all price data from database
    prices = get_stock_prices_from_db(ticker_upper)

    if not prices or len(prices) < 2:
        logger.warning(f"Insufficient price data for {ticker_upper} to compute trading metrics")
        return

    # Sort by date (ascending)
    prices_sorted = sorted(prices, key=lambda p: p.price_date)

    # Get latest price data
    latest_price = prices_sorted[-1]
    current_price = float(latest_price.close_price)

    # Get SMA values from latest record
    sma_50 = float(latest_price.dma_50) if latest_price.dma_50 else None

    # If SMAs are not available, calculate from close prices
    if sma_50 is None:
        close_prices = [float(p.close_price) for p in prices_sorted]
        if len(close_prices) >= 50:
            sma_50 = sum(close_prices[-50:]) / 50
        elif len(close_prices) > 0:
            sma_50 = sum(close_prices) / len(close_prices)

    # Calculate std dev for the last 50 prices (or available prices)
    recent_prices = [float(p.close_price) for p in prices_sorted[-50:]] if len(prices_sorted) >= 50 else [float(p.close_price) for p in prices_sorted]

    stddev_50d = None
    devstep = 0.0

    if len(recent_prices) > 1:
        stddev_50d = statistics.stdev(recent_prices)
        if stddev_50d > 0 and sma_50 is not None:
            devstep = (current_price - sma_50) / stddev_50d

    # Calculate signal
    from app.services.stock_service import calculate_signal
    signal = calculate_signal(devstep)

    # Calculate 5-day price movement
    movement_5day_stddev = 0.0

    if len(prices_sorted) >= 6 and stddev_50d and stddev_50d > 0:
        # Get price from 5 trading days ago (need at least 6 days: today + 5 days ago)
        price_5days_ago = float(prices_sorted[-6].close_price)
        price_change = current_price - price_5days_ago
        movement_5day_stddev = price_change / stddev_50d

    # Save to stock_attributes
    with Session(engine) as session:
        attributes = session.get(StockAttributes, ticker_upper)

        if attributes:
            attributes.devstep = Decimal(str(round(devstep, 4))) if devstep is not None else None
            attributes.signal = signal
            attributes.movement_5day_stddev = Decimal(str(round(movement_5day_stddev, 4))) if movement_5day_stddev is not None else None
            attributes.stddev_50d = Decimal(str(round(stddev_50d, 4))) if stddev_50d is not None else None
            session.add(attributes)
            session.commit()
            logger.debug(f"Updated trading metrics for {ticker_upper}: devstep={devstep:.4f}, signal={signal}")
        else:
            logger.warning(f"No stock_attributes found for {ticker_upper}, cannot save trading metrics")


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
    
    # Get dividend yield, earnings date, dividend date, and IV metrics from stock_attributes table
    dividend_yield = None
    next_earnings_date = None
    is_earnings_date_estimate = None
    next_dividend_date = None
    current_iv = None
    iv_rank = None
    iv_percentile = None
    iv_high_52w = None
    iv_low_52w = None
    try:
        attributes = get_stock_attributes(ticker)
        if attributes:
            if attributes.dividend_yield is not None:
                dividend_yield = float(attributes.dividend_yield)
            next_earnings_date = attributes.next_earnings_date
            is_earnings_date_estimate = attributes.is_earnings_date_estimate
            next_dividend_date = attributes.next_dividend_date
            # IV metrics
            if attributes.current_iv is not None:
                current_iv = float(attributes.current_iv)
            if attributes.iv_rank is not None:
                iv_rank = float(attributes.iv_rank)
            if attributes.iv_percentile is not None:
                iv_percentile = float(attributes.iv_percentile)
            if attributes.iv_high_52w is not None:
                iv_high_52w = float(attributes.iv_high_52w)
            if attributes.iv_low_52w is not None:
                iv_low_52w = float(attributes.iv_low_52w)
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
        "data_points": len(prices),
        # IV metrics
        "current_iv": round(current_iv, 2) if current_iv is not None else None,
        "iv_rank": round(iv_rank, 1) if iv_rank is not None else None,
        "iv_percentile": round(iv_percentile, 1) if iv_percentile is not None else None,
        "iv_high_52w": round(iv_high_52w, 2) if iv_high_52w is not None else None,
        "iv_low_52w": round(iv_low_52w, 2) if iv_low_52w is not None else None
    }


def refresh_stock_data(
    ticker: str,
    clear_cache: bool = False,
    refresh_options_strategies: bool = True,
    include_options_iv: bool = True,
    force_purge: bool = False,
) -> Dict[str, Any]:
    """
    Unified function to refresh all stock data for a ticker.

    This is the single code path that should be called from:
    - Scheduler (background jobs)
    - Force Refresh (debug page and stock detail page)
    - On-demand cache population (when cache miss occurs)

    The function performs these steps in order:
    1. (Optional) Clear options cache for the ticker
    2. Fetch and save fresh stock price data (purging first if force_purge=True or
       a stock split is detected since the last stored date)
    3. Compute and save trading metrics (SMAs, signals, IV)
    4. Compute and cache option strategies (Risk Reversal, Covered Calls)

    Args:
        ticker: Stock ticker symbol
        clear_cache: If True, clears the options cache before fetching new data.
                     Use True for force refresh scenarios.
        refresh_options_strategies: If True, compute/cache RR and covered call strategies.
        include_options_iv: If True, compute/update ATM IV during price refresh.
        force_purge: If True, delete all stored price rows before re-fetching so the
                     full history is replaced with fresh split-adjusted data.

    Returns:
        Dict with refresh results:
        - ticker: Stock ticker
        - success: Whether the refresh completed successfully
        - price_records: Number of new price records added
        - current_price: Current stock price (if available)
        - rr_strategies: Number of Risk Reversal strategies cached
        - cc_strategies: Number of Covered Call strategies cached
        - error: Error message if failed (only present on failure)
    """
    ticker_upper = ticker.strip().upper()
    result = {
        "ticker": ticker_upper,
        "success": False,
        "price_records": 0,
        "current_price": None,
        "rr_strategies": 0,
        "cc_strategies": 0
    }

    try:
        # Step 1: Optionally clear options cache
        # Cache clear is only useful when we also refresh options strategies.
        if clear_cache and refresh_options_strategies:
            try:
                from app.services.options_cache_service import clear_options_cache
                clear_options_cache(ticker_upper)
                logger.debug(f"Cleared options cache for {ticker_upper}")
            except Exception as e:
                logger.warning(f"Could not clear options cache for {ticker_upper}: {e}")

        # Step 2: Fetch and save fresh stock price data
        try:
            # If we are refreshing options strategies in this same request, avoid a
            # separate IV-only options fetch here. We'll reuse one shared options
            # snapshot in Step 4 for IV + CC + RR.
            include_options_iv_on_price_fetch = include_options_iv and not refresh_options_strategies
            price_data, new_records = fetch_and_save_stock_prices(
                ticker_upper,
                include_options_iv=include_options_iv_on_price_fetch,
                force_purge=force_purge,
            )
            result["price_records"] = new_records

            if not price_data.empty:
                result["current_price"] = float(price_data['Close'].iloc[-1])
        except Exception as e:
            logger.error(f"Error fetching stock prices for {ticker_upper}: {e}")
            result["error"] = f"Failed to fetch stock prices: {str(e)}"
            return result

        # Step 3: Compute and save trading metrics
        try:
            compute_and_save_trading_metrics(ticker_upper)
        except Exception as e:
            logger.warning(f"Could not compute trading metrics for {ticker_upper}: {e}")

        # Step 4: Compute and cache option strategies
        current_price = result.get("current_price")
        shared_options_data = None

        need_shared_options_fetch = refresh_options_strategies
        if current_price and current_price > 0 and need_shared_options_fetch:
            try:
                from app.services.stock_service import get_all_options_data
                shared_options_data = get_all_options_data(
                    ticker=ticker_upper,
                    current_price=current_price,
                    days_limit=90,
                    include_leaps=refresh_options_strategies,
                    force_refresh=clear_cache
                )
            except Exception as e:
                logger.warning(f"Could not fetch shared options data for {ticker_upper}: {e}")

        if include_options_iv and current_price and current_price > 0:
            try:
                from app.services.options_cache_service import calculate_atm_iv, update_stock_iv_metrics
                if shared_options_data:
                    for _, options_data in shared_options_data:
                        if not options_data:
                            continue
                        atm_iv = calculate_atm_iv(options_data, current_price)
                        if atm_iv is not None:
                            update_stock_iv_metrics(ticker_upper, atm_iv)
                        break
            except Exception as e:
                logger.warning(f"Could not update IV metrics for {ticker_upper}: {e}")

        if refresh_options_strategies and current_price and current_price > 0:
            try:
                from app.services.options_strategy_cache_service import (
                    compute_and_cache_risk_reversals,
                    compute_and_cache_covered_calls
                )

                # Compute and cache Risk Reversal strategies
                try:
                    rr_count = compute_and_cache_risk_reversals(
                        ticker_upper,
                        current_price,
                        options_data_by_expiration=shared_options_data
                    )
                    result["rr_strategies"] = rr_count
                except Exception as e:
                    logger.warning(f"Could not compute/cache RR strategies for {ticker_upper}: {e}")

                # Compute and cache Covered Call strategies
                try:
                    cc_count = compute_and_cache_covered_calls(
                        ticker_upper,
                        current_price,
                        options_data_by_expiration=shared_options_data
                    )
                    result["cc_strategies"] = cc_count
                except Exception as e:
                    logger.warning(f"Could not compute/cache CC strategies for {ticker_upper}: {e}")

            except ImportError as e:
                logger.warning(f"Could not import options strategy cache service: {e}")
        else:
            logger.debug(
                f"Skipping option strategy caching for {ticker_upper}: "
                f"refresh_options_strategies={refresh_options_strategies}, current_price={current_price}"
            )

        result["success"] = True
        logger.info(f"Refreshed {ticker_upper}: {result['price_records']} prices, "
                    f"{result['rr_strategies']} RR, {result['cc_strategies']} CC")

        return result

    except Exception as e:
        logger.error(f"Error refreshing stock data for {ticker_upper}: {e}")
        result["error"] = str(e)
        return result
