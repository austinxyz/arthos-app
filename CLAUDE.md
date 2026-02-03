# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Arthos is a Python investment analysis web application built with FastAPI, SQLModel, and yfinance. It provides stock data analysis with technical indicators (SMAs, standard deviation signals), watchlist management, options analysis (covered calls, risk reversals), and interactive candlestick charts.

## Common Commands

### Running the Application
```bash
python run.py
# or
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Testing
```bash
# CRITICAL: Always run tests in Docker before pushing to main
./scripts/run-tests-local.sh unit

# Run all tests including browser tests
./scripts/run-tests-local.sh all

# Run specific test file in Docker
./scripts/run-tests-local.sh tests/test_specific.py

# Quick local test (non-Docker, for fast iteration)
pytest tests/test_specific.py -v

# Run tests excluding browser/e2e
pytest tests/ -v -k "not browser and not e2e"

# Run with random order to detect test dependencies
pytest --random-order
```

### Pre-Push Workflow
```bash
docker-compose -f docker-compose.test.yml up test-runner --abort-on-container-exit
```

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
- `app/models/account.py` - User accounts (OIDC/Google auth)

### Database
- **PostgreSQL for both local development and production** (consistency is critical)
- Local dev: `docker-compose -f docker-compose.dev.yml up -d` then set `DATABASE_URL=postgresql://arthos:arthos_dev@localhost:5432/arthos`
- Production: Railway PostgreSQL (set `DATABASE_URL` environment variable)

### UUID Handling
- **Always use UUID type consistently** - both in models and database columns
- All ID fields (watchlist_id, account_id, rr_uuid) should use UUID type in PostgreSQL
- When accepting UUID parameters in service functions, use `Union[UUID, str]` type hints
- Always convert to string using `to_str()` from `app/utils/type_helpers.py` before database operations
- This prevents "operator does not exist: character varying = uuid" errors in PostgreSQL

## Testing Guidelines

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
- Set up dialog handlers BEFORE clicking buttons that trigger them

### Common Pitfalls
- `pd.isinf()` doesn't exist - use `np.isinf()` from numpy
- Normalize timestamps to timezone-naive: `df.index.tz_localize(None)`

### Database Migrations
**CRITICAL**: When adding new columns to existing SQLModel models:
- `create_db_and_tables()` only creates NEW tables, it does NOT add columns to existing tables
- You MUST add an explicit migration in `railway_deploy.py` for any new columns
- Example pattern for adding columns:
```python
def add_new_columns():
    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        # Check if column exists
        result = conn.execute(text("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'your_table' AND column_name = 'new_column'
        """))
        if not result.scalar():
            conn.execute(text("ALTER TABLE your_table ADD COLUMN new_column TEXT"))
```
- Always test migrations locally with PostgreSQL before pushing to production

## UI Standards

### Color Coding for Financial Data
- **Prices (NO color)**: Entry Price, Current Price, Net Cost, Strike, Premiums - display without color, use minus sign for negatives
- **Changes/Returns (WITH color)**: Change, Change %, Total Return - green for positive, red for negative

## API Structure

### Stock Endpoints
- `GET /v1/stock?q={ticker}` - Get stock metrics (SMA, signal, price)
- `GET /stock/{ticker}` - Stock detail page with chart
- `GET /results?tickers={csv}` - Multi-ticker results page

### Watchlist Endpoints
- `GET/POST /v1/watchlist` - List/create watchlists
- `GET/PUT/DELETE /v1/watchlist/{id}` - Watchlist CRUD
- `POST /v1/watchlist/{id}/stocks` - Add stocks
- `DELETE /v1/watchlist/{id}/stocks/{ticker}` - Remove stock

### Debug Endpoints (development)
- `GET /debug/stock-price?ticker={ticker}` - View stock price data
- `GET /debug/scheduler-log` - View scheduler logs
- `POST /debug/scheduler-log/trigger` - Manually trigger scheduler