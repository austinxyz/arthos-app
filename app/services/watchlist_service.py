"""WatchList service for managing watchlists and watchlist stocks."""
from sqlmodel import Session, select
from app.database import engine
from app.models.watchlist import WatchList, WatchListStock
from app.services.ticker_validator import validate_ticker_list
from app.services.stock_service import get_multiple_stock_metrics
from datetime import datetime
from typing import List, Dict, Any
from uuid import UUID


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


def create_watchlist(name: str) -> WatchList:
    """
    Create a new watchlist.
    
    Args:
        name: WatchList name
        
    Returns:
        Created WatchList object
        
    Raises:
        ValueError: If name is invalid
    """
    if not validate_watchlist_name(name):
        raise ValueError("WatchList name must be alphanumeric with spaces only, max 128 characters")
    
    with Session(engine) as session:
        watchlist = WatchList(
            watchlist_name=name.strip(),
            date_added=datetime.now(),
            date_modified=datetime.now()
        )
        session.add(watchlist)
        session.commit()
        session.refresh(watchlist)
        return watchlist


def get_all_watchlists() -> List[WatchList]:
    """
    Get all watchlists.
    
    Returns:
        List of all WatchList objects
    """
    with Session(engine) as session:
        statement = select(WatchList).order_by(WatchList.date_modified.desc())
        watchlists = session.exec(statement).all()
        return list(watchlists)


def get_watchlist(watchlist_id: UUID) -> WatchList:
    """
    Get a watchlist by ID.
    
    Args:
        watchlist_id: WatchList UUID
        
    Returns:
        WatchList object
        
    Raises:
        ValueError: If watchlist not found
    """
    with Session(engine) as session:
        watchlist = session.get(WatchList, watchlist_id)
        if not watchlist:
            raise ValueError(f"WatchList with ID {watchlist_id} not found")
        return watchlist


def update_watchlist_name(watchlist_id: UUID, new_name: str) -> WatchList:
    """
    Update watchlist name.
    
    Args:
        watchlist_id: WatchList UUID
        new_name: New watchlist name
        
    Returns:
        Updated WatchList object
        
    Raises:
        ValueError: If name is invalid or watchlist not found
    """
    if not validate_watchlist_name(new_name):
        raise ValueError("WatchList name must be alphanumeric with spaces only, max 128 characters")
    
    with Session(engine) as session:
        watchlist = session.get(WatchList, watchlist_id)
        if not watchlist:
            raise ValueError(f"WatchList with ID {watchlist_id} not found")
        
        watchlist.watchlist_name = new_name.strip()
        watchlist.date_modified = datetime.now()
        session.add(watchlist)
        session.commit()
        session.refresh(watchlist)
        return watchlist


def delete_watchlist(watchlist_id: UUID) -> bool:
    """
    Delete a watchlist and all its stocks (cascade delete).
    
    Args:
        watchlist_id: WatchList UUID
        
    Returns:
        True if deleted successfully
        
    Raises:
        ValueError: If watchlist not found
    """
    with Session(engine) as session:
        watchlist = session.get(WatchList, watchlist_id)
        if not watchlist:
            raise ValueError(f"WatchList with ID {watchlist_id} not found")
        
        session.delete(watchlist)
        session.commit()
        return True


def add_stocks_to_watchlist(watchlist_id: UUID, tickers: List[str]) -> List[WatchListStock]:
    """
    Add stocks to a watchlist. Ignores duplicates.
    
    Args:
        watchlist_id: WatchList UUID
        tickers: List of stock ticker symbols
        
    Returns:
        List of WatchListStock objects that were added (excluding duplicates)
        
    Raises:
        ValueError: If watchlist not found or tickers are invalid
    """
    # Validate watchlist exists
    watchlist = get_watchlist(watchlist_id)
    
    # Validate ticker formats
    valid_tickers, invalid_tickers = validate_ticker_list(tickers)
    
    if invalid_tickers:
        raise ValueError(f"Invalid ticker format(s): {', '.join(invalid_tickers)}")
    
    if not valid_tickers:
        return []
    
    with Session(engine) as session:
        added_stocks = []
        
        for ticker in valid_tickers:
            ticker = ticker.upper()
            
            # Check if stock already exists in watchlist
            statement = select(WatchListStock).where(
                WatchListStock.watchlist_id == watchlist_id,
                WatchListStock.ticker == ticker
            )
            existing = session.exec(statement).first()
            
            if not existing:
                # Add new stock
                watchlist_stock = WatchListStock(
                    watchlist_id=watchlist_id,
                    ticker=ticker,
                    date_added=datetime.now()
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
        
        return added_stocks


def remove_stock_from_watchlist(watchlist_id: UUID, ticker: str) -> bool:
    """
    Remove a stock from a watchlist.
    
    Args:
        watchlist_id: WatchList UUID
        ticker: Stock ticker symbol
        
    Returns:
        True if removed successfully
        
    Raises:
        ValueError: If watchlist or stock not found
    """
    ticker = ticker.upper()
    
    with Session(engine) as session:
        # Verify watchlist exists
        watchlist = session.get(WatchList, watchlist_id)
        if not watchlist:
            raise ValueError(f"WatchList with ID {watchlist_id} not found")
        
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


def get_watchlist_stocks(watchlist_id: UUID) -> List[WatchListStock]:
    """
    Get all stocks in a watchlist.
    
    Args:
        watchlist_id: WatchList UUID
        
    Returns:
        List of WatchListStock objects
        
    Raises:
        ValueError: If watchlist not found
    """
    # Verify watchlist exists
    get_watchlist(watchlist_id)
    
    with Session(engine) as session:
        statement = select(WatchListStock).where(
            WatchListStock.watchlist_id == watchlist_id
        ).order_by(WatchListStock.date_added.desc())
        stocks = session.exec(statement).all()
        return list(stocks)


def get_watchlist_stocks_with_metrics(watchlist_id: UUID) -> List[Dict[str, Any]]:
    """
    Get all stocks in a watchlist with their current metrics.
    
    Args:
        watchlist_id: WatchList UUID
        
    Returns:
        List of dictionaries containing stock metrics
    """
    stocks = get_watchlist_stocks(watchlist_id)
    
    if not stocks:
        return []
    
    # Get tickers
    tickers = [stock.ticker for stock in stocks]
    
    # Fetch metrics for all tickers
    metrics_list = get_multiple_stock_metrics(tickers)
    
    # Format numbers for display
    for metric in metrics_list:
        if 'error' not in metric:
            metric['current_price_formatted'] = f"${metric['current_price']:.2f}"
            metric['sma_50_formatted'] = f"${metric['sma_50']:.2f}"
            metric['sma_200_formatted'] = f"${metric['sma_200']:.2f}"
            metric['stddev_50d_formatted'] = f"{metric['devstep']:.1f}"
            # Always set dividend_yield_formatted, even if dividend_yield is missing or None
            dividend_yield = metric.get('dividend_yield')
            if dividend_yield is not None and dividend_yield != '':
                try:
                    metric['dividend_yield_formatted'] = f"{float(dividend_yield):.2f}%"
                except (ValueError, TypeError):
                    metric['dividend_yield_formatted'] = "N/A"
            else:
                metric['dividend_yield_formatted'] = "N/A"
    
    return metrics_list

