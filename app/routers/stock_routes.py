"""
Stock detail, results, and API endpoints for stock data.
"""
from fastapi import APIRouter, Request, HTTPException, Query, Path as FPath
from starlette.templating import Jinja2Templates
from pathlib import Path as PathLib


router = APIRouter()

# Set up templates directory
templates_dir = PathLib(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@router.get("/stock/{ticker}")
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
                get_cached_risk_reversals,
                cache_options_strategies_for_ticker,
            )

            # Fetch covered calls from cache; compute inline on first visit (cache miss).
            try:
                covered_calls = get_cached_covered_calls(ticker)

                if not covered_calls:
                    print(f"No cached options for {ticker} — computing inline")
                    cache_options_strategies_for_ticker(ticker)
                    covered_calls = get_cached_covered_calls(ticker)

            except Exception as e:
                print(f"Error getting covered call returns for {ticker}: {str(e)}")
                import traceback
                traceback.print_exc()
                covered_calls = []

            # Risk reversals are populated by the same cache_options_strategies_for_ticker call above.
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


@router.post("/stock/{ticker}/refresh")
async def refresh_stock_data_endpoint(request: Request, ticker: str = FPath(...)):
    """
    Force refresh all data for a specific ticker.

    Uses the unified refresh_stock_data function that:
    1. Clears the options cache
    2. Fetches fresh stock price data
    3. Recalculates trading metrics (SMAs, signals, IV)
    4. Pre-calculates option strategies (Risk Reversal, Covered Calls)

    This is the same code path used by the scheduler and debug page Force Refresh.
    """
    from app.services.stock_price_service import refresh_stock_data

    ticker = ticker.strip().upper()

    try:
        print(f"Force refresh requested for {ticker} from stock detail page")
        result = refresh_stock_data(ticker, clear_cache=True)

        if result.get("success"):
            return {
                "success": True,
                "message": f"Refreshed {ticker}: {result['price_records']} prices, "
                           f"{result['rr_strategies']} RR, {result['cc_strategies']} CC",
                "details": result,
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


@router.get("/results")
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


@router.get("/v1/stock")
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

    from app.services.stock_price_service import get_stock_metrics_from_db

    try:
        metrics = get_stock_metrics_from_db(q.strip().upper())
        return metrics
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/validate/tickers")
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
