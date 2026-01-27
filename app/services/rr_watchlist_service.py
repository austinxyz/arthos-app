"""Service for managing Risk Reversal watchlist."""
import pandas as pd
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID
from typing import Dict, Any, Optional, List, Union
from sqlmodel import Session, select
from app.database import engine
from app.models.rr_watchlist import RRWatchlist, RRHistory
from app.providers.factory import ProviderFactory
from app.providers.exceptions import TickerNotFoundError, DataNotAvailableError
import logging

logger = logging.getLogger(__name__)


def to_str(value: Union[str, UUID, None]) -> Optional[str]:
    """Convert UUID to string, pass through strings, return None for None."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    return value


def save_rr_to_watchlist(
    ticker: str,
    expiration: str,
    put_strike: float,
    call_strike: float,
    ratio: str,
    current_price: float,
    sold_call_strike: Optional[float] = None,
    collar_type: Optional[str] = None,
    account_id: Optional[Union[str, UUID]] = None
) -> Dict[str, Any]:
    """
    Save a Risk Reversal strategy to the watchlist.
    Fetches fresh quotes from data provider and calculates averages of bid/ask.
    
    Args:
        ticker: Stock ticker symbol
        expiration: Expiration date (YYYY-MM-DD format)
        put_strike: Put strike price
        call_strike: Call strike price
        ratio: Ratio string (e.g., "1:1", "1:2", "Collar")
        current_price: Current stock price
        sold_call_strike: Short call strike price for Collar strategy (optional)
        collar_type: Collar sub-type (e.g., "1:1", "1:2") for Collar strategy (optional)
        
    Returns:
        Dictionary with success status and message or error
    """
    try:
        # Parse ratio to get quantities
        is_collar = ratio == "Collar"
        if is_collar:
            # For Collar, use collar_type to determine quantities
            if collar_type:
                collar_parts = collar_type.split(':')
                put_quantity = int(collar_parts[0])
                call_quantity = int(collar_parts[1])
            else:
                # Default to 1:1 if collar_type not specified
                put_quantity = 1
                call_quantity = 1
        else:
            ratio_parts = ratio.split(':')
            put_quantity = int(ratio_parts[0])
            call_quantity = int(ratio_parts[1])
        
        # Fetch fresh option quotes from data provider
        provider = ProviderFactory.get_default_provider()
        try:
            opt_chain = provider.fetch_options_chain(ticker, expiration)
        except DataNotAvailableError:
            return {"success": False, "error": f"Options chain not available for {ticker} expiration {expiration}"}
        
        # Get put option data
        put_matches = [p for p in opt_chain.puts if round(p.strike, 2) == round(put_strike, 2)]
        if not put_matches:
            return {"success": False, "error": f"Put option with strike ${put_strike:.2f} not found for expiration {expiration}"}
        
        put = put_matches[0]
        put_bid = put.bid
        put_ask = put.ask
        
        if put_bid is None or put_ask is None or put_bid <= 0 or put_ask <= 0:
            return {"success": False, "error": f"Put option with strike ${put_strike:.2f} has missing or invalid bid/ask prices"}
        
        # Get call option data
        call_matches = [c for c in opt_chain.calls if round(c.strike, 2) == round(call_strike, 2)]
        if not call_matches:
            return {"success": False, "error": f"Call option with strike ${call_strike:.2f} not found for expiration {expiration}"}
        
        call = call_matches[0]
        call_bid = call.bid
        call_ask = call.ask
        
        if call_bid is None or call_ask is None or call_bid <= 0 or call_ask <= 0:
            return {"success": False, "error": f"Call option with strike ${call_strike:.2f} has missing or invalid bid/ask prices"}
        
        # Calculate average of bid/ask for both options
        put_option_quote = (float(put_bid) + float(put_ask)) / 2.0
        call_option_quote = (float(call_bid) + float(call_ask)) / 2.0
        
        # Handle Collar: get short call quote if applicable
        short_call_option_quote = None
        short_call_quantity = None
        if is_collar and sold_call_strike:
            short_call_matches = [c for c in opt_chain.calls if round(c.strike, 2) == round(sold_call_strike, 2)]
            if not short_call_matches:
                return {"success": False, "error": f"Short call option with strike ${sold_call_strike:.2f} not found for expiration {expiration}"}
            
            short_call = short_call_matches[0]
            short_call_bid = short_call.bid
            short_call_ask = short_call.ask
            
            if short_call_bid is None or short_call_ask is None or short_call_bid <= 0 or short_call_ask <= 0:
                return {"success": False, "error": f"Short call option with strike ${sold_call_strike:.2f} has missing or invalid bid/ask prices"}
            
            short_call_option_quote = (float(short_call_bid) + float(short_call_ask)) / 2.0
            short_call_quantity = call_quantity  # Same quantity as bought calls
        
        # Calculate net cost (entry price)
        # For risk reversal: we receive put premium, pay call premium
        # For Collar: also receive short call premium
        # Net cost = (call_option_quote * call_quantity) - (put_option_quote * put_quantity) - (short_call * short_call_quantity)
        entry_price = (call_option_quote * call_quantity) - (put_option_quote * put_quantity)
        if short_call_option_quote and short_call_quantity:
            entry_price -= (short_call_option_quote * short_call_quantity)
        
        # Parse expiration date
        exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
        
        # Create RR watchlist entry
        with Session(engine) as session:
            # Check if entry already exists for this calculation
            # Logic: If account_id provided, unique per account.
            
            statement = select(RRWatchlist).where(RRWatchlist.ticker == ticker.upper())
            if account_id:
                statement = statement.where(RRWatchlist.account_id == account_id)
            else:
                statement = statement.where(RRWatchlist.account_id == None)
                
            existing_entry = session.exec(statement).first()

            if existing_entry:
                # Update
                existing_entry.call_strike = Decimal(str(call_strike))
                existing_entry.call_quantity = call_quantity
                existing_entry.put_strike = Decimal(str(put_strike))
                existing_entry.put_quantity = put_quantity
                existing_entry.stock_price = Decimal(str(current_price))
                existing_entry.entry_price = Decimal(str(entry_price))
                existing_entry.call_option_quote = Decimal(str(call_option_quote))
                existing_entry.put_option_quote = Decimal(str(put_option_quote))
                existing_entry.expiration = exp_date
                existing_entry.ratio = ratio
                existing_entry.short_call_strike = Decimal(str(sold_call_strike)) if sold_call_strike else None
                existing_entry.short_call_quantity = short_call_quantity
                existing_entry.short_call_option_quote = Decimal(str(short_call_option_quote)) if short_call_option_quote else None
                existing_entry.collar_type = collar_type
                existing_entry.date_added = datetime.now()
                
                session.add(existing_entry)
                session.commit()
                session.refresh(existing_entry)
                rr_entry = existing_entry
            else:
                # Create
                rr_entry = RRWatchlist(
                    ticker=ticker.upper(),
                    call_strike=Decimal(str(call_strike)),
                    call_quantity=call_quantity,
                    put_strike=Decimal(str(put_strike)),
                    put_quantity=put_quantity,
                    stock_price=Decimal(str(current_price)),
                    entry_price=Decimal(str(entry_price)),
                    call_option_quote=Decimal(str(call_option_quote)),
                    put_option_quote=Decimal(str(put_option_quote)),
                    expiration=exp_date,
                    ratio=ratio,
                    expired_yn="N",
                    # Collar-specific fields
                    short_call_strike=Decimal(str(sold_call_strike)) if sold_call_strike else None,
                    short_call_quantity=short_call_quantity,
                    short_call_option_quote=Decimal(str(short_call_option_quote)) if short_call_option_quote else None,
                    collar_type=collar_type,
                    account_id=account_id
                )
                session.add(rr_entry)
                session.commit()
                session.refresh(rr_entry)
            
            if is_collar:
                logger.info(f"Saved Collar to watchlist: {ticker} {expiration} {collar_type} Put ${put_strike} Call ${call_strike} Short Call ${sold_call_strike}")
            else:
                logger.info(f"Saved RR to watchlist: {ticker} {expiration} {ratio} Put ${put_strike} Call ${call_strike}")
            
            return {
                "success": True,
                "message": f"Risk Reversal saved successfully",
                "id": str(rr_entry.id)
            }
            
    except Exception as e:
        logger.error(f"Error saving RR to watchlist: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": f"Error saving Risk Reversal: {str(e)}"}


def get_all_rr_watchlist_entries(account_id: Optional[Union[str, UUID]] = None, fetch_all: bool = False) -> List[RRWatchlist]:
    """
    Get all Risk Reversal watchlist entries.
    
    Args:
        account_id: Optional ID of the account to filter by
        fetch_all: If True, returns all entries regardless of account_id (for scheduler)
        
    Returns:
        List of RRWatchlist objects.
    """
    with Session(engine) as session:
        statement = select(RRWatchlist)
        if fetch_all:
            pass  # No filter, return all
        elif account_id:
            statement = statement.where(RRWatchlist.account_id == account_id)
        else:
             statement = statement.where(RRWatchlist.account_id == None)
             
        entries = session.exec(statement).all()
        return list(entries)


def get_latest_net_cost(rr_uuid: Union[str, UUID]) -> Optional[Decimal]:
    """Get the latest current value from rr_history for a given RR entry."""
    with Session(engine) as session:
        statement = select(RRHistory).where(
            RRHistory.rr_uuid == rr_uuid
        ).order_by(RRHistory.history_date.desc()).limit(1)
        latest = session.exec(statement).first()
        return latest.curr_value if latest else None


def get_rr_watchlist_entry(rr_uuid: Union[str, UUID], account_id: Optional[Union[str, UUID]] = None) -> Optional[RRWatchlist]:
    """Get a specific RR watchlist entry by UUID."""
    with Session(engine) as session:
        entry = session.get(RRWatchlist, rr_uuid)
        # Convert both to strings for comparison (PostgreSQL returns UUID objects)
        if entry and account_id and to_str(entry.account_id) != to_str(account_id):
            logger.warning(f"Access denied for RR entry {rr_uuid} for account {account_id}")
            return None
        return entry


def delete_rr_watchlist_entry(rr_uuid: Union[str, UUID], account_id: Optional[Union[str, UUID]] = None) -> bool:
    """
    Delete an RR watchlist entry and all associated history.
    Returns True if successful, False otherwise.
    """
    try:
        with Session(engine) as session:
            rr_entry = session.get(RRWatchlist, rr_uuid)
            if not rr_entry:
                return False
            
            # Convert both to strings for comparison (PostgreSQL returns UUID objects)
            if account_id and to_str(rr_entry.account_id) != to_str(account_id):
                logger.warning(f"Attempt to delete RR entry {rr_uuid} by wrong account {account_id}")
                return False
            
            # Delete associated history (cascade should handle this, but explicit is better)
            statement = select(RRHistory).where(RRHistory.rr_uuid == rr_uuid)
            history_entries = session.exec(statement).all()
            for hist in history_entries:
                session.delete(hist)
            
            # Delete the watchlist entry
            session.delete(rr_entry)
            session.commit()
            
            logger.info(f"Deleted RR watchlist entry: {rr_uuid}")
            return True
            
    except Exception as e:
        logger.error(f"Error deleting RR watchlist entry: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def get_rr_history(rr_uuid: Union[str, UUID]) -> list[RRHistory]:
    """Get history for a specific RR watchlist entry."""
    with Session(engine) as session:
        statement = select(RRHistory).where(
            RRHistory.rr_uuid == rr_uuid
        ).order_by(RRHistory.history_date.asc())
        entries = session.exec(statement).all()
        return list(entries)
