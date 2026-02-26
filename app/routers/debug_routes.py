"""
Debug tools and test endpoints for development and troubleshooting.
"""
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel
from starlette.templating import Jinja2Templates
from pathlib import Path as PathLib
from app.utils.route_helpers import _format_duration
import logging


router = APIRouter()
logger = logging.getLogger(__name__)

# Set up templates directory
templates_dir = PathLib(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@router.get("/debug/stock-price")
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


@router.post("/debug/stock-price/fetch")
async def fetch_stock_price_data(ticker: str = Query(..., description="Stock ticker symbol")):
    """
    Force refresh stock data, options cache, trading metrics, and option strategies.

    Uses the unified refresh_stock_data function that:
    1. Clears the options cache for this ticker
    2. Fetches fresh stock price data from yfinance
    3. Recalculates trading metrics (SMAs, signals, IV)
    4. Pre-calculates option strategies (Risk Reversal, Covered Calls)

    Args:
        ticker: Stock ticker symbol

    Returns:
        JSON response with fetch status
    """
    from app.services.stock_price_service import refresh_stock_data

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

        return {
            "message": f"Force refreshed {ticker}: {result['price_records']} price records, "
                       f"{result['rr_strategies']} RR strategies, {result['cc_strategies']} CC strategies",
            "ticker": ticker,
            "new_records": result["price_records"],
            "current_price": result.get("current_price"),
            "cache_cleared": True,
            "metrics_recalculated": True,
            "strategies_calculated": result["rr_strategies"] > 0 or result["cc_strategies"] > 0,
            "rr_strategies_count": result["rr_strategies"],
            "cc_strategies_count": result["cc_strategies"],
        }
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching data: {str(e)}")


@router.get("/debug/database-status")
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


@router.get("/debug")
async def debug_index(request: Request):
    """
    Debug tools index page - lists all available debug endpoints.

    Returns:
        HTML page with links to all debug tools
    """
    return templates.TemplateResponse("debug_index.html", {
        "request": request
    })


@router.get("/debug/scheduler-log")
async def scheduler_log_page(
    request: Request,
    limit: int = Query(50, description="Number of log entries to display"),
    job_type: str = Query("all", description="Filter log entries by job type (all, options_cache)")
):
    """
    Debug page for displaying scheduler log data.
    Dynamically displays all fields from SchedulerLog model.

    Args:
        limit: Number of log entries to display (default: 50)

    Returns:
        HTML page with scheduler log data
    """
    from sqlalchemy import func
    from sqlmodel import Session, select
    from app.database import engine
    from app.models.scheduler_log import SchedulerLog
    from app.helpers.model_helpers import get_table_columns, format_field_value

    normalized_job_type = (job_type or "all").strip().lower()
    if normalized_job_type not in {"all", "options_cache"}:
        normalized_job_type = "all"

    is_options_cache_view = normalized_job_type == "options_cache"
    page_title = "Options Data Fetch Log" if is_options_cache_view else "Scheduler Log"
    page_description = (
        "View options data fetch execution history and statistics"
        if is_options_cache_view
        else "View scheduler execution history and statistics"
    )
    table_title = "Options Data Fetch Execution Log" if is_options_cache_view else "Scheduler Execution Log"
    trigger_description = (
        "Manually trigger option data fetch for all watchlist tickers."
        if is_options_cache_view
        else "Manually trigger the scheduler to fetch stock data (bypasses market hours check)."
    )
    trigger_button_text = "Trigger Option Data Fetch" if is_options_cache_view else "Trigger Scheduler"
    trigger_endpoint = "/debug/options-cache-log/trigger" if is_options_cache_view else "/debug/scheduler-log/trigger"

    try:
        with Session(engine) as session:
            statement = select(SchedulerLog)
            if is_options_cache_view:
                statement = statement.where(func.lower(SchedulerLog.notes).contains("options cache"))
            statement = statement.order_by(SchedulerLog.id.desc()).limit(limit)
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
            # Mark as error only if notes explicitly starts with failure prefix
            if entry.end_time:
                normalized_notes = (entry.notes or "").lower()
                if normalized_notes.startswith("error:") or normalized_notes.startswith("failed:"):
                    row["status"] = "error"
                elif "skipped" in normalized_notes:
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
            "job_type": normalized_job_type,
            "page_title": page_title,
            "page_description": page_description,
            "table_title": table_title,
            "trigger_description": trigger_description,
            "trigger_button_text": trigger_button_text,
            "trigger_endpoint": trigger_endpoint,
            "show_bypass_market_hours": not is_options_cache_view,
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
            "job_type": normalized_job_type,
            "page_title": page_title,
            "page_description": page_description,
            "table_title": table_title,
            "trigger_description": trigger_description,
            "trigger_button_text": trigger_button_text,
            "trigger_endpoint": trigger_endpoint,
            "show_bypass_market_hours": not is_options_cache_view,
            "total_count": 0,
            "completed_count": 0,
            "in_progress_count": 0,
            "error_message": f"Error fetching log data: {str(e)}"
        })


@router.get("/debug/options-cache-log")
async def options_cache_log_page(request: Request, limit: int = Query(50, description="Number of log entries to display")):
    """
    Debug page for displaying option data fetch job run history.

    Args:
        limit: Number of log entries to display (default: 50)

    Returns:
        HTML page with options cache job log data
    """
    return await scheduler_log_page(request=request, limit=limit, job_type="options_cache")


@router.get("/debug/rr-history-log")
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


@router.post("/debug/rr-history-log/trigger")
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


@router.post("/debug/scheduler-log/trigger")
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


@router.post("/debug/options-cache-log/trigger")
async def trigger_options_cache_manual():
    """
    Manually trigger the options cache update job.
    This endpoint allows testing the daily options cache refresh on demand.

    Returns:
        JSON response with trigger status and log entry ID
    """
    from app.services.scheduler_service import update_options_cache_for_all_watchlists

    try:
        log_id = update_options_cache_for_all_watchlists()

        return {
            "message": "Options cache update triggered successfully",
            "log_id": log_id,
            "status": "completed"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error triggering options cache update: {str(e)}")


@router.post("/debug/cleanup-logs/trigger")
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


@router.get("/debug/llm-playground")
async def debug_llm_playground_page(request: Request):
    """
    LLM Playground - test different OpenRouter models and prompts.

    Returns:
        HTML page with model selection, prompt input, and response display
    """
    return templates.TemplateResponse("debug_llm_playground.html", {
        "request": request,
    })


@router.get("/debug/llm-playground/models")
async def get_openrouter_models():
    """
    Fetch available models from OpenRouter API.

    Returns:
        JSON list of models with pricing and tier information
    """
    from app.services import openrouter_service

    try:
        models = openrouter_service.get_available_models()
        return models
    except Exception as e:
        logger.error(f"Error fetching OpenRouter models: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching models: {str(e)}")


class TestPromptRequest(BaseModel):
    model_id: str
    prompt: str


@router.post("/debug/llm-playground/test")
async def test_llm_prompt(request: Request, body: TestPromptRequest):
    """
    Test a prompt with a specific OpenRouter model.

    Args:
        body: Request containing model_id and prompt

    Returns:
        JSON response with success status, response text, and metadata
    """
    from app.services import openrouter_service

    try:
        result = openrouter_service.test_prompt_with_model(
            model_id=body.model_id,
            prompt=body.prompt
        )
        return result
    except Exception as e:
        logger.error(f"Error testing prompt: {e}")
        raise HTTPException(status_code=500, detail=f"Error testing prompt: {str(e)}")


# TEST ONLY: Endpoint to facilitate browser test authentication
# This endpoint allows setting the session cookie via a direct request,
# bypassing the need for manual cookie injection which is brittle across processes.
@router.get("/_test/login/{user_id}")
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


@router.post("/_test/clear-cache")
async def clear_cache_endpoint():
    """Test-only endpoint to clear options cache."""
    from app.services.options_cache_service import clear_options_cache
    clear_options_cache()
    return {"status": "cache_cleared"}


@router.get("/debug/watchlist-tickers-page")
async def watchlist_tickers_page(request: Request):
    """
    Debug page for displaying all watchlist tickers.

    Returns:
        HTML page with ticker list and statistics
    """
    from app.utils.route_helpers import _require_admin
    from sqlmodel import Session, select
    from app.database import engine
    from app.models.watchlist import WatchListStock
    from sqlalchemy import func

    _require_admin(request)

    try:
        with Session(engine) as session:
            # Get all unique tickers
            tickers_stmt = select(WatchListStock.ticker).distinct().order_by(WatchListStock.ticker)
            tickers = session.exec(tickers_stmt).all()

            # Get count of watchlists per ticker
            count_stmt = (
                select(
                    WatchListStock.ticker,
                    func.count(func.distinct(WatchListStock.watchlist_id)).label('watchlist_count')
                )
                .group_by(WatchListStock.ticker)
                .order_by(func.count(func.distinct(WatchListStock.watchlist_id)).desc(), WatchListStock.ticker)
            )
            ticker_counts_raw = session.exec(count_stmt).all()

            # Calculate stats
            total_tickers = len(tickers)
            popular_tickers = sum(1 for _, count in ticker_counts_raw if count >= 2)
            single_tickers = sum(1 for _, count in ticker_counts_raw if count == 1)

            # Format ticker counts for template
            ticker_counts = [
                {"ticker": ticker, "count": count}
                for ticker, count in ticker_counts_raw
            ]

            return templates.TemplateResponse("debug_watchlist_tickers.html", {
                "request": request,
                "total_tickers": total_tickers,
                "popular_tickers": popular_tickers,
                "single_tickers": single_tickers,
                "all_tickers": list(tickers),
                "ticker_counts": ticker_counts
            })
    except Exception as e:
        logger.error(f"Error fetching watchlist tickers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/debug/watchlist-tickers")
async def get_watchlist_tickers(request: Request):
    """
    Admin API endpoint to get all unique tickers from watchlists.

    Returns:
        JSON with list of tickers and counts
    """
    from app.utils.route_helpers import _require_admin
    from sqlmodel import Session, select
    from app.database import engine
    from app.models.watchlist import WatchListStock
    from sqlalchemy import func

    _require_admin(request)

    try:
        with Session(engine) as session:
            # Get all unique tickers
            tickers_stmt = select(WatchListStock.ticker).distinct().order_by(WatchListStock.ticker)
            tickers = session.exec(tickers_stmt).all()

            # Get count of watchlists per ticker
            count_stmt = (
                select(
                    WatchListStock.ticker,
                    func.count(func.distinct(WatchListStock.watchlist_id)).label('watchlist_count')
                )
                .group_by(WatchListStock.ticker)
                .order_by(func.count(func.distinct(WatchListStock.watchlist_id)).desc(), WatchListStock.ticker)
            )
            ticker_counts = session.exec(count_stmt).all()

            return {
                "total_unique_tickers": len(tickers),
                "tickers": list(tickers),
                "ticker_counts": [
                    {"ticker": ticker, "watchlist_count": count}
                    for ticker, count in ticker_counts
                ]
            }
    except Exception as e:
        logger.error(f"Error fetching watchlist tickers: {e}")
        raise HTTPException(status_code=500, detail=str(e))
