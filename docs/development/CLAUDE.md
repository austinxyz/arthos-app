# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Arthos is a Python investment analysis web application built with FastAPI, SQLModel, and yfinance. It provides stock data analysis with technical indicators (SMAs, standard deviation signals), watchlist management, options analysis (covered calls, risk reversals), and interactive candlestick charts.

## Common Commands

### Running the Application
```bash
# Start development server
python run.py
# or
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Testing
```bash
# Run all tests (recommended: use Docker to match CI environment)
./scripts/run-tests-local.sh unit

# Run all tests including browser tests
./scripts/run-tests-local.sh all

# Run specific test file
./scripts/run-tests-local.sh tests/test_specific.py

# Quick local test (non-Docker)
pytest tests/test_specific.py -v

# Run tests excluding browser/e2e
pytest tests/ -v -k "not browser and not e2e"

# Run with random order to detect test dependencies
pytest --random-order
```

### Database
- SQLite database (`arthos.db`) is auto-created on first run
- For PostgreSQL: set `DATABASE_URL` environment variable

## Architecture

### Data Provider Pattern
The app uses an abstraction layer for stock data providers:
- `app/providers/base.py` - Abstract `StockDataProvider` class with standardized data classes (`StockPriceData`, `StockInfo`, `OptionQuote`, `OptionsChain`)
- `app/providers/yfinance_provider.py` - YFinance implementation
- `app/providers/marketdata_provider.py` - MarketData API implementation
- `app/providers/factory.py` - Factory for getting the configured provider

### Key Services
- `app/services/stock_service.py` - Core stock data fetching and metric calculation (SMAs, signals, options analysis)
- `app/services/stock_price_service.py` - Database-driven stock price storage and retrieval
- `app/services/watchlist_service.py` - Watchlist CRUD operations
- `app/services/rr_watchlist_service.py` - Risk reversal watchlist tracking
- `app/services/scheduler_service.py` - Background job for fetching stock data every 60 minutes

### Models (SQLModel)
- `app/models/stock_price.py` - `StockPrice` (daily OHLC) and `StockAttributes` (ticker metadata, dividends, earnings)
- `app/models/watchlist.py` - `WatchList` and `WatchListStock`
- `app/models/rr_watchlist.py` - Risk reversal tracking
- `app/models/scheduler_log.py` - Scheduler execution logs

### Templates
Jinja2 templates in `app/templates/` render HTML pages with DataTables for stock metrics display.

## Testing Guidelines

### CRITICAL: Always run tests in Docker before pushing
```bash
./scripts/run-tests-local.sh unit
```
Docker matches the GitHub Actions CI environment exactly.

### Test Data Management
- **Never rely on external APIs (yfinance) in tests** - use `populate_test_stock_prices()` from `tests/conftest.py`
- Clean up database BEFORE populating test data to avoid UNIQUE constraint violations
- Use `autouse=True` fixtures for consistent setup/cleanup

### Model Attribute Names
Use correct attribute names from model definitions:
- `watchlist.watchlist_id` (not `watchlist.id`)
- `StockPrice.price_date`, `StockPrice.close_price`

### Playwright Browser Tests
- Scope locators to specific sections: `page.locator("#option-data th:has-text('Strike')").first`
- Use `.first` for duplicate elements to avoid strict mode violations
- Verify page status codes before asserting on elements
- Set up dialog handlers BEFORE clicking buttons that trigger them

### Common Pitfalls
- `pd.isinf()` doesn't exist - use `np.isinf()` from numpy
- Normalize timestamps to timezone-naive: `df.index.tz_localize(None)`

## API Structure

### Stock Endpoints
- `GET /v1/stock?q={ticker}` - Get stock metrics (SMA, signal, price)
- `GET /stock/{ticker}` - Stock detail page with chart
- `GET /results?tickers={csv}` - Multi-ticker results page

### Watchlist Endpoints
- `GET/POST /v1/watchlist` - List/create watchlists
- `GET/PUT/DELETE /v1/watchlist/{id}` - Watchlist CRUD
- `POST /v1/watchlist/{id}/stocks` - Add stocks to watchlist
- `DELETE /v1/watchlist/{id}/stocks/{ticker}` - Remove stock

### Debug Endpoints (development)
- `GET /debug/stock-price?ticker={ticker}` - View stock price data
- `GET /debug/scheduler-log` - View scheduler logs
- `POST /debug/scheduler-log/trigger` - Manually trigger scheduler
