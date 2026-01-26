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
    
    logger.info("="*80)
    logger.info("SCHEDULER JOB TRIGGERED: fetch_all_watchlist_stocks()")
    logger.info(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)
    
    try:
        # Create log entry at start
        logger.debug("Creating scheduler_log entry in database...")
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
        logger.info(f"✓ Created scheduler_log entry with ID: {log_id}")
        
        # Check if market is open (unless this is the post-market update)
        et_now = datetime.now(ET_TIMEZONE)
        current_time = et_now.time()
        market_close = time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)
        
        logger.debug(f"Market hours check:")
        logger.debug(f"  Current ET time: {et_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.debug(f"  Current time: {current_time}")
        logger.debug(f"  Market close time: {market_close}")
        logger.debug(f"  Day of week: {et_now.strftime('%A')} (weekday={et_now.weekday()})")
        
        # Allow execution if market is open OR if it's the post-market update (4:00 PM - 4:05 PM)
        is_post_market = market_close <= current_time <= time(16, 5)
        market_open = is_market_open()
        
        logger.info(f"Market status: is_open={market_open}, is_post_market={is_post_market}")
        
        if not market_open and not is_post_market:
            logger.warning("⊘ SKIPPING: Market is closed and not in post-market window")
            logger.info(f"  Reason: Market hours are {MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} - {MARKET_CLOSE_HOUR}:{MARKET_CLOSE_MINUTE:02d} ET")
            logger.info(f"  Post-market window: 16:00 - 16:05 ET")
            # Update log entry
            with Session(engine) as session:
                log_entry = session.get(SchedulerLog, log_id)
                if log_entry:
                    log_entry.end_time = datetime.now()
                    log_entry.notes = "Market is closed. Skipped fetch."
                    session.add(log_entry)
                    session.commit()
            logger.debug(f"✓ Updated scheduler_log entry {log_id} with skip reason")
            return
        
        logger.info("✓ Market is open or in post-market window - proceeding with fetch")
        logger.info(f"Current ET time: {et_now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"Market open: {market_open}, Post-market: {is_post_market}")
        
        # Get all unique tickers from all watchlists
        logger.debug("Querying database for watchlist tickers...")
        with Session(engine) as session:
            statement = select(WatchListStock.ticker).distinct()
            tickers = session.exec(statement).all()
        
        unique_tickers = list(set([ticker.upper() for ticker in tickers]))
        logger.info(f"Found {len(tickers)} ticker entries in watchlist table")
        logger.info(f"Unique tickers after deduplication: {len(unique_tickers)}")
        
        if not unique_tickers:
            logger.warning("⊘ SKIPPING: No tickers found in watchlists")
            logger.debug("  Reason: watchlist table is empty or has no ticker entries")
            # Update log entry
            end_time = datetime.now()
            with Session(engine) as session:
                log_entry = session.get(SchedulerLog, log_id)
                if log_entry:
                    log_entry.end_time = end_time
                    log_entry.notes = "No tickers found in watchlists. Skipped fetch."
                    session.add(log_entry)
                    session.commit()
            logger.debug(f"✓ Updated scheduler_log entry {log_id} with skip reason")
            return
        
        logger.info(f"Processing {len(unique_tickers)} unique tickers: {', '.join(unique_tickers)}")
        logger.info("-" * 80)
        
        success_count = 0
        error_count = 0
        
        for idx, ticker in enumerate(unique_tickers, 1):
            logger.info(f"[{idx}/{len(unique_tickers)}] Processing {ticker}...")
            try:
                price_data, new_records = fetch_and_save_stock_prices(ticker)
                
                if new_records > 0:
                    success_count += 1
                    logger.info(f"  ✓ Inserted/updated {new_records} record(s) in stock_price table for {ticker}")
                else:
                    # No new records - this is normal when market is closed or no updates available
                    success_count += 1
                    logger.info(f"  ⊘ No new records to insert for {ticker} (data already up-to-date)")
            except ValueError as e:
                # ValueError indicates a real problem (invalid ticker, network error, etc.)
                error_count += 1
                logger.error(f"  ✗ ValueError for {ticker}: {str(e)}")
            except Exception as e:
                # Other exceptions (unexpected errors)
                error_count += 1
                logger.error(f"  ✗ Unexpected error for {ticker}: {str(e)}")
                import traceback
                logger.debug(f"  Stack trace:\n{traceback.format_exc()}")
        
        logger.info("-" * 80)
        logger.info(f"✓ Scheduled fetch completed. Success: {success_count}, Errors: {error_count}")
        
        # Update log entry with completion info
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        notes = f"Fetched data for {len(unique_tickers)} stock(s). Success: {success_count}, Errors: {error_count}"
        
        logger.debug(f"Updating scheduler_log entry {log_id} with completion info...")
        with Session(engine) as session:
            log_entry = session.get(SchedulerLog, log_id)
            if log_entry:
                log_entry.end_time = end_time
                log_entry.notes = notes
                session.add(log_entry)
                session.commit()
        logger.info(f"✓ Updated scheduler_log entry {log_id}")
        logger.info(f"Total execution time: {duration:.2f} seconds")
        logger.info("=" * 80)
        
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
    
    logger.info("="*80)
    logger.info("INITIALIZING SCHEDULER")
    logger.info("="*80)
    
    if scheduler is not None and scheduler.running:
        logger.warning("⚠ Scheduler is already running - skipping initialization")
        return
    
    logger.info("Creating BackgroundScheduler instance...")
    logger.info(f"  Timezone: {ET_TIMEZONE}")
    scheduler = BackgroundScheduler(timezone=ET_TIMEZONE)
    logger.info("✓ BackgroundScheduler created")
    
    # Schedule the job to run every 60 minutes
    # The fetch_all_watchlist_stocks function will check market hours internally
    # This ensures it runs every hour, refreshing today's data during market hours
    logger.info("Registering job: fetch_watchlist_stocks (interval)")
    logger.info("  Function: fetch_all_watchlist_stocks")
    logger.info("  Trigger: IntervalTrigger(minutes=60)")
    logger.info("  ID: fetch_watchlist_stocks")
    scheduler.add_job(
        func=fetch_all_watchlist_stocks,
        trigger=IntervalTrigger(minutes=60),
        id='fetch_watchlist_stocks',
        name='Fetch stock data for all watchlist tickers (every 60 min, refreshes today during market hours)',
        replace_existing=True
    )
    logger.info("✓ Job registered: fetch_watchlist_stocks")
    
    # Schedule a post-market update at 4:00 PM ET
    logger.info("Registering job: fetch_watchlist_stocks_post_market (cron)")
    logger.info("  Function: fetch_all_watchlist_stocks")
    logger.info("  Trigger: CronTrigger(hour=16, minute=0, timezone=ET_TIMEZONE)")
    logger.info("  ID: fetch_watchlist_stocks_post_market")
    scheduler.add_job(
        func=fetch_all_watchlist_stocks,
        trigger=CronTrigger(hour=16, minute=0, timezone=ET_TIMEZONE),
        id='fetch_watchlist_stocks_post_market',
        name='Fetch stock data after market close (4:00 PM ET)',
        replace_existing=True
    )
    logger.info("✓ Job registered: fetch_watchlist_stocks_post_market")
    
    # Schedule RR history update job (every hour during market hours + 60 mins after close)
    logger.info("Registering job: update_rr_history (interval)")
    logger.info("  Function: update_rr_history")
    logger.info("  Trigger: IntervalTrigger(minutes=60)")
    logger.info("  ID: update_rr_history")
    scheduler.add_job(
        func=update_rr_history,
        trigger=IntervalTrigger(minutes=60),
        id='update_rr_history',
        name='Update RR history (every 60 min, during market hours + 60 mins after close)',
        replace_existing=True
    )
    logger.info("✓ Job registered: update_rr_history")
    
    logger.info("Starting scheduler...")
    scheduler.start()
    logger.info("✓ Scheduler started successfully")
    logger.info("")
    logger.info("Scheduler configuration:")
    logger.info(f"  Market hours: {MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} - {MARKET_CLOSE_HOUR}:{MARKET_CLOSE_MINUTE:02d} ET")
    logger.info(f"  Timezone: {ET_TIMEZONE}")
    logger.info(f"  Jobs registered: {len(scheduler.get_jobs())}")
    
    # Log next run times for each job
    for job in scheduler.get_jobs():
        next_run = job.next_run_time
        logger.info(f"  - {job.id}: next run at {next_run.strftime('%Y-%m-%d %H:%M:%S %Z') if next_run else 'N/A'}")
    
    logger.info("="*80)


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
    from app.providers.factory import ProviderFactory
    from app.providers.exceptions import DataNotAvailableError
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
            logger.info("⊘ SKIPPING RR history update: Outside market hours and post-market window")
            logger.debug(f"  Current time: {current_time}")
            logger.debug(f"  Market hours: {MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d} - {MARKET_CLOSE_HOUR}:{MARKET_CLOSE_MINUTE:02d} ET")
            logger.debug(f"  Post-market window: 16:00 - 17:00 ET")
            # Update log entry
            with Session(engine) as session:
                log_entry = session.get(RRHistoryLog, log_id)
                if log_entry:
                    log_entry.end_time = datetime.now()
                    log_entry.notes = "Outside market hours and post-market window. Skipped update."
                    session.add(log_entry)
                    session.commit()
            logger.debug(f"✓ Updated rr_history_log entry {log_id} with skip reason")
            return
        
        logger.info("Starting RR history update...")
    
    except Exception as e:
        logger.error(f"Error creating RR history log entry: {str(e)}")
        # Continue without logging if log creation fails
    
    try:
        # Get all non-expired entries
        all_entries = get_all_rr_watchlist_entries(fetch_all=True)
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
                
                # Fetch fresh quotes from data provider
                provider = ProviderFactory.get_default_provider()
                expiration_str = entry.expiration.strftime('%Y-%m-%d')
                try:
                    opt_chain = provider.fetch_options_chain(entry.ticker, expiration_str)
                except DataNotAvailableError:
                    logger.warning(f"Options chain not available for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                # Get put option data
                put_matches = [p for p in opt_chain.puts if round(p.strike, 2) == round(float(entry.put_strike), 2)]
                if not put_matches:
                    logger.warning(f"Put option with strike ${entry.put_strike} not found for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                put = put_matches[0]
                put_bid = put.bid
                put_ask = put.ask
                
                if put_bid is None or put_ask is None or put_bid <= 0 or put_ask <= 0:
                    logger.warning(f"Put option with strike ${entry.put_strike} has missing or invalid bid/ask for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                # Get call option data
                call_matches = [c for c in opt_chain.calls if round(c.strike, 2) == round(float(entry.call_strike), 2)]
                if not call_matches:
                    logger.warning(f"Call option with strike ${entry.call_strike} not found for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                call = call_matches[0]
                call_bid = call.bid
                call_ask = call.ask
                
                if call_bid is None or call_ask is None or call_bid <= 0 or call_ask <= 0:
                    logger.warning(f"Call option with strike ${entry.call_strike} has missing or invalid bid/ask for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                # Calculate average of bid/ask for both options
                put_option_quote = (float(put_bid) + float(put_ask)) / 2.0
                call_option_quote = (float(call_bid) + float(call_ask)) / 2.0
                
                # Handle Collar: get short call quote if applicable
                short_call_option_quote = None
                short_call_price = None
                is_collar = entry.ratio == "Collar" and entry.short_call_strike is not None
                
                if is_collar:
                    short_call_matches = [c for c in opt_chain.calls if round(c.strike, 2) == round(float(entry.short_call_strike), 2)]
                    if not short_call_matches:
                        logger.warning(f"Short call option with strike ${entry.short_call_strike} not found for {entry.ticker} {expiration_str}")
                        error_count += 1
                        continue
                    
                    short_call = short_call_matches[0]
                    short_call_bid = short_call.bid
                    short_call_ask = short_call.ask
                    
                    if short_call_bid is None or short_call_ask is None or short_call_bid <= 0 or short_call_ask <= 0:
                        logger.warning(f"Short call option with strike ${entry.short_call_strike} has missing or invalid bid/ask for {entry.ticker} {expiration_str}")
                        error_count += 1
                        continue
                    
                    short_call_option_quote = (float(short_call_bid) + float(short_call_ask)) / 2.0
                    short_call_price = Decimal(str(short_call_option_quote))
                
                # Calculate current value using average of bid/ask for consistency
                # For risk reversal: we receive put premium, pay call premium
                # For Collar: also receive short call premium
                # Current value = (call_option_quote * call_quantity) - (put_option_quote * put_quantity) - (short_call * short_call_quantity)
                curr_value = (call_option_quote * entry.call_quantity) - (put_option_quote * entry.put_quantity)
                if is_collar and short_call_option_quote and entry.short_call_quantity:
                    curr_value -= (short_call_option_quote * entry.short_call_quantity)
                
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
                        logger.debug(f"  ✓ Updating existing rr_history record for {entry.ticker} {expiration_str}")
                        existing.curr_value = Decimal(str(curr_value))
                        existing.call_price = call_price
                        existing.put_price = put_price
                        existing.short_call_price = short_call_price
                        session.add(existing)
                    else:
                        # Create new history entry
                        logger.debug(f"  ✓ Inserting new rr_history record for {entry.ticker} {expiration_str}")
                        history_entry = RRHistory(
                            rr_uuid=entry.id,
                            ticker=entry.ticker,
                            history_date=today,
                            curr_value=Decimal(str(curr_value)),
                            call_price=call_price,
                            put_price=put_price,
                            short_call_price=short_call_price
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
    from app.providers.factory import ProviderFactory
    from app.providers.exceptions import DataNotAvailableError
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
        all_entries = get_all_rr_watchlist_entries(fetch_all=True)
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
                
                # Fetch fresh quotes from data provider
                provider = ProviderFactory.get_default_provider()
                expiration_str = entry.expiration.strftime('%Y-%m-%d')
                try:
                    opt_chain = provider.fetch_options_chain(entry.ticker, expiration_str)
                except DataNotAvailableError:
                    logger.warning(f"Options chain not available for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                # Get put option data
                put_matches = [p for p in opt_chain.puts if round(p.strike, 2) == round(float(entry.put_strike), 2)]
                if not put_matches:
                    logger.warning(f"Put option with strike ${entry.put_strike} not found for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                put = put_matches[0]
                put_bid = put.bid
                put_ask = put.ask
                
                if put_bid is None or put_ask is None or put_bid <= 0 or put_ask <= 0:
                    logger.warning(f"Put option with strike ${entry.put_strike} has missing or invalid bid/ask for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                # Get call option data
                call_matches = [c for c in opt_chain.calls if round(c.strike, 2) == round(float(entry.call_strike), 2)]
                if not call_matches:
                    logger.warning(f"Call option with strike ${entry.call_strike} not found for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                call = call_matches[0]
                call_bid = call.bid
                call_ask = call.ask
                
                if call_bid is None or call_ask is None or call_bid <= 0 or call_ask <= 0:
                    logger.warning(f"Call option with strike ${entry.call_strike} has missing or invalid bid/ask for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue
                
                # Calculate average of bid/ask for both options
                put_option_quote = (float(put_bid) + float(put_ask)) / 2.0
                call_option_quote = (float(call_bid) + float(call_ask)) / 2.0
                
                # Handle Collar: get short call quote if applicable
                short_call_option_quote = None
                short_call_price = None
                is_collar = entry.ratio == "Collar" and entry.short_call_strike is not None
                
                if is_collar:
                    short_call_matches = [c for c in opt_chain.calls if round(c.strike, 2) == round(float(entry.short_call_strike), 2)]
                    if not short_call_matches:
                        logger.warning(f"Short call option with strike ${entry.short_call_strike} not found for {entry.ticker} {expiration_str}")
                        error_count += 1
                        continue
                    
                    short_call = short_call_matches[0]
                    short_call_bid = short_call.bid
                    short_call_ask = short_call.ask
                    
                    if short_call_bid is None or short_call_ask is None or short_call_bid <= 0 or short_call_ask <= 0:
                        logger.warning(f"Short call option with strike ${entry.short_call_strike} has missing or invalid bid/ask for {entry.ticker} {expiration_str}")
                        error_count += 1
                        continue
                    
                    short_call_option_quote = (float(short_call_bid) + float(short_call_ask)) / 2.0
                    short_call_price = Decimal(str(short_call_option_quote))
                
                # Calculate current value using average of bid/ask for consistency
                # For risk reversal: we receive put premium, pay call premium
                # For Collar: also receive short call premium
                # Current value = (call_option_quote * call_quantity) - (put_option_quote * put_quantity) - (short_call * short_call_quantity)
                curr_value = (call_option_quote * entry.call_quantity) - (put_option_quote * entry.put_quantity)
                if is_collar and short_call_option_quote and entry.short_call_quantity:
                    curr_value -= (short_call_option_quote * entry.short_call_quantity)
                
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
                        existing.short_call_price = short_call_price
                        session.add(existing)
                    else:
                        # Create new history entry
                        history_entry = RRHistory(
                            rr_uuid=entry.id,
                            ticker=entry.ticker,
                            history_date=today,
                            curr_value=Decimal(str(curr_value)),
                            call_price=call_price,
                            put_price=put_price,
                            short_call_price=short_call_price
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