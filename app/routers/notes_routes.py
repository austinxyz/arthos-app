"""
Stock notes API endpoints for managing user notes on stocks within watchlists.
"""
from fastapi import APIRouter, Request, HTTPException, Path as FPath
from pydantic import BaseModel
from uuid import UUID


router = APIRouter()


# Stock Notes API Models
class StockNoteCreate(BaseModel):
    note_text: str


# Stock Notes API Endpoints
@router.get("/v1/stock/{ticker}/notes")
async def get_stock_notes(request: Request, ticker: str = FPath(...)):
    """
    Get all notes for a stock across all watchlists owned by the user.

    Args:
        request: Request object
        ticker: Stock ticker symbol

    Returns:
        JSON response with list of notes and watchlists containing this stock
    """
    from app.services import watchlist_notes_service

    account_id_str = request.session.get('account_id')

    if not account_id_str:
        # Return empty response for unauthenticated users
        return {
            "notes": [],
            "watchlists": []
        }

    try:
        notes = watchlist_notes_service.get_all_notes_for_stock(ticker, account_id_str)
        watchlists = watchlist_notes_service.get_watchlists_for_stock(ticker, account_id_str)
        return {
            "notes": notes,
            "watchlists": watchlists
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching notes: {str(e)}")


@router.put("/v1/watchlist/{watchlist_id}/stocks/{ticker}/note")
async def create_or_update_stock_note(
    request: Request,
    watchlist_id: UUID = FPath(...),
    ticker: str = FPath(...),
    note: StockNoteCreate = None
):
    """
    Create or update a note for a stock in a watchlist.

    Args:
        request: Request object
        watchlist_id: UUID of the watchlist
        ticker: Stock ticker symbol
        note: Note creation request with note_text

    Returns:
        JSON response with the created/updated note
    """
    from app.services import watchlist_notes_service

    account_id_str = request.session.get('account_id')
    if not account_id_str:
        raise HTTPException(status_code=401, detail="User must be logged in to create notes")

    if not note or not note.note_text:
        raise HTTPException(status_code=400, detail="Note text is required")

    try:
        result = watchlist_notes_service.create_or_update_note(
            watchlist_id=str(watchlist_id),
            ticker=ticker,
            note_text=note.note_text,
            account_id=account_id_str
        )
        return {
            "watchlist_id": result.watchlist_id,
            "ticker": result.ticker,
            "note_text": result.note_text,
            "created_at": result.created_at.isoformat() if result.created_at else None,
            "updated_at": result.updated_at.isoformat() if result.updated_at else None
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/v1/watchlist/{watchlist_id}/stocks/{ticker}/note")
async def delete_stock_note(
    request: Request,
    watchlist_id: UUID = FPath(...),
    ticker: str = FPath(...)
):
    """
    Delete a note for a stock in a watchlist.

    Args:
        request: Request object
        watchlist_id: UUID of the watchlist
        ticker: Stock ticker symbol

    Returns:
        JSON response with deletion status
    """
    from app.services import watchlist_notes_service

    account_id_str = request.session.get('account_id')
    if not account_id_str:
        raise HTTPException(status_code=401, detail="User must be logged in to delete notes")

    try:
        deleted = watchlist_notes_service.delete_note(
            watchlist_id=str(watchlist_id),
            ticker=ticker,
            account_id=account_id_str
        )
        if deleted:
            return {"message": f"Note for {ticker} deleted from watchlist"}
        else:
            return {"message": f"No note found for {ticker} in watchlist"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
