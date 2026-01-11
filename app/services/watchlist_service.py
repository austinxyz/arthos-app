"""WatchList service for managing watchlists and watchlist stocks."""
from sqlmodel import Session, select
from app.database import engine
from app.models.watchlist import WatchList, WatchListStock
from app.models.stock_price import StockPrice
from app.services.ticker_validator import validate_ticker_list
from app.services.stock_service import get_multiple_stock_metrics
from datetime import datetime, date
from typing import List, Dict, Any
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


def add_stocks_to_watchlist(watchlist_id: UUID, tickers: List[str]) -> tuple[List[WatchListStock], List[str]]:
    """
    Add stocks to a watchlist. Ignores duplicates and filters out invalid tickers.
    Validates both ticker format and that the ticker exists in yfinance.
    
    Args:
        watchlist_id: WatchList UUID
        tickers: List of stock ticker symbols
        
    Returns:
        Tuple of (List of WatchListStock objects that were added, List of invalid tickers)
        
    Raises:
        ValueError: If watchlist not found
    """
    # Validate watchlist exists
    watchlist = get_watchlist(watchlist_id)
    
    # Validate ticker formats - filter out invalid ones instead of raising error
    valid_format_tickers, invalid_format_tickers = validate_ticker_list(tickers)
    
    # Now validate that tickers actually exist in yfinance and fetch/save price data
    from app.services.stock_service import fetch_stock_data
    from app.services.stock_price_service import fetch_and_save_stock_prices
    
    valid_tickers = []
    invalid_tickers = list(invalid_format_tickers)  # Start with format-invalid tickers
    
    for ticker in valid_format_tickers:
        ticker = ticker.upper()
        is_valid = False
        try:
            # Try to fetch data to verify ticker exists in yfinance
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
                    # This is the ONLY time we fetch yfinance on demand (first time stock is added)
                    try:
                        price_data, new_records = fetch_and_save_stock_prices(ticker)
                        logger.info(f"Saved {new_records} new price records for {ticker}")
                    except Exception as e:
                        # Log error but don't fail the watchlist addition
                        logger.warning(f"Could not save price data for {ticker}: {e}")
        except ValueError as e:
            # ValueError is raised when ticker doesn't exist or has no data
            logger.debug(f"Ticker {ticker} failed yfinance validation (ValueError): {e}")
        except Exception as e:
            # Catch any other exceptions (network errors, etc.) and treat as invalid
            logger.debug(f"Ticker {ticker} failed yfinance validation (Exception): {e}")
        
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
        
        return added_stocks, invalid_tickers


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
    Reads from stock_attributes table and current day's stock_price table (not from yfinance cache).
    Uses get_stock_metrics_from_db to calculate devstep, signal, and 5-day movement.
    
    Args:
        watchlist_id: WatchList UUID
        
    Returns:
        List of dictionaries containing stock metrics with all columns from stock_attributes
    """
    from app.services.stock_price_service import get_stock_attributes, get_stock_metrics_from_db
    from app.models.stock_price import StockPrice
    from datetime import date
    
    stocks = get_watchlist_stocks(watchlist_id)
    
    if not stocks:
        return []
    
    # Get metrics from stock_attributes and current day's stock_price for each ticker
    metrics_list = []
    today = date.today()
    
    for stock in stocks:
        ticker = stock.ticker
        try:
            # Get stock attributes (includes dividend_amt, dividend_yield, earliest_date, latest_date)
            attributes = get_stock_attributes(ticker)
            
            if not attributes:
                metrics_list.append({
                    "ticker": ticker,
                    "error": f"No stock attributes found for ticker: {ticker}"
                })
                continue
            
            # Get current day's stock price data
            with Session(engine) as session:
                statement = select(StockPrice).where(
                    StockPrice.ticker == ticker.upper(),
                    StockPrice.price_date == today
                )
                current_price_record = session.exec(statement).first()
                
                if not current_price_record:
                    # Try to get the latest available price
                    statement = select(StockPrice).where(
                        StockPrice.ticker == ticker.upper()
                    ).order_by(StockPrice.price_date.desc())
                    current_price_record = session.exec(statement).first()
                
                if not current_price_record:
                    metrics_list.append({
                        "ticker": ticker,
                        "error": f"No price data found for ticker: {ticker}"
                    })
                    continue
            
            # Get calculated metrics (devstep, signal, movement_5day_stddev, etc.) from database
            try:
                calculated_metrics = get_stock_metrics_from_db(ticker)
            except Exception as e:
                # If calculation fails, use defaults
                calculated_metrics = {
                    "devstep": 0.0,
                    "signal": "Neutral",
                    "movement_5day_stddev": 0.0,
                    "is_price_positive_5day": True
                }
            
            # Build metrics dictionary with all data from stock_attributes, current day's stock_price, and calculated metrics
            metric = {
                "ticker": ticker.upper(),
                "current_price": float(current_price_record.close_price),
                "sma_50": float(current_price_record.dma_50) if current_price_record.dma_50 else None,
                "sma_200": float(current_price_record.dma_200) if current_price_record.dma_200 else None,
                "dividend_amt": float(attributes.dividend_amt) if attributes.dividend_amt else None,
                "dividend_yield": float(attributes.dividend_yield) if attributes.dividend_yield else None,
                "next_earnings_date": attributes.next_earnings_date,
                "is_earnings_date_estimate": attributes.is_earnings_date_estimate,
                "earliest_date": attributes.earliest_date.isoformat(),
                "latest_date": attributes.latest_date.isoformat(),
                # Use calculated metrics for trading range widget
                "devstep": calculated_metrics.get("devstep", 0.0),
                "signal": calculated_metrics.get("signal", "Neutral"),
                "movement_5day_stddev": calculated_metrics.get("movement_5day_stddev", 0.0),
                "is_price_positive_5day": calculated_metrics.get("is_price_positive_5day", True),
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
            
            metrics_list.append(metric)
        except ValueError as e:
            # No price data found - add error entry
            metrics_list.append({
                "ticker": ticker,
                "error": str(e)
            })
        except Exception as e:
            # Other errors
            metrics_list.append({
                "ticker": ticker,
                "error": f"Error fetching metrics: {str(e)}"
            })
    
    return metrics_list

