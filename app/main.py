"""FastAPI application for Arthos investment analysis."""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException, Query, Path as FPath
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from pathlib import Path
from uuid import UUID
from app.services.stock_price_service import get_stock_metrics_from_db
from app.database import create_db_and_tables
from pydantic import BaseModel


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for FastAPI app startup and shutdown."""
    # Startup
    create_db_and_tables()
    
    # Start the scheduler for fetching stock data every 60 minutes
    try:
        from app.services.scheduler_service import start_scheduler
        start_scheduler()
        print("Scheduler started for fetching stock data every 60 minutes")
    except Exception as e:
        # Don't crash startup if scheduler fails
        print(f"Warning: Could not start scheduler: {e}")
    
    yield
    
    # Shutdown
    try:
        from app.services.scheduler_service import stop_scheduler
        stop_scheduler()
        print("Scheduler stopped")
    except Exception as e:
        print(f"Warning: Could not stop scheduler: {e}")


# Initialize FastAPI app with lifespan handler
app = FastAPI(
    title="Arthos",
    description="Investment Analysis Platform",
    lifespan=lifespan
)

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
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/watchlists")
async def list_watchlists_page(request: Request):
    """
    Display list of all watchlists.
    
    Returns:
        HTML page with list of watchlists
    """
    from app.services.watchlist_service import get_all_watchlists
    
    watchlists = get_all_watchlists()
    
    # Format dates for display
    watchlists_data = []
    for w in watchlists:
        watchlists_data.append({
            "watchlist_id": str(w.watchlist_id),
            "watchlist_name": w.watchlist_name,
            "date_added": w.date_added.strftime("%Y-%m-%d %H:%M:%S"),
            "date_modified": w.date_modified.strftime("%Y-%m-%d %H:%M:%S")
        })
    
    return templates.TemplateResponse("watchlists.html", {
        "request": request,
        "watchlists": watchlists_data
    })


@app.get("/create-watchlist")
async def create_watchlist_page(request: Request):
    """
    Display create watchlist page.
    
    Returns:
        HTML page for creating a new watchlist
    """
    return templates.TemplateResponse("create_watchlist.html", {"request": request})


@app.get("/watchlist/{watchlist_id}")
async def watchlist_details_page(request: Request, watchlist_id: UUID = FPath(...)):
    """
    Display watchlist details page with stocks.
    
    Args:
        watchlist_id: UUID of the watchlist
        
    Returns:
        HTML page with watchlist details and stocks
    """
    from app.services.watchlist_service import get_watchlist, get_watchlist_stocks_with_metrics
    
    try:
        watchlist = get_watchlist(watchlist_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="WatchList not found")
    
    # Get stocks in watchlist with metrics
    metrics_list = get_watchlist_stocks_with_metrics(watchlist_id)
    
    return templates.TemplateResponse("watchlist_details.html", {
        "request": request,
        "watchlist": {
            "watchlist_id": str(watchlist.watchlist_id),
            "watchlist_name": watchlist.watchlist_name,
            "date_added": watchlist.date_added.strftime("%Y-%m-%d %H:%M:%S"),
            "date_modified": watchlist.date_modified.strftime("%Y-%m-%d %H:%M:%S")
        },
        "metrics": metrics_list
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
        
        # Get options data with error handling
        options_expiration = None
        options_data = {}
        sorted_strikes = []
        covered_calls = []
        min_distance = None
        
        try:
            from app.services.stock_service import get_options_data, calculate_covered_call_returns
            options_expiration, options_data = get_options_data(ticker, metrics['current_price'])
            
            # Sort strikes in descending order for display (highest strike first)
            # Check if options_data is a dict and has keys
            if options_data and isinstance(options_data, dict) and len(options_data) > 0:
                sorted_strikes = sorted(options_data.keys(), reverse=True)
                
                # Calculate minimum distance from current price to closest strike
                if metrics['current_price'] and metrics['current_price'] > 0:
                    for strike in sorted_strikes:
                        if strike > metrics['current_price']:
                            distance = strike - metrics['current_price']
                        else:
                            distance = metrics['current_price'] - strike
                        if min_distance is None or distance < min_distance:
                            min_distance = distance
                
                # Calculate covered call returns
                try:
                    covered_calls = calculate_covered_call_returns(options_data, metrics['current_price'])
                except Exception as e:
                    print(f"Error calculating covered call returns for {ticker}: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    covered_calls = []
        except Exception as e:
            # If options data fails, continue without it
            print(f"Error fetching options data for {ticker}: {str(e)}")
            import traceback
            traceback.print_exc()
            options_expiration = None
            options_data = {}
            sorted_strikes = []
            covered_calls = []
            min_distance = None
        
        return templates.TemplateResponse("stock_detail.html", {
            "request": request,
            "ticker": ticker,
            "chart_data": chart_data,
            "metrics": metrics,
            "options_expiration": options_expiration,
            "options_data": options_data,
            "sorted_strikes": sorted_strikes,
            "covered_calls": covered_calls,
            "current_price": metrics['current_price'],
            "min_distance": min_distance
        })
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching stock data: {str(e)}")


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


class WatchListUpdate(BaseModel):
    watchlist_name: str


class AddStocksRequest(BaseModel):
    tickers: str  # Comma-separated tickers


# WatchList API Endpoints
@app.get("/v1/watchlist")
async def list_watchlists():
    """
    List all watchlists.
    
    Returns:
        JSON response with list of watchlists
    """
    from app.services.watchlist_service import get_all_watchlists
    
    watchlists = get_all_watchlists()
    return {
        "watchlists": [
            {
                "watchlist_id": str(w.watchlist_id),
                "watchlist_name": w.watchlist_name,
                "date_added": w.date_added.isoformat(),
                "date_modified": w.date_modified.isoformat()
            }
            for w in watchlists
        ]
    }


@app.get("/v1/watchlist/{watchlist_id}")
async def get_watchlist(watchlist_id: UUID = FPath(...)):
    """
    Get watchlist details.
    
    Args:
        watchlist_id: UUID of the watchlist
        
    Returns:
        JSON response with watchlist details and stocks
    """
    from app.services.watchlist_service import get_watchlist, get_watchlist_stocks
    
    try:
        watchlist = get_watchlist(watchlist_id)
        stocks = get_watchlist_stocks(watchlist_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    return {
        "watchlist_id": str(watchlist.watchlist_id),
        "watchlist_name": watchlist.watchlist_name,
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
async def create_watchlist(watchlist: WatchListCreate):
    """
    Create a new watchlist.
    
    Args:
        watchlist: WatchList creation request with watchlist_name
        
    Returns:
        JSON response with created watchlist
    """
    from app.services.watchlist_service import create_watchlist
    
    try:
        new_watchlist = create_watchlist(watchlist.watchlist_name)
        return {
            "watchlist_id": str(new_watchlist.watchlist_id),
            "watchlist_name": new_watchlist.watchlist_name,
            "date_added": new_watchlist.date_added.isoformat(),
            "date_modified": new_watchlist.date_modified.isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/v1/watchlist/{watchlist_id}")
async def update_watchlist(watchlist_id: UUID = FPath(...), watchlist: WatchListUpdate = None):
    """
    Update watchlist name.
    
    Args:
        watchlist_id: UUID of the watchlist
        watchlist: WatchList update request with watchlist_name
        
    Returns:
        JSON response with updated watchlist
    """
    from app.services.watchlist_service import update_watchlist_name
    
    if not watchlist:
        raise HTTPException(status_code=400, detail="WatchList name is required")
    
    try:
        updated_watchlist = update_watchlist_name(watchlist_id, watchlist.watchlist_name)
        if not updated_watchlist:
            raise HTTPException(status_code=404, detail="WatchList not found")
        
        return {
            "watchlist_id": str(updated_watchlist.watchlist_id),
            "watchlist_name": updated_watchlist.watchlist_name,
            "date_added": updated_watchlist.date_added.isoformat(),
            "date_modified": updated_watchlist.date_modified.isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/v1/watchlist/{watchlist_id}")
async def delete_watchlist(watchlist_id: UUID = FPath(...)):
    """
    Delete a watchlist and all its stocks (cascade delete).
    
    Args:
        watchlist_id: UUID of the watchlist
        
    Returns:
        JSON response with deletion status
    """
    from app.services.watchlist_service import delete_watchlist
    
    try:
        delete_watchlist(watchlist_id)
        return {"message": "WatchList deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/v1/watchlist/{watchlist_id}/stocks")
async def add_stocks_to_watchlist(watchlist_id: UUID = FPath(...), request: AddStocksRequest = None):
    """
    Add stocks to a watchlist. Filters out invalid tickers and returns info about them.
    
    Args:
        watchlist_id: UUID of the watchlist
        request: Request with comma-separated tickers
        
    Returns:
        JSON response with added stocks and invalid tickers
    """
    from app.services.watchlist_service import add_stocks_to_watchlist
    
    if not request or not request.tickers:
        raise HTTPException(status_code=400, detail="Tickers are required")
    
    # Parse tickers
    ticker_list = [t.strip().upper() for t in request.tickers.split(',') if t.strip()]
    
    if not ticker_list:
        raise HTTPException(status_code=400, detail="At least one ticker is required")
    
    try:
        added_stocks, invalid_tickers = add_stocks_to_watchlist(watchlist_id, ticker_list)
        
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
async def remove_stock_from_watchlist(watchlist_id: UUID = FPath(...), ticker: str = FPath(...)):
    """
    Remove a stock from a watchlist.
    
    Args:
        watchlist_id: UUID of the watchlist
        ticker: Stock ticker symbol
        
    Returns:
        JSON response with deletion status
    """
    from app.services.watchlist_service import remove_stock_from_watchlist
    
    try:
        remove_stock_from_watchlist(watchlist_id, ticker)
        return {"message": f"Stock {ticker} removed from watchlist"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/test/stock-price")
async def test_stock_price_page(request: Request, ticker: str = Query("", description="Stock ticker symbol")):
    """
    Test page for displaying stock price data from database.
    
    Args:
        ticker: Optional stock ticker symbol to display
        
    Returns:
        HTML page with stock price data
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
            "dma_200": float(price.dma_200) if price.dma_200 else None
        })
    
    attributes_data = None
    if attributes:
        attributes_data = {
            "ticker": attributes.ticker,
            "earliest_date": attributes.earliest_date.isoformat(),
            "latest_date": attributes.latest_date.isoformat(),
            "dividend_amt": float(attributes.dividend_amt) if attributes.dividend_amt else None,
            "dividend_yield": float(attributes.dividend_yield) if attributes.dividend_yield else None
        }
    
    return templates.TemplateResponse("test_stock_price.html", {
        "request": request,
        "ticker": ticker if ticker else "",
        "prices": prices_data,
        "attributes": attributes_data,
        "error_message": error_message
    })


@app.post("/test/stock-price/fetch")
async def fetch_stock_price_data(ticker: str = Query(..., description="Stock ticker symbol")):
    """
    Fetch and save stock price data from yfinance.
    
    Args:
        ticker: Stock ticker symbol
        
    Returns:
        JSON response with fetch status
    """
    from app.services.stock_price_service import fetch_and_save_stock_prices
    
    if not ticker or not ticker.strip():
        raise HTTPException(status_code=400, detail="Ticker is required")
    
    try:
        ticker = ticker.strip().upper()
        price_data, new_records = fetch_and_save_stock_prices(ticker)
        
        return {
            "message": f"Successfully fetched and saved {new_records} new records",
            "ticker": ticker,
            "new_records": new_records,
            "data_points": len(price_data)
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching data: {str(e)}")



