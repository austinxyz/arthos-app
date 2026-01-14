"""Service for managing Risk Reversal watchlist."""
import yfinance as yf
import pandas as pd
from datetime import datetime, date
from decimal import Decimal
from uuid import UUID
from typing import Dict, Any, Optional
from sqlmodel import Session, select
from app.database import engine
from app.models.rr_watchlist import RRWatchlist, RRHistory
import logging

logger = logging.getLogger(__name__)


def save_rr_to_watchlist(
    ticker: str,
    expiration: str,
    put_strike: float,
    call_strike: float,
    ratio: str,
    current_price: float
) -> Dict[str, Any]:
    """
    Save a Risk Reversal strategy to the watchlist.
    Fetches fresh quotes from yfinance and calculates averages of bid/ask.
    
    Args:
        ticker: Stock ticker symbol
        expiration: Expiration date (YYYY-MM-DD format)
        put_strike: Put strike price
        call_strike: Call strike price
        ratio: Ratio string (e.g., "1:1", "1:2")
        current_price: Current stock price
        
    Returns:
        Dictionary with success status and message or error
    """
    try:
        # Parse ratio to get quantities
        ratio_parts = ratio.split(':')
        put_quantity = int(ratio_parts[0])
        call_quantity = int(ratio_parts[1])
        
        # Fetch fresh option quotes from yfinance
        stock = yf.Ticker(ticker)
        opt_chain = stock.option_chain(expiration)
        
        # Get put option data
        puts = opt_chain.puts
        put_row = puts[puts['strike'] == put_strike]
        
        if put_row.empty:
            return {"success": False, "error": f"Put option with strike ${put_strike:.2f} not found for expiration {expiration}"}
        
        put_row = put_row.iloc[0]
        put_bid = put_row.get('bid')
        put_ask = put_row.get('ask')
        
        if pd.isna(put_bid) or pd.isna(put_ask) or put_bid <= 0 or put_ask <= 0:
            return {"success": False, "error": f"Put option with strike ${put_strike:.2f} has missing or invalid bid/ask prices"}
        
        # Get call option data
        calls = opt_chain.calls
        call_row = calls[calls['strike'] == call_strike]
        
        if call_row.empty:
            return {"success": False, "error": f"Call option with strike ${call_strike:.2f} not found for expiration {expiration}"}
        
        call_row = call_row.iloc[0]
        call_bid = call_row.get('bid')
        call_ask = call_row.get('ask')
        
        if pd.isna(call_bid) or pd.isna(call_ask) or call_bid <= 0 or call_ask <= 0:
            return {"success": False, "error": f"Call option with strike ${call_strike:.2f} has missing or invalid bid/ask prices"}
        
        # Calculate average of bid/ask for both options
        put_option_quote = (float(put_bid) + float(put_ask)) / 2.0
        call_option_quote = (float(call_bid) + float(call_ask)) / 2.0
        
        # Calculate net cost (entry price)
        # For risk reversal: we receive put premium, pay call premium
        # Use average of bid/ask for both options for consistency
        # Net cost = (call_option_quote * call_quantity) - (put_option_quote * put_quantity)
        entry_price = (call_option_quote * call_quantity) - (put_option_quote * put_quantity)
        
        # Parse expiration date
        exp_date = datetime.strptime(expiration, '%Y-%m-%d').date()
        
        # Create RR watchlist entry
        with Session(engine) as session:
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
                expired_yn="N"
            )
            
            session.add(rr_entry)
            session.commit()
            session.refresh(rr_entry)
            
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


def get_all_rr_watchlist_entries() -> list[RRWatchlist]:
    """Get all entries from RR watchlist."""
    with Session(engine) as session:
        statement = select(RRWatchlist).order_by(RRWatchlist.date_added.desc())
        entries = session.exec(statement).all()
        return list(entries)


def get_latest_net_cost(rr_uuid: UUID) -> Optional[Decimal]:
    """Get the latest current value from rr_history for a given RR entry."""
    with Session(engine) as session:
        statement = select(RRHistory).where(
            RRHistory.rr_uuid == rr_uuid
        ).order_by(RRHistory.history_date.desc()).limit(1)
        latest = session.exec(statement).first()
        return latest.curr_value if latest else None


def get_rr_watchlist_entry(rr_uuid: UUID) -> Optional[RRWatchlist]:
    """Get a specific RR watchlist entry by UUID."""
    with Session(engine) as session:
        return session.get(RRWatchlist, rr_uuid)


def delete_rr_watchlist_entry(rr_uuid: UUID) -> bool:
    """
    Delete an RR watchlist entry and all associated history.
    Returns True if successful, False otherwise.
    """
    try:
        with Session(engine) as session:
            rr_entry = session.get(RRWatchlist, rr_uuid)
            if not rr_entry:
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


def get_rr_history(rr_uuid: UUID) -> list[RRHistory]:
    """Get history for a specific RR watchlist entry."""
    with Session(engine) as session:
        statement = select(RRHistory).where(
            RRHistory.rr_uuid == rr_uuid
        ).order_by(RRHistory.history_date.asc())
        entries = session.exec(statement).all()
        return list(entries)
