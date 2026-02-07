"""FastAPI application for Arthos investment analysis."""
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Query, Path as FPath
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from fastapi.responses import HTMLResponse
from pathlib import Path
from uuid import UUID
from app.services.stock_price_service import get_stock_metrics_from_db
from app.database import create_db_and_tables
from pydantic import BaseModel
import logging
import os
import json
import datetime


class JSONFormatter(logging.Formatter):
    """JSON formatter for Railway production logging."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


# Configure logging for both local and production (Railway)
# Set LOG_LEVEL environment variable to 'DEBUG' for detailed logs, defaults to 'INFO'
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

# Check if running in Railway (RAILWAY_ENVIRONMENT or RAILWAY_SERVICE_NAME is set)
is_railway = os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RAILWAY_SERVICE_NAME')

if is_railway:
    # Production (Railway): Use JSON format for proper log parsing
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        handlers=[handler],
        force=True  # Override any existing configuration
    )
else:
    # Local development: Use human-readable format
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(levelname)s: %(name)s - %(message)s'
    )

logger = logging.getLogger(__name__)
logger.info(f"Logging configured at {log_level} level (JSON={is_railway})")

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, skip loading .env file
    pass



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for FastAPI app startup and shutdown."""
    # Startup
    create_db_and_tables()
    
    # Start the scheduler for fetching stock data every 60 minutes
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Attempting to start scheduler...")
        
        from app.services.scheduler_service import start_scheduler
        start_scheduler()
        
        logger.info("✓ Scheduler initialization completed successfully")
        print("✓ Scheduler started for fetching stock data every 60 minutes")
    except Exception as e:
        # Don't crash startup if scheduler fails
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"✗ Failed to start scheduler: {e}")
        logger.error(f"Stack trace:\n{traceback.format_exc()}")
        print(f"⚠ Warning: Could not start scheduler: {e}")
        print("Application will continue without scheduler")
    
    yield
    
    # Shutdown
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Attempting to stop scheduler...")
        
        from app.services.scheduler_service import stop_scheduler
        stop_scheduler()
        
        logger.info("✓ Scheduler stopped successfully")
        print("✓ Scheduler stopped")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Could not stop scheduler: {e}")
        print(f"⚠ Warning: Could not stop scheduler: {e}")


# Initialize FastAPI app with lifespan handler
app = FastAPI(
    title="Arthos",
    description="Investment Analysis Platform",
    lifespan=lifespan
)

# Admin Access Control Middleware
# Protects /debug/* endpoints - only allows access to ADMIN_EMAIL
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")


class AdminAccessMiddleware(BaseHTTPMiddleware):
    """Middleware to protect admin-only routes like /debug/*."""

    async def dispatch(self, request: Request, call_next):
        # Check if this is a protected route
        if request.url.path.startswith("/debug"):
            # Get user from session
            user = request.session.get("user") if hasattr(request, "session") else None

            # Check if user is logged in and has admin email
            if not user:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Admin access required. Please log in."}
                )

            user_email = user.get("email")
            if not ADMIN_EMAIL:
                # If ADMIN_EMAIL not configured, deny all access to debug
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Admin access not configured."}
                )

            if user_email != ADMIN_EMAIL:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Admin access required. You are not authorized."}
                )

        return await call_next(request)


# Add Admin Access Middleware (must be added before SessionMiddleware)
app.add_middleware(AdminAccessMiddleware)

# Add Session Middleware
from starlette.middleware.sessions import SessionMiddleware
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400*30, same_site='lax', https_only=False)

# Include Routers
from app.routers import auth
app.include_router(auth.router)

# Set up templates directory
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Mount static files (for CSS, JS, images, etc.)
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def home(request: Request):
    """Homepage route."""
    from app.services.watchlist_service import get_top_movers

    account_id_str = request.session.get('account_id')

    try:
        top_movers = get_top_movers(limit=5, account_id=account_id_str)
    except Exception as e:
        print(f"Error fetching top movers: {e}")
        top_movers = {'winners': [], 'losers': [], 'is_user_data': False}

    return templates.TemplateResponse("index.html", {
        "request": request,
        "winners": top_movers['winners'],
        "losers": top_movers['losers'],
        "is_user_data": top_movers.get('is_user_data', False)
    })


@app.get("/portfolios", response_class=HTMLResponse)
async def portfolios_page(request: Request):
    """
    Display portfolios page (placeholder).

    Returns:
        HTML page for portfolios (coming soon)
    """
    return templates.TemplateResponse("portfolios.html", {"request": request})


@app.get("/watchlists", response_class=HTMLResponse)
async def watchlists_page(request: Request):
    """
    Display list of all watchlists.

    Returns:
        HTML page with list of watchlists
    """
    from app.services import watchlist_service
    # Get user from session
    account_id_str = request.session.get('account_id')
    account_id = account_id_str  # Use string directly, models handle conversion
    
    watchlists = watchlist_service.get_all_watchlists(account_id=account_id)
    return templates.TemplateResponse("watchlists.html", {"request": request, "watchlists": watchlists})


@app.get("/public-watchlists", response_class=HTMLResponse)
async def public_watchlists_page(request: Request):
    """
    Display list of all public watchlists (no auth required).
    
    Returns:
        HTML page with list of public watchlists
    """
    from app.services import watchlist_service
    watchlists = watchlist_service.get_all_public_watchlists()
    return templates.TemplateResponse("public_watchlists.html", {"request": request, "watchlists": watchlists})


@app.get("/create-watchlist")
async def create_watchlist_page(request: Request):
    """
    Display create watchlist page.
    
    Returns:
        HTML page for creating a new watchlist
    """
    return templates.TemplateResponse("create_watchlist.html", {"request": request})


@app.get("/rr-list", response_class=HTMLResponse)
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


@app.get("/rr-details/{rr_uuid}")
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


@app.get("/watchlist/{watchlist_id}", response_class=HTMLResponse)
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
        
    # Check ownership if needed (service layer handles this logic mostly, but good to be consistent)
    # The service.get_watchlist already checks ownership if account_id is passed, 
    # but for UI we might want to handle display logic differently? 
    # For now relying on service layer.
    
    metrics = watchlist_service.get_watchlist_stocks_with_metrics(watchlist_id, account_id=account_id)
    return templates.TemplateResponse("watchlist_details.html", {
        "request": request, 
        "watchlist": watchlist, 
        "metrics": metrics,
        "is_owner": True  # Owner viewing their own watchlist
    })


@app.get("/public-watchlist/{watchlist_id}", response_class=HTMLResponse)
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


@app.get("/stock/{ticker}")
async def stock_detail(request: Request, ticker: str = FPath(...)):
    """
    Display stock detail page with candlestick chart.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        HTML page with stock chart and metrics
    """
    from app.services.stock_chart_service import get_stock_chart_data
    from app.services.stock_price_service import get_stock_metrics_from_db
    
    ticker = ticker.strip().upper()
    
    try:
        # Get chart data (reads from stock_price table)
        chart_data = get_stock_chart_data(ticker)
        
        # Get metrics for display (reads from stock_price table)
        metrics = get_stock_metrics_from_db(ticker)
        
        # Format dividend yield for display
        if metrics.get('dividend_yield') is not None:
            metrics['dividend_yield_formatted'] = f"{metrics['dividend_yield']:.2f}%"
        else:
            metrics['dividend_yield_formatted'] = "N/A"
        
        # Format earnings date for display
        if metrics.get('next_earnings_date'):
            from datetime import date
            earnings_date = metrics['next_earnings_date']
            if isinstance(earnings_date, date):
                metrics['next_earnings_date_formatted'] = earnings_date.strftime('%b %d, %Y')
            else:
                metrics['next_earnings_date_formatted'] = str(earnings_date)
        else:
            metrics['next_earnings_date_formatted'] = None
        
        # Format dividend date for display
        if metrics.get('next_dividend_date'):
            from datetime import date
            dividend_date = metrics['next_dividend_date']
            if isinstance(dividend_date, date):
                metrics['next_dividend_date_formatted'] = dividend_date.strftime('%b %d, %Y')
            else:
                metrics['next_dividend_date_formatted'] = str(dividend_date)
        else:
            metrics['next_dividend_date_formatted'] = None
        
        # Get options data with error handling
        # First try cached data, then fall back to computing on-demand
        covered_calls = []
        risk_reversals = {}
        min_distance_rr = None
        options_updated_at = None

        try:
            from app.services.options_strategy_cache_service import (
                get_cached_covered_calls,
                get_cached_risk_reversals
            )

            # Try to get cached covered calls (no auto-compute on cache miss to save API calls)
            try:
                covered_calls = get_cached_covered_calls(ticker)

                if covered_calls:
                    print(f"Using {len(covered_calls)} cached covered calls for {ticker}")
                else:
                    print(f"No cached covered calls for {ticker} - use Force Refresh or wait for scheduled update")
                    
            except Exception as e:
                print(f"Error getting covered call returns for {ticker}: {str(e)}")
                import traceback
                traceback.print_exc()
                covered_calls = []

            # Try to get cached risk reversals (no auto-compute on cache miss to save API calls)
            try:
                risk_reversals = get_cached_risk_reversals(ticker)

                if risk_reversals:
                    print(f"Using cached risk reversals for {ticker} ({len(risk_reversals)} expirations)")
                else:
                    print(f"No cached risk reversals for {ticker} - use Force Refresh or wait for scheduled update")

                # Determine last updated timestamp
                if covered_calls and len(covered_calls) > 0:
                     # covered_calls is a list of objects (CachedCoveredCall)
                     # accessing attribute directly
                     try:
                        options_updated_at = covered_calls[0].computed_at
                     except (AttributeError, IndexError):
                        pass
                
                if not options_updated_at and risk_reversals:
                    # risk_reversals is a dict {date: [list of strategy dicts]}
                    # The strategy objects in the list are dicts (from to_dict() probably?) 
                    # status check: get_cached_risk_reversals returns a dict where values are lists of DICTIONARIES (not objects)
                    # Let's verify this in options_strategy_cache_service.py if needed, 
                    # but typically we convert to dict for template.
                    # Wait, get_cached_covered_calls returns list of SQLModel objects usually.
                    # Let's check get_cached_risk_reversals implementation.
                    # Assuming it might be objects or dicts. logic below handles both safely.
                    try:
                        first_date = next(iter(risk_reversals))
                        first_list = risk_reversals[first_date]
                        if first_list:
                            first_item = first_list[0]
                            # Check if it's a dict or object
                            if isinstance(first_item, dict):
                                options_updated_at = first_item.get('computed_at')
                            else:
                                options_updated_at = getattr(first_item, 'computed_at', None)
                    except (StopIteration, IndexError, AttributeError):
                        pass
                
                # Calculate minimum distance from current price to closest strike (put or call) for highlighting
                min_distance_rr = None
                if risk_reversals and metrics['current_price'] and metrics['current_price'] > 0:
                    for expiration, strategies in risk_reversals.items():
                        for strategy in strategies:
                            # Calculate distance for both put and call strikes, use the minimum
                            distances = []
                            if strategy.get('put_strike'):
                                put_strike = strategy['put_strike']
                                if put_strike > metrics['current_price']:
                                    distances.append(put_strike - metrics['current_price'])
                                else:
                                    distances.append(metrics['current_price'] - put_strike)
                            if strategy.get('call_strike'):
                                call_strike = strategy['call_strike']
                                if call_strike > metrics['current_price']:
                                    distances.append(call_strike - metrics['current_price'])
                                else:
                                    distances.append(metrics['current_price'] - call_strike)

                            if distances:
                                min_strategy_distance = min(distances)
                                if min_distance_rr is None or min_strategy_distance < min_distance_rr:
                                    min_distance_rr = min_strategy_distance
            except Exception as e:
                print(f"Error calculating risk reversal strategies for {ticker}: {str(e)}")
                import traceback
                traceback.print_exc()
                risk_reversals = {}
                min_distance_rr = None
        except Exception as e:
            # If options data fails, continue without it
            print(f"Error fetching options data for {ticker}: {str(e)}")
            import traceback
            traceback.print_exc()
            covered_calls = []
            risk_reversals = {}
            min_distance_rr = None
            options_updated_at = None

        # Get stock notes for user
        stock_notes = []
        stock_watchlists = []
        saved_rr_keys = set()
        account_id_str = request.session.get('account_id')
        if account_id_str:
            try:
                from app.services import watchlist_notes_service
                stock_notes = watchlist_notes_service.get_all_notes_for_stock(ticker, account_id_str)
                stock_watchlists = watchlist_notes_service.get_watchlists_for_stock(ticker, account_id_str)
            except Exception as e:
                print(f"Error fetching notes for {ticker}: {str(e)}")
                stock_notes = []
                stock_watchlists = []

            # Get saved RR combinations for this ticker
            try:
                from app.services.rr_watchlist_service import get_saved_rr_keys_for_ticker
                saved_rr_keys = get_saved_rr_keys_for_ticker(ticker, account_id_str)
            except Exception as e:
                print(f"Error fetching saved RR keys for {ticker}: {str(e)}")
                saved_rr_keys = set()

        return templates.TemplateResponse("stock_detail.html", {
            "request": request,
            "ticker": ticker,
            "chart_data": chart_data,
            "metrics": metrics,
            "covered_calls": covered_calls,
            "risk_reversals": risk_reversals,
            "current_price": metrics['current_price'],
            "min_distance_rr": min_distance_rr,
            "options_updated_at": options_updated_at,
            "stock_notes": stock_notes,
            "stock_watchlists": stock_watchlists,
            "saved_rr_keys": saved_rr_keys
        })
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching stock data: {str(e)}")


@app.post("/stock/{ticker}/refresh")
async def refresh_stock_data_endpoint(request: Request, ticker: str = FPath(...)):
    """
    Force refresh all data for a specific ticker.

    Uses the unified refresh_stock_data function that:
    1. Clears the options cache
    2. Fetches fresh stock price data
    3. Recalculates trading metrics (SMAs, signals, IV)
    4. Pre-calculates option strategies (Risk Reversal, Covered Calls)
    5. Refreshes LLM insights

    This is the same code path used by the scheduler and debug page Force Refresh.
    """
    from app.services.stock_price_service import refresh_stock_data
    from app.services import insights_service

    ticker = ticker.strip().upper()

    try:
        print(f"Force refresh requested for {ticker} from stock detail page")
        result = refresh_stock_data(ticker, clear_cache=True)

        # Also refresh insights
        insights_result = insights_service.get_insights(ticker, force_refresh=True)
        insights_refreshed = insights_result.get("status") == "available"

        if result.get("success"):
            return {
                "success": True,
                "message": f"Refreshed {ticker}: {result['price_records']} prices, "
                           f"{result['rr_strategies']} RR, {result['cc_strategies']} CC"
                           f"{', insights updated' if insights_refreshed else ''}",
                "details": result,
                "insights_refreshed": insights_refreshed
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Unknown error during refresh")
            }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"Error refreshing data: {str(e)}"
        }
@app.post("/api/rr-watchlist/save")
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


@app.delete("/api/rr-watchlist/delete/{rr_uuid}")
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


@app.get("/results")
async def results(request: Request, tickers: str = Query(..., description="Comma-separated stock tickers")):
    """
    Display stock metrics results page.
    
    Args:
        tickers: Comma-separated list of stock ticker symbols
        
    Returns:
        HTML page with stock metrics in a DataTable
    """
    from app.services.stock_service import get_multiple_stock_metrics
    
    if not tickers or not tickers.strip():
        raise HTTPException(status_code=400, detail="At least one ticker symbol is required")
    
    # Parse tickers
    from app.services.ticker_validator import validate_ticker_list
    raw_ticker_list = [t.strip().upper() for t in tickers.split(',') if t.strip()]
    
    if not raw_ticker_list:
        raise HTTPException(status_code=400, detail="At least one valid ticker symbol is required")
    
    # Validate ticker formats
    valid_tickers, invalid_tickers = validate_ticker_list(raw_ticker_list)
    
    if invalid_tickers:
        error_msg = f"Invalid ticker format(s): {', '.join(invalid_tickers)}. Tickers must be 1-5 alphanumeric characters."
        raise HTTPException(status_code=400, detail=error_msg)
    
    if not valid_tickers:
        raise HTTPException(status_code=400, detail="No valid ticker symbols found")
    
    ticker_list = valid_tickers
    
    # Fetch metrics for all tickers using yfinance API (v1)
    try:
        metrics_list = get_multiple_stock_metrics(ticker_list)
        # Format numbers for display
        for metric in metrics_list:
            if 'error' not in metric:
                metric['current_price_formatted'] = f"${metric['current_price']:.2f}"
                metric['sma_50_formatted'] = f"${metric['sma_50']:.2f}"
                metric['sma_200_formatted'] = f"${metric['sma_200']:.2f}"
                metric['stddev_50d_formatted'] = f"{metric['devstep']:.1f}"
                # Always set dividend_yield_formatted, even if dividend_yield is missing or None
                dividend_yield = metric.get('dividend_yield')
                if dividend_yield is not None and dividend_yield != '':
                    try:
                        metric['dividend_yield_formatted'] = f"{float(dividend_yield):.2f}%"
                    except (ValueError, TypeError):
                        metric['dividend_yield_formatted'] = "N/A"
                else:
                    metric['dividend_yield_formatted'] = "N/A"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stock data: {str(e)}")
    
    return templates.TemplateResponse("results.html", {
        "request": request,
        "metrics": metrics_list,
        "tickers": ticker_list
    })


@app.get("/v1/stock")
async def get_stock_data(q: str = Query(..., description="Stock ticker symbol")):
    """
    Fetch stock data and compute metrics from database.
    
    Args:
        q: Stock ticker symbol (e.g., 'AAPL', 'MSFT')
        
    Returns:
        JSON response with stock metrics:
        - ticker: Stock ticker
        - sma_50: 50-day Simple Moving Average
        - sma_200: 200-day Simple Moving Average
        - devstep: Number of standard deviations from 50-day SMA (50D STDDEV)
        - signal: Trading signal (Neutral, Overbought, etc.)
        - current_price: Current stock price
        - dividend_yield: Dividend yield as a percentage (None if not available)
        - data_points: Number of data points
        - movement_5day_stddev: 5-day price movement in standard deviations
        - is_price_positive_5day: Whether price moved up in last 5 days
    """
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Ticker symbol (q) is required")
    
    try:
        metrics = get_stock_metrics_from_db(q.strip().upper())
        return metrics
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/validate/tickers")
async def validate_tickers(tickers: str = Query(..., description="Comma-separated stock tickers")):
    """
    Validate ticker format for a list of tickers.
    
    Args:
        tickers: Comma-separated list of stock ticker symbols
        
    Returns:
        JSON response with validation results:
        - valid: List of valid tickers
        - invalid: List of invalid tickers with error messages
    """
    from app.services.ticker_validator import validate_ticker_list
    
    if not tickers or not tickers.strip():
        return {"valid": [], "invalid": []}
    
    # Parse tickers
    raw_ticker_list = [t.strip().upper() for t in tickers.split(',') if t.strip()]
    
    if not raw_ticker_list:
        return {"valid": [], "invalid": []}
    
    # Validate ticker formats
    valid_tickers, invalid_tickers = validate_ticker_list(raw_ticker_list)
    
    # Format invalid tickers with error messages
    invalid_with_errors = [
        {"ticker": ticker, "error": "Invalid format. Tickers must be 1-5 alphanumeric characters."}
        for ticker in invalid_tickers
    ]
    
    return {
        "valid": valid_tickers,
        "invalid": invalid_with_errors
    }


# WatchList API Models
class WatchListCreate(BaseModel):
    watchlist_name: str
    description: Optional[str] = None


class WatchListUpdate(BaseModel):
    watchlist_name: str
    description: Optional[str] = None


class AddStocksRequest(BaseModel):
    tickers: str  # Comma-separated tickers


# WatchList API Endpoints
    # NOTE: request object not directly available in standard FastAPI without dependency or Request parameter.
    # But here we didn't add Request parameter. We need to add it or use dependency.
    # Let's add Request param to the functions.
    pass

@app.get("/v1/watchlist")
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


@app.get("/v1/watchlist/{watchlist_id}")
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


@app.post("/v1/watchlist")
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


@app.put("/v1/watchlist/{watchlist_id}")
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


class WatchListVisibilityUpdate(BaseModel):
    is_public: bool


@app.put("/v1/watchlist/{watchlist_id}/visibility")
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


@app.delete("/v1/watchlist/{watchlist_id}")
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


@app.post("/v1/watchlist/{watchlist_id}/stocks")
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


@app.delete("/v1/watchlist/{watchlist_id}/stocks/{ticker}")
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
        return {"message": f"Stock {ticker} removed from watchlist"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Stock Notes API Models
class StockNoteCreate(BaseModel):
    note_text: str


# Stock Notes API Endpoints
@app.get("/v1/stock/{ticker}/notes")
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


@app.put("/v1/watchlist/{watchlist_id}/stocks/{ticker}/note")
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


@app.delete("/v1/watchlist/{watchlist_id}/stocks/{ticker}/note")
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


# Stock Insights API Endpoints
@app.get("/v1/stock/{ticker}/insights")
async def get_stock_insights(
    request: Request,
    ticker: str = FPath(...),
    refresh: bool = Query(False, description="Force refresh insights from LLM")
):
    """
    Get LLM-generated insights for a stock.

    Returns AI-generated comprehensive investment analysis covering strategic narrative,
    fundamentals, debt/cash flow, price action, future scenarios, and investment verdict.
    Insights are cached for 24 hours. Use refresh=true to force a fresh fetch.

    Args:
        request: Request object
        ticker: Stock ticker symbol
        refresh: If true, force refresh from LLM regardless of cache

    Returns:
        JSON response with insights data containing 'analysis' markdown text
    """
    from app.services import insights_service

    try:
        result = insights_service.get_insights(ticker, force_refresh=refresh)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching insights: {str(e)}")


def _require_admin(request: Request):
    """Check that the request comes from an admin user. Raises HTTPException if not."""
    user = request.session.get("user") if hasattr(request, "session") else None
    if not user:
        raise HTTPException(status_code=403, detail="Admin access required. Please log in.")
    if not ADMIN_EMAIL or user.get("email") != ADMIN_EMAIL:
        raise HTTPException(status_code=403, detail="Admin access required.")


# LLM Model Management API Endpoints
class LLMModelCreate(BaseModel):
    model_name: str
    tier: str


@app.get("/v1/llm-models")
async def list_llm_models(request: Request):
    """List all LLM models (admin-only)."""
    _require_admin(request)
    from app.services import llm_model_service

    models = llm_model_service.get_all_models()
    current_model = llm_model_service.get_current_active_model()

    return {
        "models": [
            {
                "id": m.id,
                "model_name": m.model_name,
                "tier": m.tier,
                "is_active": m.is_active,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in models
        ],
        "current_model": current_model.model_name if current_model else None,
    }


@app.post("/v1/llm-models")
async def create_llm_model(request: Request, body: LLMModelCreate):
    """Add a new LLM model (admin-only)."""
    _require_admin(request)
    from app.services import llm_model_service

    try:
        model = llm_model_service.add_model(body.model_name, body.tier)
        return {
            "id": model.id,
            "model_name": model.model_name,
            "tier": model.tier,
            "is_active": model.is_active,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/v1/llm-models/{model_id}/activate")
async def activate_llm_model(request: Request, model_id: int):
    """Activate an LLM model and reset provider cache (admin-only)."""
    _require_admin(request)
    from app.services import llm_model_service
    from app.providers.llm import LLMProviderFactory

    try:
        model = llm_model_service.activate_model(model_id)
        LLMProviderFactory.reset_provider()
        return {
            "id": model.id,
            "model_name": model.model_name,
            "tier": model.tier,
            "is_active": model.is_active,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/v1/llm-models/{model_id}")
async def delete_llm_model(request: Request, model_id: int):
    """Delete an LLM model (admin-only). Cannot delete the active model."""
    _require_admin(request)
    from app.services import llm_model_service

    try:
        llm_model_service.delete_model(model_id)
        return {"message": "Model deleted"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/debug/llm-models")
async def debug_llm_models_page(request: Request):
    """
    Debug page for managing LLM models.

    Returns:
        HTML page with LLM model management UI
    """
    from app.services import llm_model_service

    models = llm_model_service.get_all_models()
    current_model = llm_model_service.get_current_active_model()

    return templates.TemplateResponse("debug_llm_models.html", {
        "request": request,
        "models": models,
        "current_model": current_model,
    })


@app.get("/debug/stock-price")
async def debug_stock_price_page(request: Request, ticker: str = Query("", description="Stock ticker symbol")):
    """
    Debug page for displaying stock price data and all stock attributes from database.
    
    Args:
        ticker: Optional stock ticker symbol to display
        
    Returns:
        HTML page with stock price data and all stock attributes
    """
    from app.services.stock_price_service import get_stock_prices_from_db, get_stock_attributes
    
    prices = []
    attributes = None
    error_message = None
    
    if ticker:
        ticker = ticker.strip().upper()
        try:
            prices = get_stock_prices_from_db(ticker)
            attributes = get_stock_attributes(ticker)
        except Exception as e:
            error_message = f"Error fetching data: {str(e)}"
    
    # Format prices for display
    prices_data = []
    for price in prices:
        prices_data.append({
            "price_date": price.price_date.isoformat(),
            "ticker": price.ticker,
            "open_price": float(price.open_price),
            "close_price": float(price.close_price),
            "high_price": float(price.high_price),
            "low_price": float(price.low_price),
            "dma_50": float(price.dma_50) if price.dma_50 else None,
            "dma_200": float(price.dma_200) if price.dma_200 else None,
            "iv": float(price.iv) if price.iv else None
        })
    
    # Format all stock attributes for display - dynamically iterate over model fields
    # This ensures new fields added to StockAttributes are automatically displayed
    attributes_data = None
    attributes_fields = []  # List of (field_name, display_name, formatted_value)
    if attributes:
        from datetime import date as date_type
        from decimal import Decimal
        
        # Get all field names from the model (excluding internal SQLModel fields)
        model_fields = attributes.__class__.__fields__
        
        # Define display name mappings for prettier labels
        display_names = {
            "ticker": "Ticker",
            "earliest_date": "Earliest Date",
            "latest_date": "Latest Date",
            "dividend_amt": "Dividend Amount",
            "dividend_yield": "Dividend Yield",
            "next_earnings_date": "Next Earnings Date",
            "is_earnings_date_estimate": "Earnings Date Confirmed",
            "next_dividend_date": "Next Dividend Date",
        }
        
        for field_name in model_fields:
            value = getattr(attributes, field_name, None)
            display_name = display_names.get(field_name, field_name.replace("_", " ").title())
            
            # Format value based on type
            if value is None:
                formatted_value = None
            elif isinstance(value, date_type):
                formatted_value = value.strftime('%b %d, %Y')
            elif isinstance(value, Decimal):
                if 'yield' in field_name.lower():
                    formatted_value = f"{float(value):.4f}%"
                elif 'amt' in field_name.lower() or 'amount' in field_name.lower():
                    formatted_value = f"${float(value):.4f}"
                else:
                    formatted_value = f"{float(value):.4f}"
            elif isinstance(value, bool):
                formatted_value = "Yes" if value else "No"
            elif field_name == "is_earnings_date_estimate":
                # Special handling: invert for "Confirmed" display
                formatted_value = "No (Estimated)" if value else "Yes (Confirmed)"
            else:
                formatted_value = str(value)
            
            attributes_fields.append({
                "field": field_name,
                "label": display_name,
                "value": formatted_value,
                "raw_value": value,
                "is_ticker": field_name == "ticker"
            })
    
    return templates.TemplateResponse("debug_stock_price.html", {
        "request": request,
        "ticker": ticker if ticker else "",
        "prices": prices_data,
        "attributes_fields": attributes_fields,
        "error_message": error_message
    })


@app.post("/debug/stock-price/fetch")
async def fetch_stock_price_data(ticker: str = Query(..., description="Stock ticker symbol")):
    """
    Force refresh stock data, options cache, trading metrics, option strategies, and insights.

    Uses the unified refresh_stock_data function that:
    1. Clears the options cache for this ticker
    2. Fetches fresh stock price data from yfinance
    3. Recalculates trading metrics (SMAs, signals, IV)
    4. Pre-calculates option strategies (Risk Reversal, Covered Calls)
    5. Refreshes LLM insights

    Args:
        ticker: Stock ticker symbol

    Returns:
        JSON response with fetch status
    """
    from app.services.stock_price_service import refresh_stock_data
    from app.services import insights_service

    if not ticker or not ticker.strip():
        raise HTTPException(status_code=400, detail="Ticker is required")

    try:
        ticker = ticker.strip().upper()

        # Use unified refresh function with cache clearing enabled
        result = refresh_stock_data(ticker, clear_cache=True)

        if not result.get("success"):
            raise HTTPException(
                status_code=500,
                detail=result.get("error", "Failed to refresh stock data")
            )

        # Also refresh insights
        insights_result = insights_service.get_insights(ticker, force_refresh=True)
        insights_refreshed = insights_result.get("status") == "available"

        return {
            "message": f"Force refreshed {ticker}: {result['price_records']} price records, "
                       f"{result['rr_strategies']} RR strategies, {result['cc_strategies']} CC strategies"
                       f"{', insights updated' if insights_refreshed else ''}",
            "ticker": ticker,
            "new_records": result["price_records"],
            "current_price": result.get("current_price"),
            "cache_cleared": True,
            "metrics_recalculated": True,
            "strategies_calculated": result["rr_strategies"] > 0 or result["cc_strategies"] > 0,
            "rr_strategies_count": result["rr_strategies"],
            "cc_strategies_count": result["cc_strategies"],
            "insights_refreshed": insights_refreshed
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching data: {str(e)}")


@app.get("/debug/database-status")
async def debug_database_status():
    """Debug endpoint to check database status and earnings data."""
    from app.database import DATABASE_URL, engine
    from sqlmodel import Session, select
    from app.models.watchlist import WatchList, WatchListStock
    from app.models.stock_price import StockAttributes
    import os
    
    db_info = {
        "database_url": DATABASE_URL,
        "is_sqlite": DATABASE_URL.startswith("sqlite"),
    }
    
    if DATABASE_URL.startswith("sqlite"):
        db_file = DATABASE_URL.replace("sqlite:///", "")
        if not os.path.isabs(db_file):
            db_file = os.path.abspath(db_file)
        db_info["database_file"] = db_file
        db_info["file_exists"] = os.path.exists(db_file)
        if os.path.exists(db_file):
            db_info["file_size"] = os.path.getsize(db_file)
    
    with Session(engine) as session:
        watchlists = session.exec(select(WatchList)).all()
        db_info["watchlists_count"] = len(watchlists)
        db_info["watchlists"] = []
        
        for wl in watchlists:
            stocks = session.exec(select(WatchListStock).where(WatchListStock.watchlist_id == wl.watchlist_id)).all()
            wl_info = {
                "name": wl.watchlist_name,
                "id": str(wl.watchlist_id),
                "stocks_count": len(stocks),
                "stocks": []
            }
            
            for stock in stocks:
                attr = session.get(StockAttributes, stock.ticker.upper())
                stock_info = {
                    "ticker": stock.ticker,
                    "has_earnings": attr.next_earnings_date is not None if attr else False,
                    "earnings_date": str(attr.next_earnings_date) if attr and attr.next_earnings_date else None,
                }
                wl_info["stocks"].append(stock_info)
            
            db_info["watchlists"].append(wl_info)
    
    return db_info


@app.get("/debug")
async def debug_index(request: Request):
    """
    Debug tools index page - lists all available debug endpoints.
    
    Returns:
        HTML page with links to all debug tools
    """
    return templates.TemplateResponse("debug_index.html", {
        "request": request
    })


@app.get("/debug/scheduler-log")
async def scheduler_log_page(request: Request, limit: int = Query(50, description="Number of log entries to display")):
    """
    Debug page for displaying scheduler log data.
    Dynamically displays all fields from SchedulerLog model.
    
    Args:
        limit: Number of log entries to display (default: 50)
        
    Returns:
        HTML page with scheduler log data
    """
    from sqlmodel import Session, select
    from app.database import engine
    from app.models.scheduler_log import SchedulerLog
    from app.helpers.model_helpers import get_table_columns, format_field_value
    
    try:
        with Session(engine) as session:
            statement = select(SchedulerLog).order_by(SchedulerLog.id.desc()).limit(limit)
            log_entries = session.exec(statement).all()
        
        # Get dynamic columns from model + computed columns
        custom_labels = {
            "id": "ID",
            "start_time": "Start Time",
            "end_time": "End Time",
            "notes": "Notes"
        }
        extra_columns = [
            {"field": "duration_formatted", "label": "Duration"},
            {"field": "status", "label": "Status"}
        ]
        columns = get_table_columns(SchedulerLog, custom_labels, extra_columns)
        
        # Format log entries for display - dynamically iterate over model fields
        log_data = []
        completed_count = 0
        in_progress_count = 0
        
        for entry in log_entries:
            # Build row dynamically from model fields
            row = {}
            for field_name in SchedulerLog.__fields__:
                value = getattr(entry, field_name, None)
                row[field_name] = format_field_value(value, field_name)
                row[f"{field_name}_raw"] = value  # Keep raw value for special handling
            
            # Add computed columns
            duration = None
            if entry.end_time:
                duration = (entry.end_time - entry.start_time).total_seconds()
                completed_count += 1
            else:
                in_progress_count += 1
            
            row["duration_formatted"] = _format_duration(duration) if duration else "In Progress"
            row["duration_seconds"] = round(duration, 2) if duration else None
            
            # Determine status from notes
            # Only mark as error if notes explicitly starts with "Error:" prefix
            if entry.end_time:
                if entry.notes and entry.notes.startswith('Error:'):
                    row["status"] = "error"
                elif entry.notes and ('Skipped' in entry.notes or 'skipped' in entry.notes):
                    row["status"] = "skipped"
                else:
                    row["status"] = "completed"
            else:
                row["status"] = "in_progress"
            
            log_data.append(row)
        
        return templates.TemplateResponse("scheduler_log.html", {
            "request": request,
            "columns": columns,
            "log_entries": log_data,
            "limit": limit,
            "total_count": len(log_data),
            "completed_count": completed_count,
            "in_progress_count": in_progress_count
        })
    except Exception as e:
        return templates.TemplateResponse("scheduler_log.html", {
            "request": request,
            "columns": [],
            "log_entries": [],
            "limit": limit,
            "total_count": 0,
            "completed_count": 0,
            "in_progress_count": 0,
            "error_message": f"Error fetching log data: {str(e)}"
        })


def _format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds is None:
        return "N/A"
    
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"


@app.get("/debug/rr-history-log")
async def rr_history_log_page(request: Request, limit: int = Query(50, description="Number of log entries to display")):
    """
    Debug page for displaying RR history update log data.
    Dynamically displays all fields from RRHistoryLog model.
    
    Args:
        limit: Number of log entries to display (default: 50)
        
    Returns:
        HTML page with RR history log data
    """
    from sqlmodel import Session, select
    from app.database import engine
    from app.models.rr_history_log import RRHistoryLog
    from app.helpers.model_helpers import get_table_columns, format_field_value
    
    try:
        with Session(engine) as session:
            statement = select(RRHistoryLog).order_by(RRHistoryLog.id.desc()).limit(limit)
            log_entries = session.exec(statement).all()
        
        # Get dynamic columns from model + computed columns
        custom_labels = {
            "id": "ID",
            "start_time": "Start Time",
            "end_time": "End Time",
            "notes": "Notes"
        }
        extra_columns = [
            {"field": "duration_formatted", "label": "Duration"},
            {"field": "status", "label": "Status"}
        ]
        columns = get_table_columns(RRHistoryLog, custom_labels, extra_columns)
        
        # Format log entries for display - dynamically iterate over model fields
        log_data = []
        completed_count = 0
        in_progress_count = 0
        
        for entry in log_entries:
            # Build row dynamically from model fields
            row = {}
            for field_name in RRHistoryLog.__fields__:
                value = getattr(entry, field_name, None)
                row[field_name] = format_field_value(value, field_name)
                row[f"{field_name}_raw"] = value  # Keep raw value for special handling
            
            # Add computed columns
            duration = None
            if entry.end_time:
                duration = (entry.end_time - entry.start_time).total_seconds()
                completed_count += 1
            else:
                in_progress_count += 1
            
            row["duration_formatted"] = _format_duration(duration) if duration else "In Progress"
            row["duration_seconds"] = round(duration, 2) if duration else None
            
            # Determine status from notes
            # Only mark as error if notes explicitly starts with "Error:" prefix
            if entry.end_time:
                if entry.notes and entry.notes.startswith('Error:'):
                    row["status"] = "error"
                elif entry.notes and ('Skipped' in entry.notes or 'skipped' in entry.notes):
                    row["status"] = "skipped"
                else:
                    row["status"] = "completed"
            else:
                row["status"] = "in_progress"
            
            log_data.append(row)
        
        return templates.TemplateResponse("rr_history_log.html", {
            "request": request,
            "columns": columns,
            "log_entries": log_data,
            "limit": limit,
            "total_count": len(log_data),
            "completed_count": completed_count,
            "in_progress_count": in_progress_count
        })
    except Exception as e:
        return templates.TemplateResponse("rr_history_log.html", {
            "request": request,
            "columns": [],
            "log_entries": [],
            "limit": limit,
            "total_count": 0,
            "completed_count": 0,
            "in_progress_count": 0,
            "error_message": f"Error fetching log data: {str(e)}"
        })


@app.post("/debug/rr-history-log/trigger")
async def trigger_rr_history_manual(bypass_market_hours: bool = Query(True, description="Bypass market hours check")):
    """
    Manually trigger the RR history update.
    This endpoint allows testing the RR history update at any time, regardless of market hours.
    
    Args:
        bypass_market_hours: If True, run update even when market is closed (default: True)
        
    Returns:
        JSON response with trigger status and log entry ID
    """
    from app.services.scheduler_service import update_rr_history_manual
    
    try:
        log_id = update_rr_history_manual(bypass_market_hours=bypass_market_hours)
        
        return {
            "message": "RR history update triggered successfully",
            "log_id": log_id,
            "bypass_market_hours": bypass_market_hours,
            "status": "completed"
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "message": "Error triggering RR history update",
            "error": str(e),
            "status": "error"
        }


@app.post("/debug/scheduler-log/trigger")
async def trigger_scheduler_manual(bypass_market_hours: bool = Query(True, description="Bypass market hours check")):
    """
    Manually trigger the scheduler to fetch stock data.
    This endpoint allows testing the scheduler at any time, regardless of market hours.
    
    Args:
        bypass_market_hours: If True, run scheduler even when market is closed (default: True)
        
    Returns:
        JSON response with trigger status and log entry ID
    """
    from app.services.scheduler_service import fetch_all_watchlist_stocks_manual
    
    try:
        log_id = fetch_all_watchlist_stocks_manual(bypass_market_hours=bypass_market_hours)
        
        return {
            "message": "Scheduler triggered successfully",
            "log_id": log_id,
            "bypass_market_hours": bypass_market_hours,
            "status": "completed"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error triggering scheduler: {str(e)}")


@app.post("/debug/cleanup-logs/trigger")
async def trigger_cleanup_logs():
    """
    Manually trigger the cleanup job to delete old scheduler log entries.
    This endpoint allows testing the cleanup job at any time.

    Returns:
        JSON response with trigger status
    """
    from app.services.scheduler_service import cleanup_old_scheduler_logs

    try:
        cleanup_old_scheduler_logs()

        return {
            "message": "Cleanup job triggered successfully",
            "status": "completed"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error triggering cleanup: {str(e)}")


# TEST ONLY: Endpoint to facilitate browser test authentication
# This endpoint allows setting the session cookie via a direct request,
# bypassing the need for manual cookie injection which is brittle across processes.
# if os.getenv("ARTHOS_TEST_MODE") == "true":
@app.get("/_test/login/{user_id}")
async def test_login_endpoint(user_id: str, request: Request):
        """Test endpoint for setting up authenticated sessions.

        Args:
            user_id: Account ID as string (UUID stored as VARCHAR in database)
        """
        from app.models.account import Account
        from sqlmodel import Session as SQLSession
        from app.database import engine

        with SQLSession(engine) as session:
            # Query by string since UUIDs are stored as VARCHAR(36)
            account = session.get(Account, user_id)
            if not account:
                return {"error": "User not found"}

            # Set session data exactly as the app expects
            request.session["account_id"] = str(account.id)
            request.session["user"] = {
                "name": account.full_name,
                "email": account.email,
                "picture": account.picture_url
            }
            return {"status": "ok", "account_id": str(account.id)}


@app.post("/_test/clear-cache")
async def clear_cache_endpoint():
    """Test-only endpoint to clear options cache."""
    from app.services.options_cache_service import clear_options_cache
    clear_options_cache()
    return {"status": "cache_cleared"}

