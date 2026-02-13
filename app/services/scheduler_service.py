"""Scheduled job service for fetching stock data."""
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session, select
from app.database import engine
from app.models.watchlist import WatchListStock
from app.models.scheduler_log import SchedulerLog
from app.services.stock_price_service import refresh_stock_data
from datetime import datetime, time as dt_time, timedelta
from typing import Tuple
import pytz
import logging
import random
import time
from collections import defaultdict
from app.services.api_usage_tracker import with_api_usage_scope

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
    market_open = dt_time(MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE)
    market_close = dt_time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)

    return market_open <= current_time < market_close


def should_proceed_with_update(bypass_market_hours: bool = False, post_market_minutes: int = 20) -> Tuple[bool, str]:
    """
    Unified check for whether a scheduler job should proceed based on market hours.

    Args:
        bypass_market_hours: If True, always proceed regardless of market hours
        post_market_minutes: Minutes after market close to still allow execution (default 20)

    Returns:
        Tuple of (should_proceed: bool, skip_reason: str)
        - If should_proceed is True, skip_reason will be empty
        - If should_proceed is False, skip_reason explains why
    """
    if bypass_market_hours:
        return True, ""

    et_now = datetime.now(ET_TIMEZONE)
    current_time = et_now.time()
    market_close = dt_time(MARKET_CLOSE_HOUR, MARKET_CLOSE_MINUTE)

    # Calculate post-market end time using datetime arithmetic to handle minute overflow
    market_close_dt = et_now.replace(hour=MARKET_CLOSE_HOUR, minute=MARKET_CLOSE_MINUTE, second=0, microsecond=0)
    post_market_end_dt = market_close_dt + timedelta(minutes=post_market_minutes)
    post_market_end = post_market_end_dt.time()

    # Allow execution if market is open
    if is_market_open():
        return True, ""

    # Allow execution in post-market window
    if market_close <= current_time <= post_market_end:
        return True, ""

    return False, f"Market closed. Current time: {current_time}, Market hours: {MARKET_OPEN_HOUR}:{MARKET_OPEN_MINUTE:02d}-{MARKET_CLOSE_HOUR}:{MARKET_CLOSE_MINUTE:02d} ET"


@with_api_usage_scope("scheduler.update_stock_prices")
def update_stock_prices_for_all_watchlists(bypass_market_hours: bool = False):
    """
    Fetch stock price data for all unique tickers across all watchlists.

    Args:
        bypass_market_hours: If True, skip market hours check and run regardless.

    Returns:
        log_id: The ID of the scheduler log entry created for this run, or None if failed.
    """
    start_time = datetime.now()
    log_id = None

    logger.info("="*80)
    logger.info("SCHEDULER JOB: update_stock_prices_for_all_watchlists()")
    logger.info(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Bypass market hours: {bypass_market_hours}")
    logger.info("="*80)

    try:
        # Create log entry at start
        with Session(engine) as session:
            log_entry = SchedulerLog(
                start_time=start_time,
                end_time=None,
                notes="Stock price update job started"
            )
            session.add(log_entry)
            session.commit()
            session.refresh(log_entry)
            log_id = log_entry.id
        logger.info(f"✓ Created scheduler_log entry with ID: {log_id}")

        # Check if we should proceed based on market hours
        should_proceed, skip_reason = should_proceed_with_update(bypass_market_hours, post_market_minutes=20)

        if not should_proceed:
            logger.info(f"⊘ SKIPPING: {skip_reason}")
            with Session(engine) as session:
                log_entry = session.get(SchedulerLog, log_id)
                if log_entry:
                    log_entry.end_time = datetime.now()
                    log_entry.notes = f"Skipped: {skip_reason}"
                    session.add(log_entry)
                    session.commit()
            return log_id

        # Get all unique tickers from all watchlists
        with Session(engine) as session:
            statement = select(WatchListStock.ticker).distinct()
            tickers = session.exec(statement).all()

        unique_tickers = list(set([ticker.upper() for ticker in tickers]))

        if not unique_tickers:
            logger.warning("⊘ SKIPPING: No tickers found")
            with Session(engine) as session:
                log_entry = session.get(SchedulerLog, log_id)
                if log_entry:
                    log_entry.end_time = datetime.now()
                    log_entry.notes = "No tickers found. Skipped stock update."
                    session.add(log_entry)
                    session.commit()
            return log_id

        logger.info(f"Processing {len(unique_tickers)} unique tickers for STOCK DATA")

        success_count = 0
        error_count = 0

        # Jitter initialization
        next_pause_count = random.randint(1, 10)
        processed_count_since_pause = 0

        for idx, ticker in enumerate(unique_tickers, 1):
            # Jitter logic
            processed_count_since_pause += 1
            if processed_count_since_pause >= next_pause_count:
                pause_duration = random.randint(1, 10)
                logger.info(f"  ...Cooling off for {pause_duration}s...")
                time.sleep(pause_duration)
                processed_count_since_pause = 0
                next_pause_count = random.randint(1, 10)

            logger.info(f"[{idx}/{len(unique_tickers)}] Refreshing data for {ticker}...")
            try:
                # Stock update job should refresh prices/metrics only.
                # Options strategies are handled by the dedicated daily options-cache job.
                result = refresh_stock_data(
                    ticker,
                    clear_cache=False,
                    refresh_options_strategies=False,
                    include_options_iv=False
                )

                if result.get("success"):
                    logger.info(f"  ✓ {ticker}: {result['price_records']} prices refreshed")
                    success_count += 1
                else:
                    error_count += 1
                    logger.error(f"  ✗ {ticker}: {result.get('error', 'Unknown error')}")
            except Exception as e:
                error_count += 1
                logger.error(f"  ✗ Error for {ticker}: {str(e)}")

        # Update log entry
        end_time = datetime.now()
        notes = f"Updated stocks: {len(unique_tickers)}. Success: {success_count}, Errors: {error_count}"

        with Session(engine) as session:
            log_entry = session.get(SchedulerLog, log_id)
            if log_entry:
                log_entry.end_time = end_time
                log_entry.notes = notes
                session.add(log_entry)
                session.commit()
        logger.info(f"✓ Stock update job completed. {notes}")

        return log_id

    except Exception as e:
        logger.error(f"Error in update_stock_prices_for_all_watchlists: {str(e)}")
        # Update log entry to mark as failed
        if log_id:
            try:
                with Session(engine) as session:
                    log_entry = session.get(SchedulerLog, log_id)
                    if log_entry:
                        log_entry.end_time = datetime.now()
                        log_entry.notes = f"FAILED: {str(e)}"
                        session.add(log_entry)
                        session.commit()
            except Exception as log_error:
                logger.error(f"Could not update log entry: {log_error}")
        return None


@with_api_usage_scope("scheduler.update_options_cache")
def update_options_cache_for_all_watchlists():
    """
    Fetch and cache options strategies for all unique tickers.
    Scheduled to run at specific times (10:00 AM, 2:00 PM, 4:05 PM ET).
    Creates a log entry in scheduler_log table.

    Returns:
        The ID of the scheduler_log entry created for this run, or None if failed.
    """
    start_time = datetime.now()
    log_id = None

    logger.info("="*80)
    logger.info("SCHEDULER JOB: update_options_cache_for_all_watchlists()")
    logger.info(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)

    try:
        # Create log entry
        with Session(engine) as session:
            log_entry = SchedulerLog(
                start_time=start_time,
                end_time=None,
                notes="Options cache update job started"
            )
            session.add(log_entry)
            session.commit()
            session.refresh(log_entry)
            log_id = log_entry.id

        # Prune expired options from cache before processing
        try:
            from app.services.options_strategy_cache_service import prune_expired_options_cache
            prune_expired_options_cache()
        except Exception as e:
            logger.warning(f"Could not prune expired options cache: {e}")

        # Get tickers
        with Session(engine) as session:
            statement = select(WatchListStock.ticker).distinct()
            tickers = session.exec(statement).all()

        unique_tickers = list(set([ticker.upper() for ticker in tickers]))

        if not unique_tickers:
            logger.warning("⊘ SKIPPING: No tickers found")
            with Session(engine) as session:
                log_entry = session.get(SchedulerLog, log_id)
                if log_entry:
                    log_entry.end_time = datetime.now()
                    log_entry.notes = "No tickers found for options update."
                    session.add(log_entry)
                    session.commit()
            return log_id

        logger.info(f"Processing {len(unique_tickers)} tickers for OPTIONS CACHE")

        success_count = 0
        error_count = 0

        # Jitter initialization
        next_pause_count = random.randint(1, 10)
        processed_count_since_pause = 0

        for idx, ticker in enumerate(unique_tickers, 1):
            # Jitter logic
            processed_count_since_pause += 1
            if processed_count_since_pause >= next_pause_count:
                pause_duration = random.randint(1, 10)
                logger.info(f"  ...Cooling off for {pause_duration}s...")
                time.sleep(pause_duration)
                processed_count_since_pause = 0
                next_pause_count = random.randint(1, 10)

            logger.info(f"[{idx}/{len(unique_tickers)}] Caching options for {ticker}...")
            try:
                from app.services.options_strategy_cache_service import cache_options_strategies_for_ticker
                result = cache_options_strategies_for_ticker(ticker)
                if result['covered_calls'] > 0 or result['risk_reversals'] > 0:
                    logger.info(f"  ✓ Cached {result['covered_calls']} CC, {result['risk_reversals']} RR for {ticker}")
                success_count += 1
            except Exception as e:
                error_count += 1
                logger.error(f"  ✗ Error caching options for {ticker}: {e}")

        # Update log
        end_time = datetime.now()
        notes = f"Updated options cache: {len(unique_tickers)}. Success: {success_count}, Errors: {error_count}"

        with Session(engine) as session:
            log_entry = session.get(SchedulerLog, log_id)
            if log_entry:
                log_entry.end_time = end_time
                log_entry.notes = notes
                session.add(log_entry)
                session.commit()
        logger.info(f"✓ Options cache update job completed. {notes}")
        return log_id

    except Exception as e:
        logger.error(f"Error in update_options_cache_for_all_watchlists: {str(e)}")
        # Update log entry to mark as failed
        if log_id:
            try:
                with Session(engine) as session:
                    log_entry = session.get(SchedulerLog, log_id)
                    if log_entry:
                        log_entry.end_time = datetime.now()
                        log_entry.notes = f"FAILED: {str(e)}"
                        session.add(log_entry)
                        session.commit()
            except Exception as log_error:
                logger.error(f"Could not update log entry: {log_error}")
        return None


@with_api_usage_scope("scheduler.update_rr_history")
def update_rr_history(bypass_market_hours: bool = False):
    """
    Update Risk Reversal history by recalculating net cost for all active entries.

    Args:
        bypass_market_hours: If True, skip market hours check and run regardless.

    Returns:
        log_id: ID of the log entry created for this run, or None if failed.
    """
    from app.models.rr_watchlist import RRWatchlist, RRHistory
    from app.models.rr_history_log import RRHistoryLog
    from app.services.rr_watchlist_service import get_all_rr_watchlist_entries
    from app.providers.factory import ProviderFactory
    from app.providers.exceptions import DataNotAvailableError
    from decimal import Decimal

    start_time = datetime.now()
    log_id = None

    logger.info("="*80)
    logger.info("SCHEDULER JOB: update_rr_history()")
    logger.info(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Bypass market hours: {bypass_market_hours}")
    logger.info("="*80)

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
        logger.info(f"✓ Created rr_history_log entry with ID: {log_id}")

        # Check if we should proceed based on market hours (60 min post-market window for RR)
        should_proceed, skip_reason = should_proceed_with_update(bypass_market_hours, post_market_minutes=60)

        if not should_proceed:
            logger.info(f"⊘ SKIPPING: {skip_reason}")
            with Session(engine) as session:
                log_entry = session.get(RRHistoryLog, log_id)
                if log_entry:
                    log_entry.end_time = datetime.now()
                    log_entry.notes = f"Skipped: {skip_reason}"
                    session.add(log_entry)
                    session.commit()
            return log_id

        logger.info("Starting RR history update...")

        # Get all non-expired entries
        all_entries = get_all_rr_watchlist_entries(fetch_all=True)
        active_entries = [e for e in all_entries if e.expired_yn == 'N']

        if not active_entries:
            logger.info("No active RR entries to update")
            with Session(engine) as session:
                log_entry = session.get(RRHistoryLog, log_id)
                if log_entry:
                    log_entry.end_time = datetime.now()
                    log_entry.notes = "No active RR entries to update"
                    session.add(log_entry)
                    session.commit()
            return log_id

        logger.info(f"Found {len(active_entries)} active RR entries to update")

        today = datetime.now().date()
        success_count = 0
        error_count = 0
        expired_count = 0

        # Jitter initialization
        next_pause_count = random.randint(1, 10)
        processed_count_since_pause = 0

        provider = ProviderFactory.get_default_provider()
        options_chain_cache = {}
        options_chain_requests = 0
        options_chain_fetches = 0
        options_chain_cache_hits = 0
        options_chain_fetch_errors = 0
        rr_requests_by_ticker = defaultdict(int)
        rr_fetches_by_ticker = defaultdict(int)
        rr_cache_hits_by_ticker = defaultdict(int)

        for idx, entry in enumerate(active_entries, 1):
            # Jitter logic
            processed_count_since_pause += 1
            if processed_count_since_pause >= next_pause_count:
                pause_duration = random.randint(1, 10)
                logger.info(f"  ...Cooling off for {pause_duration}s to avoid rate limiting...")
                time.sleep(pause_duration)
                processed_count_since_pause = 0
                next_pause_count = random.randint(1, 10)

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
                expiration_str = entry.expiration.strftime('%Y-%m-%d')
                ticker_upper = entry.ticker.upper()
                cache_key = (ticker_upper, expiration_str)
                options_chain_requests += 1
                rr_requests_by_ticker[ticker_upper] += 1
                if cache_key in options_chain_cache:
                    opt_chain = options_chain_cache[cache_key]
                    options_chain_cache_hits += 1
                    rr_cache_hits_by_ticker[ticker_upper] += 1
                    if opt_chain is None:
                        error_count += 1
                        continue
                else:
                    options_chain_fetches += 1
                    rr_fetches_by_ticker[ticker_upper] += 1
                    try:
                        opt_chain = provider.fetch_options_chain(entry.ticker, expiration_str)
                        options_chain_cache[cache_key] = opt_chain
                    except DataNotAvailableError:
                        options_chain_fetch_errors += 1
                        logger.warning(f"Options chain not available for {entry.ticker} {expiration_str}")
                        options_chain_cache[cache_key] = None
                        error_count += 1
                        continue

                # Get put option data
                put_matches = [p for p in opt_chain.puts if round(p.strike, 2) == round(float(entry.put_strike), 2)]
                if not put_matches:
                    logger.warning(f"Put option with strike ${entry.put_strike} not found for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue

                put = put_matches[0]
                if put.bid is None or put.ask is None or put.bid <= 0 or put.ask <= 0:
                    logger.warning(f"Put option with strike ${entry.put_strike} has missing or invalid bid/ask")
                    error_count += 1
                    continue

                # Get call option data
                call_matches = [c for c in opt_chain.calls if round(c.strike, 2) == round(float(entry.call_strike), 2)]
                if not call_matches:
                    logger.warning(f"Call option with strike ${entry.call_strike} not found for {entry.ticker} {expiration_str}")
                    error_count += 1
                    continue

                call = call_matches[0]
                if call.bid is None or call.ask is None or call.bid <= 0 or call.ask <= 0:
                    logger.warning(f"Call option with strike ${entry.call_strike} has missing or invalid bid/ask")
                    error_count += 1
                    continue

                # Calculate average of bid/ask for both options
                put_option_quote = (float(put.bid) + float(put.ask)) / 2.0
                call_option_quote = (float(call.bid) + float(call.ask)) / 2.0

                # Handle Collar: get short call quote if applicable
                short_call_option_quote = None
                short_call_price = None
                is_collar = entry.ratio == "Collar" and entry.short_call_strike is not None

                if is_collar:
                    short_call_matches = [c for c in opt_chain.calls if round(c.strike, 2) == round(float(entry.short_call_strike), 2)]
                    if not short_call_matches:
                        logger.warning(f"Short call option with strike ${entry.short_call_strike} not found")
                        error_count += 1
                        continue

                    short_call = short_call_matches[0]
                    if short_call.bid is None or short_call.ask is None or short_call.bid <= 0 or short_call.ask <= 0:
                        logger.warning(f"Short call option with strike ${entry.short_call_strike} has missing or invalid bid/ask")
                        error_count += 1
                        continue

                    short_call_option_quote = (float(short_call.bid) + float(short_call.ask)) / 2.0
                    short_call_price = Decimal(str(short_call_option_quote))

                # Calculate current value
                curr_value = (call_option_quote * entry.call_quantity) - (put_option_quote * entry.put_quantity)
                if is_collar and short_call_option_quote and entry.short_call_quantity:
                    curr_value -= (short_call_option_quote * entry.short_call_quantity)

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
                        existing.curr_value = Decimal(str(curr_value))
                        existing.call_price = call_price
                        existing.put_price = put_price
                        existing.short_call_price = short_call_price
                        session.add(existing)
                    else:
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

        # Update log entry with completion info
        end_time = datetime.now()
        notes = f"Updated {len(active_entries)} RR entry(ies). Success: {success_count}, Errors: {error_count}, Expired: {expired_count}"

        logger.info(f"✓ RR history update completed. {notes}")
        logger.info(
            "RR_OPTIONS_CHAIN_USAGE job=update_rr_history active_entries=%d requests=%d provider_fetches=%d cache_hits=%d avoided_calls=%d unique_contracts=%d fetch_errors=%d",
            len(active_entries),
            options_chain_requests,
            options_chain_fetches,
            options_chain_cache_hits,
            options_chain_cache_hits,
            len(options_chain_cache),
            options_chain_fetch_errors
        )

        for ticker in sorted(rr_requests_by_ticker.keys()):
            logger.info(
                "RR_OPTIONS_CHAIN_TICKER ticker=%s requests=%d provider_fetches=%d cache_hits=%d",
                ticker,
                rr_requests_by_ticker[ticker],
                rr_fetches_by_ticker[ticker],
                rr_cache_hits_by_ticker[ticker]
            )

        with Session(engine) as session:
            log_entry = session.get(RRHistoryLog, log_id)
            if log_entry:
                log_entry.end_time = end_time
                log_entry.notes = notes
                session.add(log_entry)
                session.commit()

        return log_id

    except Exception as e:
        logger.error(f"Error in update_rr_history: {str(e)}")
        import traceback
        traceback.print_exc()

        # Update log entry with error info
        if log_id:
            try:
                with Session(engine) as session:
                    from app.models.rr_history_log import RRHistoryLog
                    log_entry = session.get(RRHistoryLog, log_id)
                    if log_entry:
                        log_entry.end_time = datetime.now()
                        log_entry.notes = f"FAILED: {str(e)}"
                        session.add(log_entry)
                        session.commit()
            except Exception as log_error:
                logger.error(f"Could not update log entry: {log_error}")

        return None


def cleanup_old_scheduler_logs():
    """
    Delete scheduler log entries older than 72 hours.
    Cleans up both scheduler_log and rr_history_log tables.
    Scheduled to run daily at 5:00 AM ET.
    Creates a log entry in scheduler_log table for tracking.
    """
    from app.models.rr_history_log import RRHistoryLog

    start_time = datetime.now()
    cutoff_time = start_time - timedelta(hours=72)
    log_id = None

    logger.info("="*80)
    logger.info("SCHEDULER JOB: cleanup_old_scheduler_logs()")
    logger.info(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Deleting log entries older than {cutoff_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)

    try:
        # Create log entry at start
        with Session(engine) as session:
            log_entry = SchedulerLog(
                start_time=start_time,
                end_time=None,
                notes="Scheduler log cleanup job started"
            )
            session.add(log_entry)
            session.commit()
            session.refresh(log_entry)
            log_id = log_entry.id
        logger.info(f"✓ Created scheduler_log entry with ID: {log_id}")

        scheduler_deleted = 0
        rr_history_deleted = 0

        # Delete old scheduler_log entries
        with Session(engine) as session:
            statement = select(SchedulerLog).where(SchedulerLog.start_time < cutoff_time)
            old_entries = session.exec(statement).all()
            scheduler_deleted = len(old_entries)
            for entry in old_entries:
                session.delete(entry)
            session.commit()

        # Delete old rr_history_log entries
        with Session(engine) as session:
            statement = select(RRHistoryLog).where(RRHistoryLog.start_time < cutoff_time)
            old_entries = session.exec(statement).all()
            rr_history_deleted = len(old_entries)
            for entry in old_entries:
                session.delete(entry)
            session.commit()

        # Update log entry with completion info
        end_time = datetime.now()
        notes = f"Cleanup completed: Deleted {scheduler_deleted} scheduler_log, {rr_history_deleted} rr_history_log entries"

        with Session(engine) as session:
            log_entry = session.get(SchedulerLog, log_id)
            if log_entry:
                log_entry.end_time = end_time
                log_entry.notes = notes
                session.add(log_entry)
                session.commit()

        logger.info(f"✓ {notes}")

    except Exception as e:
        logger.error(f"Error in cleanup_old_scheduler_logs: {str(e)}")
        if log_id:
            try:
                with Session(engine) as session:
                    log_entry = session.get(SchedulerLog, log_id)
                    if log_entry:
                        log_entry.end_time = datetime.now()
                        log_entry.notes = f"FAILED: {str(e)}"
                        session.add(log_entry)
                        session.commit()
            except Exception as log_error:
                logger.error(f"Could not update log entry: {log_error}")
        import traceback
        traceback.print_exc()


def update_insights_for_all_watchlists():
    """
    Refresh LLM-generated insights for all unique tickers across all watchlists.
    Scheduled to run daily at 5:00 AM ET.
    Creates a log entry in scheduler_log table.
    """
    start_time = datetime.now()
    log_id = None

    logger.info("="*80)
    logger.info("SCHEDULER JOB: update_insights_for_all_watchlists()")
    logger.info(f"Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("="*80)

    try:
        # Create log entry
        with Session(engine) as session:
            log_entry = SchedulerLog(
                start_time=start_time,
                end_time=None,
                notes="LLM insights update job started"
            )
            session.add(log_entry)
            session.commit()
            session.refresh(log_entry)
            log_id = log_entry.id
        logger.info(f"✓ Created scheduler_log entry with ID: {log_id}")

        # Call the insights service to refresh
        from app.services.insights_service import refresh_insights_for_watchlist_tickers
        results = refresh_insights_for_watchlist_tickers()

        # Update log entry
        end_time = datetime.now()
        notes = f"Insights refresh: Success={results['success']}, Failed={results['failed']}, Skipped={results['skipped']}"

        with Session(engine) as session:
            log_entry = session.get(SchedulerLog, log_id)
            if log_entry:
                log_entry.end_time = end_time
                log_entry.notes = notes
                session.add(log_entry)
                session.commit()

        logger.info(f"✓ Insights update job completed. {notes}")

    except Exception as e:
        logger.error(f"Error in update_insights_for_all_watchlists: {str(e)}")
        if log_id:
            try:
                with Session(engine) as session:
                    log_entry = session.get(SchedulerLog, log_id)
                    if log_entry:
                        log_entry.end_time = datetime.now()
                        log_entry.notes = f"FAILED: {str(e)}"
                        session.add(log_entry)
                        session.commit()
            except Exception as log_error:
                logger.error(f"Could not update log entry: {log_error}")
        import traceback
        traceback.print_exc()


def start_scheduler():
    """
    Start the background scheduler to fetch stock data and update options cache.
    """
    global scheduler

    logger.info("="*80)
    logger.info("INITIALIZING SCHEDULER")
    logger.info("="*80)

    import os
    auto_start = os.getenv("SCHEDULER_AUTO_START", "true").lower() == "true"

    if not auto_start:
        logger.warning("⚠ SCHEDULER AUTO-START DISABLED (Dev Mode)")
        logger.info("  Set SCHEDULER_AUTO_START=true in .env to enable automatic scheduling.")
        logger.info("  You can still trigger jobs manually via debug endpoints.")
        return

    if scheduler is not None and scheduler.running:
        logger.warning("⚠ Scheduler is already running - skipping initialization")
        return

    logger.info("Creating BackgroundScheduler instance...")
    logger.info(f"  Timezone: {ET_TIMEZONE}")
    scheduler = BackgroundScheduler(timezone=ET_TIMEZONE)
    logger.info("✓ BackgroundScheduler created")

    # 1. Stock Data Update: Every 20 minutes (with market hours check inside)
    logger.info("Registering job: update_stock_prices (interval=20min)")
    scheduler.add_job(
        func=update_stock_prices_for_all_watchlists,
        trigger=IntervalTrigger(minutes=20),
        id='update_stock_prices',
        name='Update stock prices (every 20 min)',
        replace_existing=True
    )

    # 2. Options Cache Update: After Market Close (4:05 PM ET / 1:05 PM PT)
    logger.info("Registering job: update_options_cache (16:05 ET)")
    scheduler.add_job(
        func=update_options_cache_for_all_watchlists,
        trigger=CronTrigger(hour=16, minute=5, timezone=ET_TIMEZONE),
        id='update_options_cache',
        name='Update options cache (daily 16:05 ET)',
        replace_existing=True
    )

    # 3. RR History Update: Every 60 minutes (with market hours check inside)
    logger.info("Registering job: update_rr_history (interval=60min)")
    scheduler.add_job(
        func=update_rr_history,
        trigger=IntervalTrigger(minutes=60),
        id='update_rr_history',
        name='Update RR history (every 60 min)',
        replace_existing=True
    )

    # 4. Cleanup old scheduler logs: Daily at 5:00 AM ET
    logger.info("Registering job: cleanup_old_scheduler_logs (daily 05:00 ET)")
    scheduler.add_job(
        func=cleanup_old_scheduler_logs,
        trigger=CronTrigger(hour=5, minute=0, timezone=ET_TIMEZONE),
        id='cleanup_old_scheduler_logs',
        name='Cleanup old scheduler logs (daily 05:00 ET)',
        replace_existing=True
    )

    # 5. LLM Insights Update: Daily at 5:30 AM ET
    logger.info("Registering job: update_insights (daily 05:30 ET)")
    scheduler.add_job(
        func=update_insights_for_all_watchlists,
        trigger=CronTrigger(hour=5, minute=30, timezone=ET_TIMEZONE),
        id='update_insights',
        name='Update LLM insights (daily 05:30 ET)',
        replace_existing=True
    )

    logger.info("Starting scheduler...")
    scheduler.start()
    logger.info("✓ Scheduler started successfully")

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


# Aliases for backward compatibility with existing code
def fetch_all_watchlist_stocks_manual(bypass_market_hours: bool = False):
    """Alias for update_stock_prices_for_all_watchlists with bypass option."""
    return update_stock_prices_for_all_watchlists(bypass_market_hours=bypass_market_hours)


def update_rr_history_manual(bypass_market_hours: bool = False):
    """Alias for update_rr_history with bypass option."""
    return update_rr_history(bypass_market_hours=bypass_market_hours)
