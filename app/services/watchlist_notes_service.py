"""Service layer for managing watchlist stock notes."""
from sqlmodel import Session, select
from app.database import engine
from app.models.watchlist_stock_notes import WatchlistStockNote
from app.models.watchlist import WatchList, WatchListStock
from app.utils.type_helpers import to_str
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
import logging

logger = logging.getLogger(__name__)

MAX_NOTE_LENGTH = 500


def _verify_watchlist_ownership(session: Session, watchlist_id: str, account_id: str) -> WatchList:
    """
    Verify that the account owns the watchlist.

    Args:
        session: Database session
        watchlist_id: Watchlist ID
        account_id: Account ID

    Returns:
        WatchList object if access is allowed

    Raises:
        ValueError: If watchlist not found or access denied
    """
    watchlist = session.get(WatchList, watchlist_id)
    if not watchlist:
        raise ValueError(f"Watchlist with ID {watchlist_id} not found")

    if watchlist.account_id:
        if not account_id or to_str(watchlist.account_id) != account_id:
            raise ValueError(f"Access denied: Watchlist with ID {watchlist_id} belongs to another account")

    return watchlist


def _verify_stock_in_watchlist(session: Session, watchlist_id: str, ticker: str) -> None:
    """
    Verify that the stock is in the watchlist.

    Args:
        session: Database session
        watchlist_id: Watchlist ID
        ticker: Stock ticker

    Raises:
        ValueError: If stock is not in the watchlist
    """
    statement = select(WatchListStock).where(
        WatchListStock.watchlist_id == watchlist_id,
        WatchListStock.ticker == ticker.upper()
    )
    stock = session.exec(statement).first()
    if not stock:
        raise ValueError(f"Stock {ticker} is not in watchlist {watchlist_id}")


def create_or_update_note(
    watchlist_id: str,
    ticker: str,
    note_text: str,
    account_id: str
) -> WatchlistStockNote:
    """
    Create or update a note for a stock in a watchlist.

    Args:
        watchlist_id: UUID of the watchlist
        ticker: Stock ticker symbol
        note_text: The note text (max 500 characters)
        account_id: Account ID of the user

    Returns:
        The created or updated WatchlistStockNote

    Raises:
        ValueError: If note is too long, watchlist not found, or access denied
    """
    wl_id = to_str(watchlist_id)
    acc_id = to_str(account_id)
    ticker = ticker.upper()
    note_text = note_text.strip()

    # Validate note length
    if len(note_text) > MAX_NOTE_LENGTH:
        raise ValueError(f"Note cannot exceed {MAX_NOTE_LENGTH} characters")

    with Session(engine) as session:
        # Verify ownership
        _verify_watchlist_ownership(session, wl_id, acc_id)

        # Verify stock is in watchlist
        _verify_stock_in_watchlist(session, wl_id, ticker)

        # Check if note exists
        existing_note = session.get(WatchlistStockNote, (wl_id, ticker))

        if existing_note:
            # Update existing note
            existing_note.note_text = note_text
            existing_note.updated_at = datetime.utcnow()
            session.add(existing_note)
            session.commit()
            session.refresh(existing_note)
            return existing_note
        else:
            # Create new note
            new_note = WatchlistStockNote(
                watchlist_id=wl_id,
                ticker=ticker,
                note_text=note_text,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            session.add(new_note)
            session.commit()
            session.refresh(new_note)
            return new_note


def get_note(
    watchlist_id: str,
    ticker: str,
    account_id: str
) -> Optional[WatchlistStockNote]:
    """
    Get a note for a stock in a watchlist.

    Args:
        watchlist_id: UUID of the watchlist
        ticker: Stock ticker symbol
        account_id: Account ID of the user

    Returns:
        The WatchlistStockNote if found, None otherwise

    Raises:
        ValueError: If watchlist not found or access denied
    """
    wl_id = to_str(watchlist_id)
    acc_id = to_str(account_id)
    ticker = ticker.upper()

    with Session(engine) as session:
        # Verify ownership
        _verify_watchlist_ownership(session, wl_id, acc_id)

        return session.get(WatchlistStockNote, (wl_id, ticker))


def delete_note(
    watchlist_id: str,
    ticker: str,
    account_id: str
) -> bool:
    """
    Delete a note for a stock in a watchlist.

    Args:
        watchlist_id: UUID of the watchlist
        ticker: Stock ticker symbol
        account_id: Account ID of the user

    Returns:
        True if deleted, False if note didn't exist

    Raises:
        ValueError: If watchlist not found or access denied
    """
    wl_id = to_str(watchlist_id)
    acc_id = to_str(account_id)
    ticker = ticker.upper()

    with Session(engine) as session:
        # Verify ownership
        _verify_watchlist_ownership(session, wl_id, acc_id)

        note = session.get(WatchlistStockNote, (wl_id, ticker))
        if note:
            session.delete(note)
            session.commit()
            return True
        return False


def get_all_notes_for_stock(
    ticker: str,
    account_id: str
) -> List[Dict[str, Any]]:
    """
    Get all notes for a stock across all watchlists owned by the user.

    Args:
        ticker: Stock ticker symbol
        account_id: Account ID of the user

    Returns:
        List of dictionaries containing note info with watchlist details
    """
    acc_id = to_str(account_id)
    ticker = ticker.upper()

    with Session(engine) as session:
        # Get all watchlists owned by the user that contain this stock
        statement = select(WatchList).where(WatchList.account_id == acc_id)
        watchlists = session.exec(statement).all()

        # Create lookup for watchlist details
        watchlist_lookup = {wl.watchlist_id: wl for wl in watchlists}
        watchlist_ids = list(watchlist_lookup.keys())

        if not watchlist_ids:
            return []

        # Get all notes for this ticker in user's watchlists
        statement = select(WatchlistStockNote).where(
            WatchlistStockNote.ticker == ticker,
            WatchlistStockNote.watchlist_id.in_(watchlist_ids)
        )
        notes = session.exec(statement).all()

        # Build response with watchlist details
        result = []
        for note in notes:
            watchlist = watchlist_lookup.get(note.watchlist_id)
            result.append({
                "watchlist_id": note.watchlist_id,
                "watchlist_name": watchlist.watchlist_name if watchlist else "Unknown",
                "ticker": note.ticker,
                "note_text": note.note_text,
                "created_at": note.created_at.isoformat() if note.created_at else None,
                "updated_at": note.updated_at.isoformat() if note.updated_at else None
            })

        return result


def get_watchlists_for_stock(
    ticker: str,
    account_id: str
) -> List[Dict[str, Any]]:
    """
    Get all watchlists owned by the user that contain a specific stock.

    Args:
        ticker: Stock ticker symbol
        account_id: Account ID of the user

    Returns:
        List of dictionaries containing watchlist details
    """
    acc_id = to_str(account_id)
    ticker = ticker.upper()

    with Session(engine) as session:
        # Get all watchlists owned by the user
        statement = select(WatchList).where(WatchList.account_id == acc_id)
        watchlists = session.exec(statement).all()

        result = []
        for watchlist in watchlists:
            # Check if stock is in this watchlist
            stock_statement = select(WatchListStock).where(
                WatchListStock.watchlist_id == watchlist.watchlist_id,
                WatchListStock.ticker == ticker
            )
            stock = session.exec(stock_statement).first()

            if stock:
                result.append({
                    "watchlist_id": watchlist.watchlist_id,
                    "watchlist_name": watchlist.watchlist_name
                })

        return result
