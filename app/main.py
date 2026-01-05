"""FastAPI application for Arthos investment analysis."""
from fastapi import FastAPI, Request, HTTPException, Query, Path as FPath
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from pathlib import Path
from uuid import UUID
from app.services.stock_service import get_stock_metrics
from app.database import create_db_and_tables
from pydantic import BaseModel

# Initialize FastAPI app
app = FastAPI(title="Arthos", description="Investment Analysis Platform")

# Initialize database tables on startup
@app.on_event("startup")
async def startup_event():
    """Initialize database tables on application startup."""
    create_db_and_tables()
    # Purge cache entries with invalid versions (e.g., when cache structure changes)
    # This is done in a try-except to handle cases where the cache_version column
    # doesn't exist yet in the database (will be created on next cache write)
    try:
        from app.services.cache_service import purge_invalid_cache_versions
        purged_count = purge_invalid_cache_versions()
        if purged_count > 0:
            print(f"Purged {purged_count} cache entries with invalid versions")
    except Exception as e:
        # Don't crash startup if cache purging fails
        print(f"Warning: Could not purge invalid cache versions on startup: {e}")

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


@app.get("/portfolios")
async def list_portfolios_page(request: Request):
    """
    Display list of all portfolios.
    
    Returns:
        HTML page with list of portfolios
    """
    from app.services.portfolio_service import get_all_portfolios
    
    portfolios = get_all_portfolios()
    
    # Format dates for display
    portfolios_data = []
    for p in portfolios:
        portfolios_data.append({
            "portfolio_id": str(p.portfolio_id),
            "portfolio_name": p.portfolio_name,
            "date_added": p.date_added.strftime("%Y-%m-%d %H:%M:%S"),
            "date_modified": p.date_modified.strftime("%Y-%m-%d %H:%M:%S")
        })
    
    return templates.TemplateResponse("portfolios.html", {
        "request": request,
        "portfolios": portfolios_data
    })


@app.get("/create-portfolio")
async def create_portfolio_page(request: Request):
    """
    Display create portfolio page.
    
    Returns:
        HTML page for creating a new portfolio
    """
    return templates.TemplateResponse("create_portfolio.html", {"request": request})


@app.get("/portfolio/{portfolio_id}")
async def portfolio_details_page(request: Request, portfolio_id: UUID = FPath(...)):
    """
    Display portfolio details page with stocks.
    
    Args:
        portfolio_id: UUID of the portfolio
        
    Returns:
        HTML page with portfolio details and stocks
    """
    from app.services.portfolio_service import get_portfolio, get_portfolio_stocks
    from app.services.stock_service import get_multiple_stock_metrics
    
    portfolio = get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(status_code=404, detail="Portfolio not found")
    
    # Get stocks in portfolio
    portfolio_stocks = get_portfolio_stocks(portfolio_id)
    ticker_list = [s.ticker for s in portfolio_stocks]
    
    # Fetch metrics for all tickers
    metrics_list = []
    if ticker_list:
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
            # If there's an error fetching metrics, still show the page with error messages
            pass
    
    return templates.TemplateResponse("portfolio_details.html", {
        "request": request,
        "portfolio": {
            "portfolio_id": str(portfolio.portfolio_id),
            "portfolio_name": portfolio.portfolio_name,
            "date_added": portfolio.date_added.strftime("%Y-%m-%d %H:%M:%S"),
            "date_modified": portfolio.date_modified.strftime("%Y-%m-%d %H:%M:%S")
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
    from app.services.stock_service import get_stock_metrics
    
    ticker = ticker.strip().upper()
    
    try:
        # Get chart data
        chart_data = get_stock_chart_data(ticker)
        
        # Get metrics for display
        metrics = get_stock_metrics(ticker)
        
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
    Fetch past 365 days of stock data and compute metrics.
    Uses caching to avoid unnecessary yfinance API calls (60-minute cache).
    
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
        - data_points: Number of data points fetched
        - cached: Boolean indicating if data came from cache
        - cache_timestamp: ISO timestamp of cache entry (only if cached=true)
    """
    if not q or not q.strip():
        raise HTTPException(status_code=400, detail="Ticker symbol (q) is required")
    
    try:
        metrics = get_stock_metrics(q.strip().upper())
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


# Portfolio API Models
class PortfolioCreate(BaseModel):
    portfolio_name: str


class PortfolioUpdate(BaseModel):
    portfolio_name: str


class AddStocksRequest(BaseModel):
    tickers: str  # Comma-separated tickers


# Portfolio API Endpoints
@app.get("/v1/portfolio")
async def list_portfolios():
    """
    List all portfolios.
    
    Returns:
        JSON response with list of portfolios
    """
    from app.services.portfolio_service import get_all_portfolios
    
    portfolios = get_all_portfolios()
    return {
        "portfolios": [
            {
                "portfolio_id": str(p.portfolio_id),
                "portfolio_name": p.portfolio_name,
                "date_added": p.date_added.isoformat(),
                "date_modified": p.date_modified.isoformat()
            }
            for p in portfolios
        ]
    }


@app.get("/v1/portfolio/{portfolio_id}")
async def get_portfolio(portfolio_id: UUID = FPath(...)):
    """
    Get portfolio details.
    
    Args:
        portfolio_id: UUID of the portfolio
        
    Returns:
        JSON response with portfolio details and stocks
    """
    from app.services.portfolio_service import get_portfolio, get_portfolio_stocks
    
    try:
        portfolio = get_portfolio(portfolio_id)
        stocks = get_portfolio_stocks(portfolio_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    return {
        "portfolio_id": str(portfolio.portfolio_id),
        "portfolio_name": portfolio.portfolio_name,
        "date_added": portfolio.date_added.isoformat(),
        "date_modified": portfolio.date_modified.isoformat(),
        "stocks": [
            {
                "ticker": s.ticker,
                "date_added": s.date_added.isoformat()
            }
            for s in stocks
        ]
    }


@app.post("/v1/portfolio")
async def create_portfolio(portfolio: PortfolioCreate):
    """
    Create a new portfolio.
    
    Args:
        portfolio: Portfolio creation request with portfolio_name
        
    Returns:
        JSON response with created portfolio
    """
    from app.services.portfolio_service import create_portfolio
    
    try:
        new_portfolio = create_portfolio(portfolio.portfolio_name)
        return {
            "portfolio_id": str(new_portfolio.portfolio_id),
            "portfolio_name": new_portfolio.portfolio_name,
            "date_added": new_portfolio.date_added.isoformat(),
            "date_modified": new_portfolio.date_modified.isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/v1/portfolio/{portfolio_id}")
async def update_portfolio(portfolio_id: UUID = FPath(...), portfolio: PortfolioUpdate = None):
    """
    Update portfolio name.
    
    Args:
        portfolio_id: UUID of the portfolio
        portfolio: Portfolio update request with portfolio_name
        
    Returns:
        JSON response with updated portfolio
    """
    from app.services.portfolio_service import update_portfolio_name
    
    if not portfolio:
        raise HTTPException(status_code=400, detail="Portfolio name is required")
    
    try:
        updated_portfolio = update_portfolio_name(portfolio_id, portfolio.portfolio_name)
        if not updated_portfolio:
            raise HTTPException(status_code=404, detail="Portfolio not found")
        
        return {
            "portfolio_id": str(updated_portfolio.portfolio_id),
            "portfolio_name": updated_portfolio.portfolio_name,
            "date_added": updated_portfolio.date_added.isoformat(),
            "date_modified": updated_portfolio.date_modified.isoformat()
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/v1/portfolio/{portfolio_id}")
async def delete_portfolio(portfolio_id: UUID = FPath(...)):
    """
    Delete a portfolio and all its stocks (cascade delete).
    
    Args:
        portfolio_id: UUID of the portfolio
        
    Returns:
        JSON response with deletion status
    """
    from app.services.portfolio_service import delete_portfolio
    
    try:
        delete_portfolio(portfolio_id)
        return {"message": "Portfolio deleted successfully"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/v1/portfolio/{portfolio_id}/stocks")
async def add_stocks_to_portfolio(portfolio_id: UUID = FPath(...), request: AddStocksRequest = None):
    """
    Add stocks to a portfolio.
    
    Args:
        portfolio_id: UUID of the portfolio
        request: Request with comma-separated tickers
        
    Returns:
        JSON response with added stocks
    """
    from app.services.portfolio_service import add_stocks_to_portfolio
    
    if not request or not request.tickers:
        raise HTTPException(status_code=400, detail="Tickers are required")
    
    # Parse tickers
    ticker_list = [t.strip().upper() for t in request.tickers.split(',') if t.strip()]
    
    if not ticker_list:
        raise HTTPException(status_code=400, detail="At least one ticker is required")
    
    try:
        added_stocks = add_stocks_to_portfolio(portfolio_id, ticker_list)
        return {
            "message": f"Added {len(added_stocks)} stock(s) to portfolio",
            "added_stocks": [
                {
                    "ticker": s.ticker,
                    "date_added": s.date_added.isoformat()
                }
                for s in added_stocks
            ]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/v1/portfolio/{portfolio_id}/stocks/{ticker}")
async def remove_stock_from_portfolio(portfolio_id: UUID = FPath(...), ticker: str = FPath(...)):
    """
    Remove a stock from a portfolio.
    
    Args:
        portfolio_id: UUID of the portfolio
        ticker: Stock ticker symbol
        
    Returns:
        JSON response with deletion status
    """
    from app.services.portfolio_service import remove_stock_from_portfolio
    
    try:
        remove_stock_from_portfolio(portfolio_id, ticker)
        return {"message": f"Stock {ticker} removed from portfolio"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))



