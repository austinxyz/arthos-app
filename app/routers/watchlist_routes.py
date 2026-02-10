"""Watchlist-related routes for managing watchlists and their stocks."""
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Path as FPath
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from uuid import UUID
from starlette.templating import Jinja2Templates

# Initialize router
router = APIRouter()

# Initialize templates (shared with main app)
templates = Jinja2Templates(directory="app/templates")


# Pydantic Models
class WatchListCreate(BaseModel):
    watchlist_name: str
    description: Optional[str] = None


class WatchListUpdate(BaseModel):
    watchlist_name: str
    description: Optional[str] = None


class WatchListVisibilityUpdate(BaseModel):
    is_public: bool


class AddStocksRequest(BaseModel):
    tickers: str  # Comma-separated tickers


# Page Routes
@router.get("/watchlists", response_class=HTMLResponse)
async def watchlists_page(request: Request):
    """
    Display list of all watchlists.

    Returns:
        HTML page with list of watchlists
    """
    from app.services import watchlist_service

    account_id_str = request.session.get('account_id')
    account_id = account_id_str  # Use string directly, models handle conversion

    watchlists = watchlist_service.get_all_watchlists(account_id=account_id)
    return templates.TemplateResponse("watchlists.html", {"request": request, "watchlists": watchlists})


@router.get("/public-watchlists", response_class=HTMLResponse)
async def public_watchlists_page(request: Request):
    """
    Display list of all public watchlists (no auth required).

    Returns:
        HTML page with list of public watchlists
    """
    from app.services import watchlist_service
    watchlists = watchlist_service.get_all_public_watchlists()
    return templates.TemplateResponse("public_watchlists.html", {"request": request, "watchlists": watchlists})


@router.get("/create-watchlist")
async def create_watchlist_page(request: Request):
    """
    Display create watchlist page.

    Returns:
        HTML page for creating a new watchlist
    """
    return templates.TemplateResponse("create_watchlist.html", {"request": request})


@router.get("/watchlist/{watchlist_id}", response_class=HTMLResponse)
async def watchlist_details_page(request: Request, watchlist_id: UUID):
    """
    Display watchlist details page with stocks.

    Args:
        watchlist_id: UUID of the watchlist

    Returns:
        HTML page with watchlist details and stocks
    """
    from app.services import watchlist_service

    # Get user from session
    account_id_str = request.session.get('account_id')
    account_id = account_id_str  # Use string directly, models handle conversion

    watchlist = watchlist_service.get_watchlist(watchlist_id, account_id=account_id)
    if not watchlist:
        raise HTTPException(status_code=404, detail="Watchlist not found")

    metrics = watchlist_service.get_watchlist_stocks_with_metrics(watchlist_id, account_id=account_id)
    return templates.TemplateResponse("watchlist_details.html", {
        "request": request,
        "watchlist": watchlist,
        "metrics": metrics,
        "is_owner": True  # Owner viewing their own watchlist
    })


@router.get("/public-watchlist/{watchlist_id}", response_class=HTMLResponse)
async def public_watchlist_details_page(request: Request, watchlist_id: UUID):
    """
    Display public watchlist details page (read-only, no auth required).

    Args:
        watchlist_id: UUID of the watchlist

    Returns:
        HTML page with public watchlist details and stocks
    """
    from app.services import watchlist_service

    try:
        watchlist = watchlist_service.get_public_watchlist(watchlist_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Public watchlist not found")

    # Get metrics (using None for account_id since this is public access)
    metrics = watchlist_service.get_watchlist_stocks_with_metrics(watchlist_id, account_id=None)
    return templates.TemplateResponse("watchlist_details.html", {
        "request": request,
        "watchlist": watchlist,
        "metrics": metrics,
        "is_owner": False,  # Viewing a public watchlist
        "is_public_view": True  # Flag for template to hide edit controls
    })


# API Routes
@router.get("/v1/watchlist")
async def list_watchlists(request: Request):
    """
    List all watchlists.

    Returns:
        JSON response with list of watchlists
    """
    from app.services.watchlist_service import get_all_watchlists

    account_id_str = request.session.get('account_id')
    account_id = account_id_str  # Use string directly, models handle conversion

    watchlists = get_all_watchlists(account_id)
    return {
        "watchlists": [
            {
                "watchlist_id": str(w.watchlist_id),
                "watchlist_name": w.watchlist_name,
                "description": w.description,
                "date_added": w.date_added.isoformat(),
                "date_modified": w.date_modified.isoformat()
            }
            for w in watchlists
        ]
    }


@router.get("/v1/watchlist/{watchlist_id}")
async def get_watchlist(request: Request, watchlist_id: UUID = FPath(...)):
    """
    Get watchlist details.

    Args:
        watchlist_id: UUID of the watchlist

    Returns:
        JSON response with watchlist details and stocks
    """
    from app.services.watchlist_service import get_watchlist, get_watchlist_stocks

    account_id_str = request.session.get('account_id')
    account_id = account_id_str  # Use string directly, models handle conversion

    try:
        watchlist = get_watchlist(watchlist_id, account_id)
        stocks = get_watchlist_stocks(watchlist_id, account_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "watchlist_id": str(watchlist.watchlist_id),
        "watchlist_name": watchlist.watchlist_name,
        "description": watchlist.description,
        "date_added": watchlist.date_added.isoformat(),
        "date_modified": watchlist.date_modified.isoformat(),
        "stocks": [
            {
                "ticker": s.ticker,
                "date_added": s.date_added.isoformat()
            }
            for s in stocks
        ]
    }


@router.post("/v1/watchlist")
async def create_watchlist(request: Request, watchlist: WatchListCreate):
    """
    Create a new watchlist.

    Args:
        request: Request object
        watchlist: WatchList creation request with watchlist_name

    Returns:
        JSON response with created watchlist
    """
    from app.services import watchlist_service

    account_id_str = request.session.get('account_id')
    account_id = account_id_str  # Use string directly, models handle conversion

    if not account_id:
        raise HTTPException(status_code=401, detail="User must be logged in to create a watchlist")

    try:
        new_watchlist = watchlist_service.create_watchlist(
            watchlist_name=watchlist.watchlist_name,
            description=watchlist.description,
            account_id=account_id
        )
        return {
            "watchlist_id": str(new_watchlist.watchlist_id),
            "watchlist_name": new_watchlist.watchlist_name,
            "description": new_watchlist.description,
            "date_added": new_watchlist.date_added.isoformat(),
            "date_modified": new_watchlist.date_modified.isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/v1/watchlist/{watchlist_id}")
async def update_watchlist(request: Request, watchlist_id: UUID = FPath(...), watchlist: WatchListUpdate = None):
    """
    Update watchlist name and/or description.

    Args:
        request: Request object
        watchlist_id: UUID of the watchlist
        watchlist: WatchList update request with watchlist_name and optional description

    Returns:
        JSON response with updated watchlist
    """
    from app.services.watchlist_service import update_watchlist

    account_id_str = request.session.get('account_id')
    account_id = account_id_str  # Use string directly, models handle conversion

    if not account_id:
        raise HTTPException(status_code=401, detail="User must be logged in to update a watchlist")

    if not watchlist:
        raise HTTPException(status_code=400, detail="WatchList name is required")

    try:
        updated_watchlist = update_watchlist(watchlist_id, watchlist.watchlist_name, watchlist.description, account_id)
        if not updated_watchlist:
            raise HTTPException(status_code=404, detail="WatchList not found")

        return {
            "watchlist_id": str(updated_watchlist.watchlist_id),
            "watchlist_name": updated_watchlist.watchlist_name,
            "description": updated_watchlist.description,
            "date_added": updated_watchlist.date_added.isoformat(),
            "date_modified": updated_watchlist.date_modified.isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/v1/watchlist/{watchlist_id}/visibility")
async def update_watchlist_visibility_api(request: Request, watchlist_id: UUID = FPath(...), visibility: WatchListVisibilityUpdate = None):
    """
    Update watchlist visibility (public/private).

    Args:
        request: Request object
        watchlist_id: UUID of the watchlist
        visibility: Visibility update request with is_public boolean

    Returns:
        JSON response with updated watchlist
    """
    from app.services.watchlist_service import update_watchlist_visibility

    account_id_str = request.session.get('account_id')
    account_id = account_id_str  # Use string directly, models handle conversion

    if not account_id:
        raise HTTPException(status_code=401, detail="User must be logged in to update watchlist visibility")

    if visibility is None:
        raise HTTPException(status_code=400, detail="Visibility setting is required")

    try:
        updated_watchlist = update_watchlist_visibility(watchlist_id, visibility.is_public, account_id)
        return {
            "watchlist_id": str(updated_watchlist.watchlist_id),
            "watchlist_name": updated_watchlist.watchlist_name,
            "is_public": updated_watchlist.is_public,
            "date_modified": updated_watchlist.date_modified.isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/v1/watchlist/{watchlist_id}")
async def delete_watchlist_api(watchlist_id: UUID, request: Request):
    """
    Delete a watchlist and all its stocks (cascade delete).

    Args:
        request: Request object
        watchlist_id: UUID of the watchlist

    Returns:
        JSON response with deletion status
    """
    from app.services import watchlist_service
    # Ensure user is logged in
    account_id_str = request.session.get('account_id')
    if not account_id_str:
        raise HTTPException(status_code=401, detail="User must be logged in to delete a watchlist")

    try:
        account_id = account_id_str  # Use string directly
        result = watchlist_service.delete_watchlist(watchlist_id, account_id=account_id)
        if not result:
            raise HTTPException(status_code=404, detail="WatchList not found")
        return {"message": "WatchList deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/v1/watchlist/{watchlist_id}/stocks")
async def add_stocks_to_watchlist(request: Request, watchlist_id: UUID = FPath(...), request_body: AddStocksRequest = None):
    """
    Add stocks to a watchlist. Filters out invalid tickers and returns info about them.

    Args:
        request: Request object
        watchlist_id: UUID of the watchlist
        request_body: Request with comma-separated tickers

    Returns:
        JSON response with added stocks and invalid tickers
    """
    from app.services.watchlist_service import add_stocks_to_watchlist

    account_id_str = request.session.get('account_id')
    account_id = account_id_str  # Use string directly, models handle conversion

    if not account_id:
        raise HTTPException(status_code=401, detail="User must be logged in to add stocks")

    if not request_body or not request_body.tickers:
        raise HTTPException(status_code=400, detail="Tickers are required")

    # Parse tickers
    ticker_list = [t.strip().upper() for t in request_body.tickers.split(',') if t.strip()]

    if not ticker_list:
        raise HTTPException(status_code=400, detail="At least one ticker is required")

    try:
        added_stocks, invalid_tickers = add_stocks_to_watchlist(watchlist_id, ticker_list, account_id)

        # Build response message
        messages = []
        if added_stocks:
            messages.append(f"Added {len(added_stocks)} stock(s) to watchlist")
        if invalid_tickers:
            for invalid_ticker in invalid_tickers:
                messages.append(f"Ticker {invalid_ticker} is invalid")

        response = {
            "message": ". ".join(messages) if messages else "No valid tickers to add",
            "added_stocks": [
                {
                    "ticker": s.ticker,
                    "date_added": s.date_added.isoformat()
                }
                for s in added_stocks
            ],
            "invalid_tickers": invalid_tickers
        }

        return response
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/v1/watchlist/{watchlist_id}/stocks/{ticker}")
async def remove_stock_from_watchlist_api(watchlist_id: UUID, ticker: str, request: Request):
    """
    Remove a stock from a watchlist.

    Args:
        request: Request object
        watchlist_id: UUID of the watchlist
        ticker: Stock ticker symbol

    Returns:
        JSON response with deletion status
    """
    from app.services import watchlist_service
    # Ensure user is logged in
    account_id_str = request.session.get('account_id')
    if not account_id_str:
        raise HTTPException(status_code=401, detail="User must be logged in to remove stocks")

    try:
        account_id = account_id_str  # Use string directly
        result = watchlist_service.remove_stock_from_watchlist(
            watchlist_id=watchlist_id,
            ticker=ticker,
            account_id=account_id
        )
        if not result:
            raise HTTPException(status_code=404, detail="Stock not found in watchlist")
        return {"message": f"Stock {ticker} removed from watchlist"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
