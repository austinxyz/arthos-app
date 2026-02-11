"""
Risk Reversal (RR) watchlist endpoints for tracking and managing RR strategies.
"""
from fastapi import APIRouter, Request, HTTPException, Path as FPath
from fastapi.responses import HTMLResponse
from starlette.templating import Jinja2Templates
from pathlib import Path as PathLib
from uuid import UUID


router = APIRouter()

# Set up templates directory
templates_dir = PathLib(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@router.get("/rr-list", response_class=HTMLResponse)
async def rr_list_page(request: Request):
    """
    Display RR watchlist page with all Risk Reversal entries.

    Returns:
        HTML page with list of RR watchlist entries
    """
    from app.services import rr_watchlist_service
    # Get user from session
    account_id_str = request.session.get('account_id')
    account_id = account_id_str  # Use string directly, models handle conversion

    rr_entries = rr_watchlist_service.get_all_rr_watchlist_entries(account_id=account_id)

    # Format entries for display
    formatted_entries = []
    for entry in rr_entries:
        # Build legs data for crisp display
        legs = []
        # Put leg (short)
        legs.append({
            'position': 'Short',
            'type': 'Put',
            'strike': float(entry.put_strike),
            'qty': entry.put_quantity
        })
        # Call leg (long)
        legs.append({
            'position': 'Long',
            'type': 'Call',
            'strike': float(entry.call_strike),
            'qty': entry.call_quantity
        })
        # Short call for Collar
        if entry.ratio == 'Collar' and entry.short_call_strike:
            legs.append({
                'position': 'Short',
                'type': 'Call',
                'strike': float(entry.short_call_strike),
                'qty': entry.short_call_quantity or 1
            })

        # Get latest net cost from history
        latest_net_cost = rr_watchlist_service.get_latest_net_cost(entry.id)
        current_price = float(latest_net_cost) if latest_net_cost is not None else None

        # Calculate Change and Change %
        entry_price = float(entry.entry_price)
        if current_price is not None:
            change = current_price - entry_price
            change_pct = (change / abs(entry_price) * 100) if entry_price != 0 else None
        else:
            change = None
            change_pct = None

        # Get current stock price from the database
        from app.models.stock_price import StockPrice
        from sqlmodel import Session, select
        from app.database import engine

        current_stock_price = None
        stock_price_change = None
        stock_price_change_pct = None

        with Session(engine) as session:
            statement = select(StockPrice).where(
                StockPrice.ticker == entry.ticker
            ).order_by(StockPrice.price_date.desc()).limit(1)
            latest_stock_price = session.exec(statement).first()
            if latest_stock_price:
                current_stock_price = float(latest_stock_price.close_price)
                entry_stock_price = float(entry.stock_price)
                stock_price_change = current_stock_price - entry_stock_price
                if entry_stock_price != 0:
                    stock_price_change_pct = (stock_price_change / entry_stock_price) * 100

        formatted_entries.append({
            'id': entry.id,
            'ticker': entry.ticker,
            'legs': legs,
            'ratio': entry.ratio,
            'stock_price': float(entry.stock_price),
            'current_stock_price': current_stock_price,
            'stock_price_change': stock_price_change,
            'stock_price_change_pct': stock_price_change_pct,
            'date_added': entry.date_added,
            'entry_price': entry_price,
            'current_price': current_price,
            'change': change,
            'change_pct': change_pct,
            'call_option_quote': float(entry.call_option_quote),
            'put_option_quote': float(entry.put_option_quote),
            'short_call_option_quote': float(entry.short_call_option_quote) if entry.short_call_option_quote else None,
            'expiration': entry.expiration
        })

    return templates.TemplateResponse("rr_list.html", {
        "request": request,
        "entries": formatted_entries
    })


@router.get("/rr-details/{rr_uuid}")
async def rr_details_page(request: Request, rr_uuid: UUID = FPath(...)):
    """
    Display RR details page with chart and history table.

    Args:
        rr_uuid: UUID of the RR watchlist entry

    Returns:
        HTML page with RR details, chart, and history
    """
    from app.services.rr_watchlist_service import get_rr_watchlist_entry, get_rr_history
    from datetime import date

    account_id_str = request.session.get('account_id')
    account_id = account_id_str  # Use string directly, models handle conversion

    entry = get_rr_watchlist_entry(rr_uuid, account_id)

    if not entry:
        raise HTTPException(status_code=404, detail="RR entry not found")

    # Get history
    history = get_rr_history(rr_uuid)

    # Format entry for display
    expiration_str = entry.expiration.strftime('%b %Y')
    if entry.ratio == 'Collar':
        short_call_strike = float(entry.short_call_strike) if entry.short_call_strike else 0
        short_call_qty = entry.short_call_quantity or 1
        contract = (
            f"{entry.ticker} {expiration_str} sell {entry.put_quantity} ${entry.put_strike:.2f} put, "
            f"buy {entry.call_quantity} ${entry.call_strike:.2f} call, "
            f"sell {short_call_qty} ${short_call_strike:.2f} call"
        )
    elif entry.ratio == '1:2':
        contract = f"{entry.ticker} {expiration_str} sell {entry.put_quantity} ${entry.put_strike:.2f} put and buy {entry.call_quantity} ${entry.call_strike:.2f} calls"
    else:
        contract = f"{entry.ticker} {expiration_str} sell {entry.put_quantity} ${entry.put_strike:.2f} put and buy {entry.call_quantity} ${entry.call_strike:.2f} call"

    # Format history for chart
    chart_data = []
    table_data = []
    is_collar = entry.ratio == 'Collar'
    for hist in history:
        chart_data.append({
            'x': hist.history_date.isoformat(),
            'y': float(hist.curr_value)
        })
        row_data = {
            'history_date': hist.history_date,
            'curr_value': float(hist.curr_value),
            'call_price': float(hist.call_price) if hist.call_price else None,
            'put_price': float(hist.put_price) if hist.put_price else None
        }
        if is_collar:
            row_data['short_call_price'] = float(hist.short_call_price) if hist.short_call_price else None
        table_data.append(row_data)

    # Sort by date
    chart_data.sort(key=lambda x: x['x'])
    table_data.sort(key=lambda x: x['history_date'])

    # Get latest prices from most recent history entry
    latest_call_price = None
    latest_put_price = None
    latest_short_call_price = None
    current_value = None
    if table_data:
        latest = table_data[-1]  # Most recent after sorting
        latest_call_price = latest.get('call_price')
        latest_put_price = latest.get('put_price')
        latest_short_call_price = latest.get('short_call_price') if is_collar else None
        current_value = latest.get('curr_value')

    # Calculate % changes for legs
    entry_call_quote = float(entry.call_option_quote)
    entry_put_quote = float(entry.put_option_quote)
    entry_price = float(entry.entry_price)

    call_change_pct = None
    if latest_call_price is not None and entry_call_quote != 0:
        call_change_pct = ((latest_call_price - entry_call_quote) / entry_call_quote) * 100

    put_change_pct = None
    if latest_put_price is not None and entry_put_quote != 0:
        put_change_pct = ((latest_put_price - entry_put_quote) / entry_put_quote) * 100

    short_call_change_pct = None
    if is_collar and latest_short_call_price is not None:
        entry_short_call_quote = float(entry.short_call_option_quote) if entry.short_call_option_quote else 0
        if entry_short_call_quote != 0:
            short_call_change_pct = ((latest_short_call_price - entry_short_call_quote) / entry_short_call_quote) * 100

    # Calculate overall value change
    value_change = None
    value_change_pct = None
    if current_value is not None:
        value_change = current_value - entry_price
        if entry_price != 0:
            value_change_pct = (value_change / abs(entry_price)) * 100

    # Get current stock price and calculate stock price change
    from app.models.stock_price import StockPrice
    from sqlmodel import Session, select
    from app.database import engine

    current_stock_price = None
    stock_price_change = None
    stock_price_change_pct = None
    entry_stock_price = float(entry.stock_price)

    with Session(engine) as session:
        statement = select(StockPrice).where(
            StockPrice.ticker == entry.ticker
        ).order_by(StockPrice.price_date.desc()).limit(1)
        latest_stock_price = session.exec(statement).first()
        if latest_stock_price:
            current_stock_price = float(latest_stock_price.close_price)
            stock_price_change = current_stock_price - entry_stock_price
            if entry_stock_price != 0:
                stock_price_change_pct = (stock_price_change / entry_stock_price) * 100

    # Build entry dict with collar fields if applicable
    entry_dict = {
        'id': entry.id,
        'contract': contract,
        'ticker': entry.ticker,
        'call_strike': float(entry.call_strike),
        'call_quantity': entry.call_quantity,
        'put_strike': float(entry.put_strike),
        'put_quantity': entry.put_quantity,
        'stock_price': float(entry.stock_price),
        'date_added': entry.date_added,
        'entry_price': entry_price,
        'call_option_quote': entry_call_quote,
        'put_option_quote': entry_put_quote,
        'expiration': entry.expiration,
        'ratio': entry.ratio,
        'expired_yn': entry.expired_yn,
        # Current prices
        'current_call_price': latest_call_price,
        'current_put_price': latest_put_price,
        'call_change_pct': call_change_pct,
        'put_change_pct': put_change_pct,
        # Summary values
        'current_value': current_value,
        'value_change': value_change,
        'value_change_pct': value_change_pct,
        # Current stock price
        'current_stock_price': current_stock_price,
        'stock_price_change': stock_price_change,
        'stock_price_change_pct': stock_price_change_pct
    }

    # Add collar-specific fields
    if is_collar:
        entry_dict['short_call_strike'] = float(entry.short_call_strike) if entry.short_call_strike else None
        entry_dict['short_call_quantity'] = entry.short_call_quantity
        entry_dict['short_call_option_quote'] = float(entry.short_call_option_quote) if entry.short_call_option_quote else None
        entry_dict['collar_type'] = entry.collar_type
        entry_dict['current_short_call_price'] = latest_short_call_price
        entry_dict['short_call_change_pct'] = short_call_change_pct

    return templates.TemplateResponse("rr_details.html", {
        "request": request,
        "entry": entry_dict,
        "chart_data": chart_data,
        "table_data": table_data,
        "is_collar": is_collar
    })


@router.post("/api/rr-watchlist/save")
async def save_rr_to_watchlist_api(request: Request):
    """Save a Risk Reversal strategy to the watchlist."""
    from app.services.rr_watchlist_service import save_rr_to_watchlist
    from fastapi import Form

    try:
        data = await request.json()
        ticker = data.get('ticker')
        expiration = data.get('expiration')
        put_strike = float(data.get('put_strike'))
        call_strike = float(data.get('call_strike'))
        ratio = data.get('ratio', '1:1')
        current_price = float(data.get('current_price'))

        # Collar-specific fields (optional)
        sold_call_strike = data.get('sold_call_strike')
        if sold_call_strike is not None:
            sold_call_strike = float(sold_call_strike)
        collar_type = data.get('collar_type')

        account_id_str = request.session.get('account_id')
        account_id = account_id_str  # Use string directly, models handle conversion

        if not account_id:
             return {"success": False, "error": "User must be logged in to save strategies"}

        if not all([ticker, expiration, put_strike, call_strike, current_price]):
            return {"success": False, "error": "Missing required fields"}

        result = save_rr_to_watchlist(
            ticker=ticker,
            expiration=expiration,
            put_strike=put_strike,
            call_strike=call_strike,
            ratio=ratio,
            current_price=current_price,
            sold_call_strike=sold_call_strike,
            collar_type=collar_type,
            account_id=account_id
        )

        return result

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": f"Error: {str(e)}"}


@router.delete("/api/rr-watchlist/delete/{rr_uuid}")
async def delete_rr_watchlist_api(request: Request, rr_uuid: UUID = FPath(...)):
    """Delete a Risk Reversal watchlist entry and all associated history."""
    from app.services.rr_watchlist_service import delete_rr_watchlist_entry

    try:
        account_id_str = request.session.get('account_id')
        account_id = account_id_str  # Use string directly, models handle conversion

        if not account_id:
             return {"success": False, "error": "User must be logged in to delete strategies"}

        success = delete_rr_watchlist_entry(rr_uuid, account_id)
        if success:
            return {"success": True, "message": "Risk Reversal entry deleted successfully"}
        else:
            return {"success": False, "error": "Entry not found or could not be deleted"}
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"success": False, "error": f"Error: {str(e)}"}
