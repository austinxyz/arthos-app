"""Scheduled job service for fetching stock data."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select
from app.database import engine
from app.models.watchlist import WatchListStock
from app.models.scheduler_log import SchedulerLog
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
    Creates a log entry in scheduler_log table for tracking.
    """
    log_entry = None
    start_time = datetime.now()
    
    try:
        # Create log entry at start
        with Session(engine) as session:
            log_entry = SchedulerLog(
                start_time=start_time,
                end_time=None,
                notes=None
            )
            session.add(log_entry)
            session.commit()
            session.refresh(log_entry)
            log_id = log_entry.id
        
        # Check if market is open (unless this is the post-market update)
        et_now = datetime.now(ET_TIMEZONE)
        current_time = et_now.time()
        market_close = time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
        
        # Allow execution if market is open OR if it's the post-market update (4:00 PM - 4:05 PM)
        is_post_market = market_close <= current_time <= time(16, 5)
        
        if not is_market_open() and not is_post_market:
            logger.info("Market is closed. Skipping scheduled fetch.")
            # Update log entry
            with Session(engine) as session:
                log_entry = session.get(SchedulerLog, log_id)
                if log_entry:
                    log_entry.end_time = datetime.now()
                    log_entry.notes = "Market is closed. Skipped fetch."
                    session.add(log_entry)
                    session.commit()
            return
        
        logger.info("Starting scheduled fetch for all watchlist stocks...")
        logger.info(f"Current ET time: {et_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"Market open check: {is_market_open()}, Post-market check: {is_post_market}")
        
        # Get all unique tickers from all watchlists
        with Session(engine) as session:
            statement = select(WatchListStock.ticker).distinct()
            tickers = session.exec(statement).all()
        
        unique_tickers = list(set([ticker.upper() for ticker in tickers]))
        
        if not unique_tickers:
            logger.info("No tickers found in watchlists. Skipping fetch.")
            # Update log entry
            end_time = datetime.now()
            with Session(engine) as session:
                log_entry = session.get(SchedulerLog, log_id)
                if log_entry:
                    log_entry.end_time = end_time
                    log_entry.notes = "No tickers found in watchlists. Skipped fetch."
                    session.add(log_entry)
                    session.commit()
            return
        
        logger.info(f"Found {len(unique_tickers)} unique tickers across all watchlists")
        
        success_count = 0
        error_count = 0
        
        for ticker in unique_tickers:
            try:
                logger.info(f"Fetching data for {ticker}...")
                price_data, new_records = fetch_and_save_stock_prices(ticker)
                
                if new_records > 0:
                    success_count += 1
                    logger.info(f"Successfully fetched and saved {new_records} new record(s) for {ticker}")
                else:
                    # No new records - this is normal when market is closed or no updates available
                    success_count += 1
                    logger.info(f"No new data available for {ticker} (market may be closed or no updates)")
            except ValueError as e:
                # ValueError indicates a real problem (invalid ticker, network error, etc.)
                error_count += 1
                logger.error(f"Error fetching data for {ticker}: {str(e)}")
            except Exception as e:
                # Other exceptions (unexpected errors)
                error_count += 1
                logger.error(f"Unexpected error fetching data for {ticker}: {str(e)}")
        
        logger.info(f"Scheduled fetch completed. Success: {success_count}, Errors: {error_count}")
        
        # Update log entry with completion info
        end_time = datetime.now()
        notes = f"Fetched data for {len(unique_tickers)} stock(s). Success: {success_count}, Errors: {error_count}"
        
        with Session(engine) as session:
            log_entry = session.get(SchedulerLog, log_id)
            if log_entry:
                log_entry.end_time = end_time
                log_entry.notes = notes
                session.add(log_entry)
                session.commit()
        
    except Exception as e:
        logger.error(f"Error in scheduled fetch_all_watchlist_stocks: {str(e)}")
        
        # Update log entry with error info
        if 'log_id' in locals() and log_id:
            try:
                end_time = datetime.now()
                with Session(engine) as session:
                    log_entry = session.get(SchedulerLog, log_id)
                    if log_entry:
                        log_entry.end_time = end_time
                        log_entry.notes = f"Error: {str(e)}"
                        session.add(log_entry)
                        session.commit()
            except Exception as log_error:
                logger.error(f"Error updating log entry: {str(log_error)}")


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
    
    # Schedule the job to run every 60 minutes
    # The fetch_all_watchlist_stocks function will check market hours internally
    # This ensures it runs every hour, refreshing today's data during market hours
    scheduler.add_job(
        func=fetch_all_watchlist_stocks,
        trigger=IntervalTrigger(minutes=60),
        id='fetch_watchlist_stocks',
        name='Fetch stock data for all watchlist tickers (every 60 min, refreshes today during market hours)',
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


def fetch_all_watchlist_stocks_manual(bypass_market_hours: bool = False):
    """
    Manually trigger fetch for all watchlist stocks.
    This function bypasses market hours check if bypass_market_hours is True.
    Useful for testing and manual triggers.
    
    Args:
        bypass_market_hours: If True, skip market hours check and run regardless of market status
    """
    log_entry = None
    start_time = datetime.now()
    
    try:
        # Create log entry at start
        with Session(engine) as session:
            log_entry = SchedulerLog(
                start_time=start_time,
                end_time=None,
                notes=None
            )
            session.add(log_entry)
            session.commit()
            session.refresh(log_entry)
            log_id = log_entry.id
        
        # Check if market is open (unless bypassing)
        if not bypass_market_hours:
            et_now = datetime.now(ET_TIMEZONE)
            current_time = et_now.time()
            market_close = time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
            
            # Allow execution if market is open OR if it's the post-market update (4:00 PM - 4:05 PM)
            is_post_market = market_close <= current_time <= time(16, 5)
            
            if not is_market_open() and not is_post_market:
                logger.info("Market is closed. Skipping scheduled fetch.")
                # Update log entry
                with Session(engine) as session:
                    log_entry = session.get(SchedulerLog, log_id)
                    if log_entry:
                        log_entry.end_time = datetime.now()
                        log_entry.notes = "Market is closed. Skipped fetch."
                        session.add(log_entry)
                        session.commit()
                return log_id
        
        et_now = datetime.now(ET_TIMEZONE)
        logger.info("Starting manual fetch for all watchlist stocks...")
        logger.info(f"Current ET time: {et_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"Bypass market hours: {bypass_market_hours}")
        if not bypass_market_hours:
            logger.info(f"Market open check: {is_market_open()}")
        
        # Get all unique tickers from all watchlists
        with Session(engine) as session:
            statement = select(WatchListStock.ticker).distinct()
            tickers = session.exec(statement).all()
        
        unique_tickers = list(set([ticker.upper() for ticker in tickers]))
        
        if not unique_tickers:
            logger.info("No tickers found in watchlists. Skipping fetch.")
            # Update log entry
            end_time = datetime.now()
            with Session(engine) as session:
                log_entry = session.get(SchedulerLog, log_id)
                if log_entry:
                    log_entry.end_time = end_time
                    log_entry.notes = "No tickers found in watchlists. Skipped fetch."
                    session.add(log_entry)
                    session.commit()
            return log_id
        
        logger.info(f"Found {len(unique_tickers)} unique tickers across all watchlists")
        
        success_count = 0
        error_count = 0
        
        for ticker in unique_tickers:
            try:
                logger.info(f"Fetching data for {ticker}...")
                price_data, new_records = fetch_and_save_stock_prices(ticker)
                
                if new_records > 0:
                    success_count += 1
                    logger.info(f"Successfully fetched and saved {new_records} new record(s) for {ticker}")
                else:
                    # No new records - this is normal when market is closed or no updates available
                    success_count += 1
                    logger.info(f"No new data available for {ticker} (market may be closed or no updates)")
            except ValueError as e:
                # ValueError indicates a real problem (invalid ticker, network error, etc.)
                error_count += 1
                logger.error(f"Error fetching data for {ticker}: {str(e)}")
            except Exception as e:
                # Other exceptions (unexpected errors)
                error_count += 1
                logger.error(f"Unexpected error fetching data for {ticker}: {str(e)}")
        
        logger.info(f"Manual fetch completed. Success: {success_count}, Errors: {error_count}")
        
        # Update log entry with completion info
        end_time = datetime.now()
        notes = f"Manual fetch: {len(unique_tickers)} stock(s). Success: {success_count}, Errors: {error_count}"
        
        with Session(engine) as session:
            log_entry = session.get(SchedulerLog, log_id)
            if log_entry:
                log_entry.end_time = end_time
                log_entry.notes = notes
                session.add(log_entry)
                session.commit()
        
        return log_id
        
    except Exception as e:
        logger.error(f"Error in manual fetch_all_watchlist_stocks: {str(e)}")
        
        # Update log entry with error info
        if 'log_id' in locals() and log_id:
            try:
                end_time = datetime.now()
                with Session(engine) as session:
                    log_entry = session.get(SchedulerLog, log_id)
                    if log_entry:
                        log_entry.end_time = end_time
                        log_entry.notes = f"Manual fetch error: {str(e)}"
                        session.add(log_entry)
                        session.commit()
            except Exception as log_error:
                logger.error(f"Error updating log entry: {str(log_error)}")
        
        raise
