"""Scheduled job service for fetching stock data."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select
from app.database import engine
from app.models.watchlist import WatchListStock
from app.services.stock_price_service import fetch_and_save_stock_prices
from datetime import datetime, time
import pytz
import logging

logger = logging.getLogger(__name__)

# Global scheduler instance
scheduler = None

# Market hours: 9:30 AM ET - 4:00 PM ET
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0
ET_TIMEZONE = pytz.timezone('US/Eastern')


def is_market_open() -> bool:
    """
    Check if the market is currently open (9:30 AM ET - 4:00 PM ET).
    Market is closed on weekends.
    
    Returns:
        True if market is open, False otherwise
    """
    et_now = datetime.now(ET_TIMEZONE)
    
    # Market is closed on weekends
    if et_now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return False
    
    # Check if current time is within market hours
    current_time = et_now.time()
    market_open = time(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE)
    market_close = time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
    
    return market_open <= current_time < market_close


def fetch_all_watchlist_stocks():
    """
    Fetch stock price data for all unique tickers across all watchlists.
    This function is called by the scheduler during market hours or after market close.
    """
    try:
        # Check if market is open (unless this is the post-market update)
        et_now = datetime.now(ET_TIMEZONE)
        current_time = et_now.time()
        market_close = time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
        
        # Allow execution if market is open OR if it's the post-market update (4:00 PM - 4:05 PM)
        is_post_market = market_close <= current_time <= time(16, 5)
        
        if not is_market_open() and not is_post_market:
            logger.info("Market is closed. Skipping scheduled fetch.")
            return
        
        logger.info("Starting scheduled fetch for all watchlist stocks...")
        
        # Get all unique tickers from all watchlists
        with Session(engine) as session:
            statement = select(WatchListStock.ticker).distinct()
            tickers = session.exec(statement).all()
        
        unique_tickers = list(set([ticker.upper() for ticker in tickers]))
        
        logger.info(f"Found {len(unique_tickers)} unique tickers across all watchlists")
        
        success_count = 0
        error_count = 0
        
        for ticker in unique_tickers:
            try:
                logger.info(f"Fetching data for {ticker}...")
                fetch_and_save_stock_prices(ticker)
                success_count += 1
                logger.info(f"Successfully fetched data for {ticker}")
            except Exception as e:
                error_count += 1
                logger.error(f"Error fetching data for {ticker}: {str(e)}")
        
        logger.info(f"Scheduled fetch completed. Success: {success_count}, Errors: {error_count}")
        
    except Exception as e:
        logger.error(f"Error in scheduled fetch_all_watchlist_stocks: {str(e)}")


def start_scheduler():
    """
    Start the background scheduler to fetch stock data.
    - Runs every 60 minutes during market hours (9:30 AM ET - 4:00 PM ET)
    - Runs once after market close (4:00 PM ET)
    """
    global scheduler
    
    if scheduler is not None and scheduler.running:
        logger.warning("Scheduler is already running")
        return
    
    scheduler = BackgroundScheduler(timezone=ET_TIMEZONE)
    
    # Schedule the job to run every 60 minutes (only during market hours)
    scheduler.add_job(
        func=fetch_all_watchlist_stocks,
        trigger=IntervalTrigger(minutes=60),
        id='fetch_watchlist_stocks',
        name='Fetch stock data for all watchlist tickers (every 60 min during market hours)',
        replace_existing=True
    )
    
    # Schedule a post-market update at 4:00 PM ET
    scheduler.add_job(
        func=fetch_all_watchlist_stocks,
        trigger=CronTrigger(hour=16, minute=0, timezone=ET_TIMEZONE),
        id='fetch_watchlist_stocks_post_market',
        name='Fetch stock data after market close (4:00 PM ET)',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Scheduler started. Will fetch stock data every 60 minutes during market hours (9:30 AM - 4:00 PM ET) and once after market close (4:00 PM ET).")


def stop_scheduler():
    """Stop the background scheduler."""
    global scheduler
    
    if scheduler is not None and scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")
    else:
        logger.warning("Scheduler is not running")
