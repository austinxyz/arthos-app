"""WatchList service for managing watchlists and watchlist stocks."""
from sqlmodel import Session, select
from app.database import engine
from app.models.watchlist import WatchList, WatchListStock
from app.models.stock_price import StockPrice
from app.services.ticker_validator import validate_ticker_list
from app.services.stock_service import get_multiple_stock_metrics
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
import logging

logger = logging.getLogger(__name__)


def validate_watchlist_name(name: str) -> bool:
    """
    Validate watchlist name (alphanumeric and spaces only, max 128 chars).
    
    Args:
        name: WatchList name to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not name or not name.strip():
        return False
    
    if len(name) > 128:
        return False
    
    # Allow alphanumeric and spaces only
    return all(c.isalnum() or c.isspace() for c in name)


def create_watchlist(watchlist_name: str, account_id: Optional[UUID] = None, description: Optional[str] = None) -> WatchList:
    """
    Create a new watchlist.
    
    Args:
        watchlist_name: Name of the watchlist
        account_id: Optional ID of the owner account
        description: Optional description of the watchlist
        
    Returns:
        The created WatchList object
        
    Raises:
        ValueError: If name is invalid, description is too long, or a watchlist with the same name already exists for the account.
    """
    if not validate_watchlist_name(watchlist_name):
        raise ValueError("WatchList name must be alphanumeric with spaces only, max 128 characters")
    
    if description is not None and len(description) > 265:
        raise ValueError("Description must be 265 characters or less")
    
    with Session(engine) as session:
        # Check if watchlist with same name exists for this account (or globally if public?)
        # Logic: If account_id provided, unique per account. If not, unique globally (for legacy/guest).
        
        statement = select(WatchList).where(WatchList.watchlist_name == watchlist_name.strip())
        if account_id:
            statement = statement.where(WatchList.account_id == account_id)
        else:
             statement = statement.where(WatchList.account_id == None)
             
        existing_watchlist = session.exec(statement).first()
        
        if existing_watchlist:
            raise ValueError(f"WatchList '{watchlist_name}' already exists")
            
        new_watchlist = WatchList(
            watchlist_name=watchlist_name.strip(), 
            description=description.strip() if description else None,
            account_id=account_id,
            date_added=datetime.now(),
            date_modified=datetime.now()
        )
        session.add(new_watchlist)
        session.commit()
        session.refresh(new_watchlist)
        return new_watchlist


def get_all_watchlists(account_id: Optional[UUID] = None) -> List[WatchList]:
    """
    Get all watchlists, optionally filtered by account_id.
    
    Args:
        account_id: Optional ID of the account to filter by
        
    Returns:
        List of WatchList objects
    """
    with Session(engine) as session:
        statement = select(WatchList)
        if account_id:
            statement = statement.where(WatchList.account_id == account_id)
        else:
            # If no account specified, maybe return only public ones or ones without owner?
            # Or for backward compatibility, all of them? 
            # Let's enforce: If no account_id, return only unowned watchlists (legacy)
            statement = statement.where(WatchList.account_id == None)
            
        statement = statement.order_by(WatchList.date_modified.desc())
        watchlists = session.exec(statement).all()
        return list(watchlists)


def get_watchlist(watchlist_id: UUID, account_id: Optional[UUID] = None) -> WatchList:
    """
    Get a watchlist by ID.
    
    Args:
        watchlist_id: WatchList UUID
        account_id: Optional ID of the requesting account to verify ownership
        
    Returns:
        WatchList object
        
    Raises:
        ValueError: If watchlist not found or access denied
    """
    with Session(engine) as session:
        watchlist = session.get(WatchList, watchlist_id)
        if not watchlist:
            raise ValueError(f"WatchList with ID {watchlist_id} not found")
        
        # Verify ownership if watchlist has an owner
        if watchlist.account_id:
            if not account_id or str(watchlist.account_id) != str(account_id):
                 raise ValueError(f"Access denied: WatchList with ID {watchlist_id} belongs to another account")
        return watchlist


def update_watchlist_name(watchlist_id: UUID, new_name: str, account_id: Optional[UUID] = None) -> WatchList:
    """
    Update watchlist name.
    
    Args:
        watchlist_id: WatchList UUID
        new_name: New watchlist name
        account_id: Optional ID of the requesting account to verify ownership
        
    Returns:
        Updated WatchList object
        
    Raises:
        ValueError: If name is invalid, watchlist not found, access denied, or new name already exists
    """
    if not validate_watchlist_name(new_name):
        raise ValueError("WatchList name must be alphanumeric with spaces only, max 128 characters")
    
    with Session(engine) as session:
        watchlist = session.get(WatchList, watchlist_id)
        if not watchlist:
            raise ValueError(f"WatchList with ID {watchlist_id} not found")
        
        # Verify ownership if watchlist has an owner
        if watchlist.account_id:
            if not account_id or watchlist.account_id != account_id:
                 raise ValueError(f"Access denied: WatchList with ID {watchlist_id} belongs to another account")
        
        # Check for duplicate name for the same account (or unowned)
        statement = select(WatchList).where(
            WatchList.watchlist_name == new_name.strip(),
            WatchList.watchlist_id != watchlist_id # Exclude current watchlist
        )
        if account_id:
            statement = statement.where(WatchList.account_id == account_id)
        else:
            statement = statement.where(WatchList.account_id == None)
        
        existing = session.exec(statement).first()
        if existing:
            raise ValueError(f"WatchList '{new_name}' already exists for this account")

        watchlist.watchlist_name = new_name.strip()
        watchlist.date_modified = datetime.now()
        session.add(watchlist)
        session.commit()
        session.refresh(watchlist)
        return watchlist


def update_watchlist(watchlist_id: UUID, watchlist_name: Optional[str] = None, description: Optional[str] = None, account_id: Optional[UUID] = None) -> Optional[WatchList]:
    """
    Update a watchlist's name and/or description.
    
    Args:
        watchlist_id: UUID of the watchlist
        watchlist_name: New name (optional)
        description: New description (optional)
        account_id: Optional ID of the requesting account to verify ownership
        
    Returns:
        Updated WatchList object or None if not found
        
    Raises:
        ValueError: If name or description is invalid, watchlist not found, access denied, or new name already exists
    """
    with Session(engine) as session:
        watchlist = session.get(WatchList, watchlist_id)
        if not watchlist:
            raise ValueError(f"WatchList with ID {watchlist_id} not found")
            
        # Verify ownership
        if watchlist.account_id:
            if not account_id or watchlist.account_id != account_id:
                raise ValueError("Access denied: You do not own this watchlist")
        
        if watchlist_name is not None:
            if not validate_watchlist_name(watchlist_name):
                raise ValueError("WatchList name must be alphanumeric with spaces only, max 128 characters")
            
            # Check for duplicates, excluding current watchlist
            statement = select(WatchList).where(WatchList.watchlist_name == watchlist_name.strip()).where(WatchList.watchlist_id != watchlist_id)
            if account_id:
                statement = statement.where(WatchList.account_id == account_id)
            else:
                statement = statement.where(WatchList.account_id == None)
                
            existing = session.exec(statement).first()
            if existing:
                raise ValueError(f"WatchList '{watchlist_name}' already exists")
            watchlist.watchlist_name = watchlist_name.strip()
            
        if description is not None:
            if len(description) > 265:
                raise ValueError("Description must be 265 characters or less")
            watchlist.description = description.strip() if description.strip() else None
             
        watchlist.date_modified = datetime.utcnow()
        session.add(watchlist)
        session.commit()
        session.refresh(watchlist)
        return watchlist


def delete_watchlist(watchlist_id: UUID, account_id: Optional[UUID] = None) -> bool:
    """
    Delete a watchlist and all its stocks (cascade delete).
    
    Args:
        watchlist_id: UUID of the watchlist
        account_id: Optional ID of the requesting account to verify ownership
        
    Returns:
        True if deleted successfully
        
    Raises:
        ValueError: If watchlist not found or access denied
    """
    with Session(engine) as session:
        watchlist = session.get(WatchList, watchlist_id)
        if not watchlist:
            raise ValueError(f"WatchList with ID {watchlist_id} not found")
            
        # Verify ownership
        if watchlist.account_id:
            if not account_id or watchlist.account_id != account_id:
                raise ValueError("Access denied: You do not own this watchlist")
            
        session.delete(watchlist)
        session.commit()
        return True


def add_stocks_to_watchlist(watchlist_id: UUID, tickers: List[str], account_id: Optional[UUID] = None) -> Tuple[List[WatchListStock], List[str]]:
    """
    Add stocks to a watchlist. Ignores duplicates and filters out invalid tickers.
    Validates both ticker format and that the ticker exists in the data provider.
    
    Args:
        watchlist_id: WatchList UUID
        tickers: List of stock ticker symbols
        account_id: Optional ID of the requesting account to verify ownership
        
    Returns:
        Tuple of (List of WatchListStock objects that were added, List of invalid tickers)
        
    Raises:
        ValueError: If watchlist not found or access denied
    """
    # Validate watchlist exists and ownership
    watchlist = get_watchlist(watchlist_id, account_id)
    
    # Validate ticker formats - filter out invalid ones instead of raising error
    valid_format_tickers, invalid_format_tickers = validate_ticker_list(tickers)
    
    # Now validate that tickers actually exist in the data provider and fetch/save price data
    from app.services.stock_service import fetch_stock_data
    from app.services.stock_price_service import fetch_and_save_stock_prices, compute_and_save_trading_metrics
    
    valid_tickers = []
    invalid_tickers = list(invalid_format_tickers)  # Start with format-invalid tickers
    
    for ticker in valid_format_tickers:
        ticker = ticker.upper()
        is_valid = False
        try:
            # Try to fetch data to verify ticker exists in the data provider
            # This will raise ValueError if ticker doesn't exist or has no data
            data = fetch_stock_data(ticker)
            # Double-check: data should not be None or empty, and should have required columns
            if data is None or len(data) == 0:
                logger.debug(f"Ticker {ticker} returned empty data, marking as invalid")
            elif 'Close' not in data.columns:
                logger.debug(f"Ticker {ticker} missing 'Close' column, marking as invalid")
            elif len(data) < 1:
                logger.debug(f"Ticker {ticker} has insufficient data points, marking as invalid")
            else:
                # Additional validation: check if Close prices are valid (not all NaN)
                if data['Close'].isna().all():
                    logger.debug(f"Ticker {ticker} has all NaN Close prices, marking as invalid")
                else:
                    logger.debug(f"Ticker {ticker} validated successfully, {len(data)} data points")
                    is_valid = True
                    valid_tickers.append(ticker)
                    
                    # Fetch and save stock price data to database
                    # This is the ONLY time we fetch data provider on demand (first time stock is added)
                    try:
                        price_data, new_records = fetch_and_save_stock_prices(ticker)
                        logger.info(f"Saved {new_records} new price records for {ticker}")
                        
                        # Calculate trading metrics immediately so UI shows correct signal
                        compute_and_save_trading_metrics(ticker)
                        logger.info(f"Computed trading metrics for {ticker}")
                    except Exception as e:
                        # Log error but don't fail the watchlist addition
                        logger.warning(f"Could not save price data for {ticker}: {e}")
        except ValueError as e:
            # ValueError is raised when ticker doesn't exist or has no data
            logger.debug(f"Ticker {ticker} failed data provider validation (ValueError): {e}")
        except Exception as e:
            # Catch any other exceptions (network errors, etc.) and treat as invalid
            logger.debug(f"Ticker {ticker} failed data provider validation (Exception): {e}")
        
        # If validation failed, add to invalid list
        if not is_valid:
            invalid_tickers.append(ticker)
    
    if not valid_tickers:
        return [], invalid_tickers
    
    with Session(engine) as session:
        added_stocks = []
        
        for ticker in valid_tickers:
            # Check if stock already exists in watchlist
            statement = select(WatchListStock).where(
                WatchListStock.watchlist_id == watchlist_id,
                WatchListStock.ticker == ticker
            )
            existing = session.exec(statement).first()
            
            if not existing:
                # Get current price as entry price
                entry_price = None
                try:
                    from app.services.stock_price_service import get_stock_attributes
                    from app.models.stock_price import StockPrice
                    from decimal import Decimal
                    
                    # Try to get latest close price from database
                    price_statement = select(StockPrice).where(
                        StockPrice.ticker == ticker.upper()
                    ).order_by(StockPrice.price_date.desc())
                    latest_price = session.exec(price_statement).first()
                    
                    if latest_price and latest_price.close_price:
                        entry_price = latest_price.close_price
                        logger.debug(f"Captured entry price {entry_price} for {ticker}")
                except Exception as e:
                    logger.warning(f"Could not capture entry price for {ticker}: {e}")
                
                # Add new stock with entry price
                watchlist_stock = WatchListStock(
                    watchlist_id=watchlist_id,
                    ticker=ticker,
                    date_added=datetime.now(),
                    entry_price=entry_price
                )
                session.add(watchlist_stock)
                added_stocks.append(watchlist_stock)
        
        # Update watchlist's date_modified
        watchlist.date_modified = datetime.now()
        session.add(watchlist)
        
        session.commit()
        
        # Refresh added stocks
        for stock in added_stocks:
            session.refresh(stock)
        
        return added_stocks, invalid_tickers


def remove_stock_from_watchlist(watchlist_id: UUID, ticker: str, account_id: Optional[UUID] = None) -> bool:
    """
    Remove a stock from a watchlist.
    
    Args:
        watchlist_id: WatchList UUID
        ticker: Stock ticker symbol
        account_id: Optional ID of the requesting account to verify ownership
        
    Returns:
        True if removed successfully
        
    Raises:
        ValueError: If watchlist or stock not found, or access denied
    """
    ticker = ticker.upper()
    
    with Session(engine) as session:
        # Verify watchlist exists and ownership
        watchlist = session.get(WatchList, watchlist_id)
        if not watchlist:
            raise ValueError(f"WatchList with ID {watchlist_id} not found")
            
        if watchlist.account_id:
            if not account_id or watchlist.account_id != account_id:
                 raise ValueError(f"Access denied: WatchList with ID {watchlist_id} belongs to another account")
        
        # Find and delete the stock
        statement = select(WatchListStock).where(
            WatchListStock.watchlist_id == watchlist_id,
            WatchListStock.ticker == ticker
        )
        watchlist_stock = session.exec(statement).first()
        
        if not watchlist_stock:
            raise ValueError(f"Stock {ticker} not found in watchlist {watchlist_id}")
        
        session.delete(watchlist_stock)
        
        # Update watchlist's date_modified
        watchlist.date_modified = datetime.now()
        session.add(watchlist)
        
        session.commit()
        return True


def get_watchlist_stocks(watchlist_id: UUID, account_id: Optional[UUID] = None, skip_auth: bool = False) -> List[WatchListStock]:
    """
    Get all stocks in a watchlist.
    
    NOTE: Auth is enforced at the watchlist level, not here. 
    The caller is responsible for verifying access to the watchlist before calling this function.
    
    Args:
        watchlist_id: WatchList UUID
        account_id: Deprecated - not used (kept for backward compatibility)
        skip_auth: Deprecated - not used (kept for backward compatibility)
        
    Returns:
        List of WatchListStock objects
    """
    with Session(engine) as session:
        statement = select(WatchListStock).where(
            WatchListStock.watchlist_id == watchlist_id
        ).order_by(WatchListStock.date_added.desc())
        stocks = session.exec(statement).all()
        return list(stocks)


def get_watchlist_stocks_with_metrics(watchlist_id: UUID, account_id: UUID = None, skip_auth: bool = False) -> List[Dict[str, Any]]:
    """
    Get all stocks in a watchlist with their current metrics.

    OPTIMIZED: Uses batch queries to fetch all data in 2-3 queries instead of 30-40.
    - Reads pre-computed devstep, signal, movement_5day_stddev from stock_attributes
    - Batch fetches latest stock_price for all tickers

    NOTE: Auth is enforced at the watchlist level, not here.
    The caller is responsible for verifying access to the watchlist before calling this function.

    Args:
        watchlist_id: WatchList UUID
        account_id: Deprecated - not used (kept for backward compatibility)
        skip_auth: Deprecated - not used (kept for backward compatibility)

    Returns:
        List of dictionaries containing stock metrics with all columns from stock_attributes
    """
    from app.models.stock_price import StockPrice, StockAttributes
    from sqlalchemy import func

    stocks = get_watchlist_stocks(watchlist_id)

    if not stocks:
        return []

    # Get list of all tickers
    tickers = [stock.ticker.upper() for stock in stocks]
    # Build entry_price lookup from watchlist stocks
    entry_price_lookup = {stock.ticker.upper(): float(stock.entry_price) if stock.entry_price else None for stock in stocks}

    with Session(engine) as session:
        # BATCH QUERY 1: Get all stock_attributes for tickers in watchlist
        attributes_statement = select(StockAttributes).where(StockAttributes.ticker.in_(tickers))
        attributes_list = session.exec(attributes_statement).all()
        attributes_lookup = {attr.ticker: attr for attr in attributes_list}

        # BATCH QUERY 2: Get latest stock_price for each ticker using subquery
        # This finds the max price_date for each ticker, then fetches those records
        subquery = (
            select(StockPrice.ticker, func.max(StockPrice.price_date).label('max_date'))
            .where(StockPrice.ticker.in_(tickers))
            .group_by(StockPrice.ticker)
            .subquery()
        )
        price_statement = (
            select(StockPrice)
            .join(subquery, (StockPrice.ticker == subquery.c.ticker) & (StockPrice.price_date == subquery.c.max_date))
        )
        price_list = session.exec(price_statement).all()
        price_lookup = {price.ticker: price for price in price_list}

    # Build metrics for each stock
    metrics_list = []

    for stock in stocks:
        ticker = stock.ticker.upper()
        attributes = attributes_lookup.get(ticker)
        current_price_record = price_lookup.get(ticker)

        # Handle missing data
        if not attributes:
            metrics_list.append({
                "ticker": ticker,
                "error": f"No stock attributes found for ticker: {ticker}"
            })
            continue

        if not current_price_record:
            metrics_list.append({
                "ticker": ticker,
                "error": f"No price data found for ticker: {ticker}"
            })
            continue

        # Get current price and entry price
        current_price = float(current_price_record.close_price)
        entry_price = entry_price_lookup.get(ticker)

        # Calculate change and percent change from entry price
        change = None
        percent_change = None
        if entry_price and entry_price > 0:
            change = current_price - entry_price
            percent_change = ((current_price - entry_price) / entry_price) * 100

        # Read pre-computed trading metrics from stock_attributes
        devstep = float(attributes.devstep) if attributes.devstep is not None else 0.0
        signal = attributes.signal if attributes.signal else "Neutral"
        movement_5day_stddev = float(attributes.movement_5day_stddev) if attributes.movement_5day_stddev is not None else 0.0

        # Determine if price movement is positive (for UI coloring)
        is_price_positive_5day = movement_5day_stddev >= 0

        metric = {
            "ticker": ticker,
            "current_price": current_price,
            "entry_price": entry_price,
            "change": change,
            "percent_change": percent_change,
            "sma_50": float(current_price_record.dma_50) if current_price_record.dma_50 else None,
            "sma_200": float(current_price_record.dma_200) if current_price_record.dma_200 else None,
            "dividend_amt": float(attributes.dividend_amt) if attributes.dividend_amt else None,
            "dividend_yield": float(attributes.dividend_yield) if attributes.dividend_yield else None,
            "next_earnings_date": attributes.next_earnings_date,
            "is_earnings_date_estimate": attributes.is_earnings_date_estimate,
            "next_dividend_date": attributes.next_dividend_date,
            "earliest_date": attributes.earliest_date.isoformat(),
            "latest_date": attributes.latest_date.isoformat(),
            # Use pre-computed metrics from stock_attributes
            "devstep": devstep,
            "signal": signal,
            "movement_5day_stddev": movement_5day_stddev,
            "is_price_positive_5day": is_price_positive_5day,
        }

        # Format numbers for display
        metric['current_price_formatted'] = f"${metric['current_price']:.2f}"
        metric['sma_50_formatted'] = f"${metric['sma_50']:.2f}" if metric['sma_50'] else "N/A"
        metric['sma_200_formatted'] = f"${metric['sma_200']:.2f}" if metric['sma_200'] else "N/A"
        metric['dividend_amt_formatted'] = f"${metric['dividend_amt']:.2f}" if metric['dividend_amt'] else "N/A"
        metric['stddev_50d_formatted'] = f"{metric['devstep']:.1f}"

        # Format dividend yield
        dividend_yield = metric.get('dividend_yield')
        if dividend_yield is not None and dividend_yield != '':
            try:
                metric['dividend_yield_formatted'] = f"{float(dividend_yield):.2f}%"
            except (ValueError, TypeError):
                metric['dividend_yield_formatted'] = "N/A"
        else:
            metric['dividend_yield_formatted'] = "N/A"

        # Format entry price, change, and percent change
        metric['entry_price_formatted'] = f"${metric['entry_price']:.2f}" if metric['entry_price'] else "N/A"

        if metric['change'] is not None:
            # Format with + sign for positive values
            sign = "+" if metric['change'] >= 0 else ""
            metric['change_formatted'] = f"{sign}${metric['change']:.2f}"
            metric['is_change_positive'] = metric['change'] >= 0
        else:
            metric['change_formatted'] = "N/A"
            metric['is_change_positive'] = None

        if metric['percent_change'] is not None:
            sign = "+" if metric['percent_change'] >= 0 else ""
            metric['percent_change_formatted'] = f"{sign}{metric['percent_change']:.2f}%"
            metric['is_percent_positive'] = metric['percent_change'] >= 0
        else:
            metric['percent_change_formatted'] = "N/A"
            metric['is_percent_positive'] = None

        # Format earnings date for display (yyyy-MM-dd format for proper text sorting)
        if metric.get('next_earnings_date'):
            earnings_date = metric['next_earnings_date']
            if isinstance(earnings_date, date):
                metric['next_earnings_date_formatted'] = earnings_date.strftime('%Y-%m-%d')
            else:
                metric['next_earnings_date_formatted'] = str(earnings_date)
        else:
            metric['next_earnings_date_formatted'] = None

        # Format dividend date for display (yyyy-MM-dd format for proper text sorting)
        if metric.get('next_dividend_date'):
            dividend_date = metric['next_dividend_date']
            if isinstance(dividend_date, date):
                metric['next_dividend_date_formatted'] = dividend_date.strftime('%Y-%m-%d')
            else:
                metric['next_dividend_date_formatted'] = str(dividend_date)
        else:
            metric['next_dividend_date_formatted'] = None

        metrics_list.append(metric)

    return metrics_list


def get_all_public_watchlists() -> List[WatchList]:
    """
    Get all public watchlists with account and stocks eagerly loaded.
    
    Returns:
        List of WatchList objects where is_public=True
    """
    from sqlalchemy.orm import selectinload
    
    with Session(engine) as session:
        statement = (
            select(WatchList)
            .where(WatchList.is_public == True)
            .options(selectinload(WatchList.account), selectinload(WatchList.stocks))
            .order_by(WatchList.date_modified.desc())
        )
        watchlists = session.exec(statement).all()
        return watchlists


def get_public_watchlist(watchlist_id: UUID) -> WatchList:
    """
    Get a public watchlist by ID. Does not require authentication.
    
    Args:
        watchlist_id: WatchList UUID
        
    Returns:
        WatchList object
        
    Raises:
        ValueError: If watchlist not found or is not public
    """
    from sqlalchemy.orm import selectinload
    
    with Session(engine) as session:
        statement = (
            select(WatchList)
            .where(
                WatchList.watchlist_id == watchlist_id,
                WatchList.is_public == True
            )
            .options(selectinload(WatchList.account))
        )
        watchlist = session.exec(statement).first()
        
        if not watchlist:
            raise ValueError(f"Public watchlist not found: {watchlist_id}")
        
        return watchlist


def update_watchlist_visibility(watchlist_id: UUID, is_public: bool, account_id: UUID) -> WatchList:
    """
    Update a watchlist's public/private visibility.
    
    Args:
        watchlist_id: UUID of the watchlist
        is_public: True to make public, False for private
        account_id: ID of the requesting account to verify ownership
        
    Returns:
        Updated WatchList object
        
    Raises:
        ValueError: If watchlist not found or access denied
    """
    # Verify ownership
    watchlist = get_watchlist(watchlist_id, account_id)
    
    with Session(engine) as session:
        # Re-fetch within session
        db_watchlist = session.get(WatchList, watchlist_id)
        if not db_watchlist:
            raise ValueError(f"Watchlist not found: {watchlist_id}")
        
        db_watchlist.is_public = is_public
        db_watchlist.date_modified = datetime.now()
        session.add(db_watchlist)
        session.commit()
        session.refresh(db_watchlist)
        
        return db_watchlist


def get_public_watchlist_stocks(watchlist_id: UUID) -> List[WatchListStock]:
    """
    Get all stocks in a PUBLIC watchlist (no auth required).
    
    Args:
        watchlist_id: WatchList UUID
        
    Returns:
        List of WatchListStock objects
        
    Raises:
        ValueError: If watchlist not found or is not public
    """
    # Verify it's a public watchlist
    watchlist = get_public_watchlist(watchlist_id)
    
    with Session(engine) as session:
        statement = select(WatchListStock).where(
            WatchListStock.watchlist_id == watchlist_id
        )
        stocks = session.exec(statement).all()
        return stocks


