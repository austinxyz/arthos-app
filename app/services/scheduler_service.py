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
    
    # Schedule RR history update job (every hour during market hours + 60 mins after close)
    scheduler.add_job(
        func=update_rr_history,
        trigger=IntervalTrigger(minutes=60),
        id='update_rr_history',
        name='Update RR history (every 60 min, during market hours + 60 mins after close)',
        replace_existing=True
    )
    
    scheduler.start()
    logger.info("Scheduler started. Will fetch stock data every 60 minutes during market hours (9:30 AM - 4:00 PM ET) and once after market close (4:00 PM ET).")
    logger.info("RR history update job scheduled to run every 60 minutes during market hours + 60 mins after close.")


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


def update_rr_history():
    """
    Update Risk Reversal history by recalculating net cost for all active entries.
    Runs every hour during market hours + 60 mins after market close.
    Filters out expired entries (expired_yn = 'N').
    Creates a log entry in rr_history_log table for tracking.
    """
    from app.models.rr_watchlist import RRWatchlist, RRHistory
    from app.models.rr_history_log import RRHistoryLog
    from app.services.rr_watchlist_service import get_all_rr_watchlist_entries
    import yfinance as yf
    import pandas as pd
    from decimal import Decimal
    
    log_entry = None
    start_time = datetime.now()
    
    try:
        # Create log entry at start
        with Session(engine) as session:
            log_entry = RRHistoryLog(
                start_time=start_time,
                end_time=None,
                notes=None
            )
            session.add(log_entry)
            session.commit()
            session.refresh(log_entry)
            log_id = log_entry.id
        
        # Check if we should run (market hours or within 60 mins after close)
        et_now = datetime.now(ET_TIMEZONE)
        current_time = et_now.time()
        market_close = time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
        post_market_end = time(17, 0)  # 5:00 PM ET (60 mins after 4:00 PM close)
        
        # Allow execution if market is open OR if it's within 60 mins after market close
        is_post_market_window = market_close <= current_time <= post_market_end
        
        if not is_market_open() and not is_post_market_window:
            logger.debug("Outside market hours and post-market window. Skipping RR history update.")
            # Update log entry
            with Session(engine) as session:
                log_entry = session.get(RRHistoryLog, log_id)
                if log_entry:
                    log_entry.end_time = datetime.now()
                    log_entry.notes = "Outside market hours and post-market window. Skipped update."
                    session.add(log_entry)
                    session.commit()
            return
        
        logger.info("Starting RR history update...")
    
    except Exception as e:
        logger.error(f"Error creating RR history log entry: {str(e)}")
        # Continue without logging if log creation fails
    
    try:
        # Get all non-expired entries
        all_entries = get_all_rr_watchlist_entries()
        active_entries = [e for e in all_entries if e.expired_yn == 'N']
        
        if not active_entries:
            logger.info("No active RR entries to update")
            return
        
        logger.info(f"Found {len(active_entries)} active RR entries to update")
        
        today = datetime.now().date()
        success_count = 0
        error_count = 0
        expired_count = 0
        
        for entry in active_entries:
            try:
                # Check if expired
                if entry.expiration < today:
                    # Mark as expired
                    with Session(engine) as session:
                        db_entry = session.get(RRWatchlist, entry.id)
                        if db_entry:
                            db_entry.expired_yn = 'Y'
                            session.add(db_entry)
                            session.commit()
                    expired_count += 1
                    logger.info(f"Marked RR entry {entry.id} as expired (expiration: {entry.expiration})")
                    continue
                
                # Fetch fresh quotes from yfinance
                stock = yf.Ticker(entry.ticker)
                expiration_str = entry.expiration.strftime('%Y-%m-%d')
                opt_chain = stock.option_chain(expiration_str)
                
                # Get put option data
                puts = opt_chain.puts
                put_row = puts[puts['strike'] == float(entry.put_strike)]
                
                if put_row.empty:
                    logger.warning(f"Put option with strike ${entry.put_strike} not found for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                put_row = put_row.iloc[0]
                put_bid = put_row.get('bid')
                put_ask = put_row.get('ask')
                
                if pd.isna(put_bid) or pd.isna(put_ask) or put_bid <= 0 or put_ask <= 0:
                    logger.warning(f"Put option with strike ${entry.put_strike} has missing or invalid bid/ask for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                # Get call option data
                calls = opt_chain.calls
                call_row = calls[calls['strike'] == float(entry.call_strike)]
                
                if call_row.empty:
                    logger.warning(f"Call option with strike ${entry.call_strike} not found for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                call_row = call_row.iloc[0]
                call_bid = call_row.get('bid')
                call_ask = call_row.get('ask')
                
                if pd.isna(call_bid) or pd.isna(call_ask) or call_bid <= 0 or call_ask <= 0:
                    logger.warning(f"Call option with strike ${entry.call_strike} has missing or invalid bid/ask for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                # Calculate average of bid/ask for both options
                put_option_quote = (float(put_bid) + float(put_ask)) / 2.0
                call_option_quote = (float(call_bid) + float(call_ask)) / 2.0
                
                # Calculate current value using average of bid/ask for consistency
                # For risk reversal: we receive put premium, pay call premium
                # Current value = (call_option_quote * call_quantity) - (put_option_quote * put_quantity)
                curr_value = (call_option_quote * entry.call_quantity) - (put_option_quote * entry.put_quantity)
                
                # Store the prices used in calculation (average of bid/ask)
                call_price = Decimal(str(call_option_quote))
                put_price = Decimal(str(put_option_quote))
                
                # Check if history entry already exists for today
                with Session(engine) as session:
                    existing = session.exec(
                        select(RRHistory).where(
                            RRHistory.rr_uuid == entry.id,
                            RRHistory.history_date == today
                        )
                    ).first()
                    
                    if existing:
                        # Update existing entry
                        existing.curr_value = Decimal(str(curr_value))
                        existing.call_price = call_price
                        existing.put_price = put_price
                        session.add(existing)
                    else:
                        # Create new history entry
                        history_entry = RRHistory(
                            rr_uuid=entry.id,
                            ticker=entry.ticker,
                            history_date=today,
                            curr_value=Decimal(str(curr_value)),
                            call_price=call_price,
                            put_price=put_price
                        )
                        session.add(history_entry)
                    
                    session.commit()
                    success_count += 1
                    logger.debug(f"Updated RR history for {entry.ticker} {expiration_str} - Current Value: ${curr_value:.2f}")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error updating RR history for entry {entry.id}: {str(e)}")
                import traceback
                traceback.print_exc()
        
        logger.info(f"RR history update completed. Success: {success_count}, Errors: {error_count}, Expired: {expired_count}")
        
        # Update log entry with completion info
        end_time = datetime.now()
        notes = f"Updated {len(active_entries)} RR entry(ies). Success: {success_count}, Errors: {error_count}, Expired: {expired_count}"
        
        if 'log_id' in locals() and log_id:
            try:
                with Session(engine) as session:
                    log_entry = session.get(RRHistoryLog, log_id)
                    if log_entry:
                        log_entry.end_time = end_time
                        log_entry.notes = notes
                        session.add(log_entry)
                        session.commit()
            except Exception as log_error:
                logger.error(f"Error updating RR history log entry: {str(log_error)}")
        
    except Exception as e:
        logger.error(f"Error in update_rr_history: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Update log entry with error info
        if 'log_id' in locals() and log_id:
            try:
                end_time = datetime.now()
                with Session(engine) as session:
                    log_entry = session.get(RRHistoryLog, log_id)
                    if log_entry:
                        log_entry.end_time = end_time
                        log_entry.notes = f"Error: {str(e)}"
                        session.add(log_entry)
                        session.commit()
            except Exception as log_error:
                logger.error(f"Error updating RR history log entry: {str(log_error)}")


def update_rr_history_manual(bypass_market_hours: bool = False):
    """
    Manually trigger RR history update.
    This function bypasses market hours check if bypass_market_hours is True.
    Useful for testing and manual triggers.
    
    Args:
        bypass_market_hours: If True, skip market hours check and run regardless of market status
        
    Returns:
        log_id: ID of the log entry created for this run
    """
    from app.models.rr_watchlist import RRWatchlist, RRHistory
    from app.models.rr_history_log import RRHistoryLog
    from app.services.rr_watchlist_service import get_all_rr_watchlist_entries
    import yfinance as yf
    import pandas as pd
    from decimal import Decimal
    
    log_entry = None
    start_time = datetime.now()
    log_id = None
    
    try:
        # Create log entry at start
        with Session(engine) as session:
            log_entry = RRHistoryLog(
                start_time=start_time,
                end_time=None,
                notes=None
            )
            session.add(log_entry)
            session.commit()
            session.refresh(log_entry)
            log_id = log_entry.id
        
        # Check if we should run (market hours or within 60 mins after close) unless bypassing
        if not bypass_market_hours:
            et_now = datetime.now(ET_TIMEZONE)
            current_time = et_now.time()
            market_close = time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
            post_market_end = time(17, 0)  # 5:00 PM ET (60 mins after 4:00 PM close)
            
            # Allow execution if market is open OR if it's within 60 mins after market close
            is_post_market_window = market_close <= current_time <= post_market_end
            
            if not is_market_open() and not is_post_market_window:
                logger.info("Outside market hours and post-market window. Skipping RR history update.")
                # Update log entry
                with Session(engine) as session:
                    log_entry = session.get(RRHistoryLog, log_id)
                    if log_entry:
                        log_entry.end_time = datetime.now()
                        log_entry.notes = "Outside market hours and post-market window. Skipped update."
                        session.add(log_entry)
                        session.commit()
                return log_id
        
        et_now = datetime.now(ET_TIMEZONE)
        logger.info("Starting manual RR history update...")
        logger.info(f"Current ET time: {et_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"Bypass market hours: {bypass_market_hours}")
        if not bypass_market_hours:
            logger.info(f"Market open check: {is_market_open()}")
    
    except Exception as e:
        logger.error(f"Error creating RR history log entry: {str(e)}")
        # Continue without logging if log creation fails, but we need log_id
        if not log_id:
            raise
    
    try:
        # Get all non-expired entries
        all_entries = get_all_rr_watchlist_entries()
        active_entries = [e for e in all_entries if e.expired_yn == 'N']
        
        if not active_entries:
            logger.info("No active RR entries to update")
            # Update log entry
            if log_id:
                try:
                    end_time = datetime.now()
                    with Session(engine) as session:
                        log_entry = session.get(RRHistoryLog, log_id)
                        if log_entry:
                            log_entry.end_time = end_time
                            log_entry.notes = "No active RR entries to update"
                            session.add(log_entry)
                            session.commit()
                except Exception as log_error:
                    logger.error(f"Error updating RR history log entry: {str(log_error)}")
            return log_id
        
        logger.info(f"Found {len(active_entries)} active RR entries to update")
        
        today = datetime.now().date()
        success_count = 0
        error_count = 0
        expired_count = 0
        
        for entry in active_entries:
            try:
                # Check if expired
                if entry.expiration < today:
                    # Mark as expired
                    with Session(engine) as session:
                        db_entry = session.get(RRWatchlist, entry.id)
                        if db_entry:
                            db_entry.expired_yn = 'Y'
                            session.add(db_entry)
                            session.commit()
                    expired_count += 1
                    logger.info(f"Marked RR entry {entry.id} as expired (expiration: {entry.expiration})")
                    continue
                
                # Fetch fresh quotes from yfinance
                stock = yf.Ticker(entry.ticker)
                expiration_str = entry.expiration.strftime('%Y-%m-%d')
                opt_chain = stock.option_chain(expiration_str)
                
                # Get put option data
                puts = opt_chain.puts
                put_row = puts[puts['strike'] == float(entry.put_strike)]
                
                if put_row.empty:
                    logger.warning(f"Put option with strike ${entry.put_strike} not found for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                put_row = put_row.iloc[0]
                put_bid = put_row.get('bid')
                put_ask = put_row.get('ask')
                
                if pd.isna(put_bid) or pd.isna(put_ask) or put_bid <= 0 or put_ask <= 0:
                    logger.warning(f"Put option with strike ${entry.put_strike} has missing or invalid bid/ask for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                # Get call option data
                calls = opt_chain.calls
                call_row = calls[calls['strike'] == float(entry.call_strike)]
                
                if call_row.empty:
                    logger.warning(f"Call option with strike ${entry.call_strike} not found for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                call_row = call_row.iloc[0]
                call_bid = call_row.get('bid')
                call_ask = call_row.get('ask')
                
                if pd.isna(call_bid) or pd.isna(call_ask) or call_bid <= 0 or call_ask <= 0:
                    logger.warning(f"Call option with strike ${entry.call_strike} has missing or invalid bid/ask for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                # Calculate average of bid/ask for both options
                put_option_quote = (float(put_bid) + float(put_ask)) / 2.0
                call_option_quote = (float(call_bid) + float(call_ask)) / 2.0
                
                # Calculate current value using average of bid/ask for consistency
                # For risk reversal: we receive put premium, pay call premium
                # Current value = (call_option_quote * call_quantity) - (put_option_quote * put_quantity)
                curr_value = (call_option_quote * entry.call_quantity) - (put_option_quote * entry.put_quantity)
                
                # Store the prices used in calculation (average of bid/ask)
                call_price = Decimal(str(call_option_quote))
                put_price = Decimal(str(put_option_quote))
                
                # Check if history entry already exists for today
                with Session(engine) as session:
                    existing = session.exec(
                        select(RRHistory).where(
                            RRHistory.rr_uuid == entry.id,
                            RRHistory.history_date == today
                        )
                    ).first()
                    
                    if existing:
                        # Update existing entry
                        existing.curr_value = Decimal(str(curr_value))
                        existing.call_price = call_price
                        existing.put_price = put_price
                        session.add(existing)
                    else:
                        # Create new history entry
                        history_entry = RRHistory(
                            rr_uuid=entry.id,
                            ticker=entry.ticker,
                            history_date=today,
                            curr_value=Decimal(str(curr_value)),
                            call_price=call_price,
                            put_price=put_price
                        )
                        session.add(history_entry)
                    
                    session.commit()
                    success_count += 1
                    logger.debug(f"Updated RR history for {entry.ticker} {expiration_str} - Current Value: ${curr_value:.2f}")
                    
            except Exception as e:
                error_count += 1
                logger.error(f"Error updating RR history for entry {entry.id}: {str(e)}")
                import traceback
                traceback.print_exc()
        
        logger.info(f"Manual RR history update completed. Success: {success_count}, Errors: {error_count}, Expired: {expired_count}")
        
        # Update log entry with completion info
        end_time = datetime.now()
        notes = f"Manual update: {len(active_entries)} RR entry(ies). Success: {success_count}, Errors: {error_count}, Expired: {expired_count}"
        
        if log_id:
            try:
                with Session(engine) as session:
                    log_entry = session.get(RRHistoryLog, log_id)
                    if log_entry:
                        log_entry.end_time = end_time
                        log_entry.notes = notes
                        session.add(log_entry)
                        session.commit()
            except Exception as log_error:
                logger.error(f"Error updating RR history log entry: {str(log_error)}")
        
        return log_id
        
    except Exception as e:
        logger.error(f"Error in manual update_rr_history: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Update log entry with error info
        if log_id:
            try:
                end_time = datetime.now()
                with Session(engine) as session:
                    log_entry = session.get(RRHistoryLog, log_id)
                    if log_entry:
                        log_entry.end_time = end_time
                        log_entry.notes = f"Manual update error: {str(e)}"
                        session.add(log_entry)
                        session.commit()
            except Exception as log_error:
                logger.error(f"Error updating RR history log entry: {str(log_error)}")
        
        raise