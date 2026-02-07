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

## Development Workflow

**CRITICAL**: All code changes MUST follow this workflow. No exceptions.

### 1. Make Changes & Add Tests
- **All code changes require test cases** (excludes documentation/config files)
- When adding new functionality:
  - Backend changes: Add unit/integration tests
  - New API endpoints with UI: Add Playwright browser tests
  - Backend-only API endpoints: Add API/integration tests only
  - UI changes (new pages, interactions, styling): Add/update/remove Playwright tests
- **Review code for simplicity**: Before writing tests, refactor code to make it testable and simple
  - Simpler code = simpler tests = easier maintenance

### 2. Run Tests in Docker
```bash
# MANDATORY: Run ALL tests in a fresh Docker container before committing
./scripts/run-tests-local.sh all
```
- **Why all tests?** Backend changes can affect UI, so we always run the full suite
- Tests MUST pass 100% before proceeding to commit
- If tests fail, fix the issues and re-run until all pass

### 3. Commit Changes
```bash
git add <files>
git commit -m "Descriptive message

Details about the change...

Co-Authored-By: Claude <noreply@anthropic.com>"
```
- Bundle related changes into a single commit (implementation + tests + fixes)
- Use descriptive commit messages with context

### 4. Push to Main
```bash
git push origin main
```
- Push immediately after local commit
- Never leave commits unpushed

### 5. Wait for Deployment
- Monitor Railway deployment status
- Wait for deployment to complete before verification

### 6. Verify in Production
**Production URL:** `https://my.arthos.app`

**Required verification steps (automated by Claude):**

a. **Check Railway logs for errors**
   ```bash
   # Automatically check logs after deployment
   /opt/homebrew/bin/railway logs --json | tail -100
   ```
   - Scan for errors that only appear in production
   - Look for stack traces, 500 errors, database errors
   - Check for any unexpected warnings
   - Report any issues found

b. **Run Playwright tests against production**
   ```bash
   # Run browser tests against production URL
   TEST_SERVER_URL=https://my.arthos.app pytest tests/test_*_browser.py -v
   ```
   - Test all user-facing functionality works in production
   - Use dedicated test account credentials (stored in environment/config)
   - Verify changed pages/flows work correctly
   - Report any failures or UI issues

c. **Monitor error tracking**
   - Check Sentry (if configured) for new errors
   - Verify no new exceptions were introduced

**Test Account Setup:**
- Dedicated Google test account with known credentials
- Store credentials securely (environment variables or config)
- Used for automated Playwright testing against production

### 7. Fix Production Issues (if any)
If errors are found:
1. Investigate and fix locally
2. Test the fix locally (Docker tests must pass)
3. Commit and push to main
4. Verify fix in production
5. Repeat until production is clean

### Exceptions
- **Documentation-only changes**: Skip testing, push directly
- **Config files outside code**: Skip testing (e.g., `.gitignore`, `README.md`)
- **Emergency hotfixes**: Follow same workflow (will revisit fast-track process in future)

### Quick Reference
```bash
# Complete workflow in one go:
./scripts/run-tests-local.sh all && \
git add -A && \
git commit -m "Your message" && \
git push origin main && \
echo "Now verify in production!"
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

### Table Naming
- **Always verify table names from model `__tablename__`** - don't assume based on patterns
- Table names are inconsistent: `watchlist_stocks` (plural) vs `stock_price` (singular)
- When writing raw SQL, check the model definition first:
  - `StockPrice` → `stock_price`
  - `StockAttributes` → `stock_attributes`
  - `WatchListStock` → `watchlist_stocks`
  - `WatchList` → `watchlist`
  - `LLMModel` → `llm_model`
  - `AppSettings` → `app_settings`

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
- **Template conditionals with enums/ratios**: When displaying badges or labels based on enum-like values (e.g., RR ratios: '1:1', '1:2', '1:3', 'Collar'), ensure ALL valid values are handled. Don't use `else` as a catch-all assuming only one default - explicitly check each value to avoid incorrect displays.
- **Consistent styling across related pages**: When the same data (e.g., ratio badges) appears on multiple pages (list view and detail view), ensure colors/styling are consistent. Check existing pages for the established color scheme before adding new styles.

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

## Environment Variables

Required environment variables for production:
- `DATABASE_URL` - PostgreSQL connection string
- `SECRET_KEY` - Session secret for authentication
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - OAuth for Google login
- `OPENROUTER_API_KEY` - API key for OpenRouter (required for LLM insights)
- `OPENROUTER_MODEL` - (optional) Fallback model if DB has no models configured, defaults to `anthropic/claude-3.5-sonnet`
- `SENTRY_DSN` - (optional) Error tracking

## Deployment Notes

### Railway Deployment
- Deploy script: `railway_deploy.py` runs migrations before app starts
- Logs: `railway logs --json` to view deployment/runtime logs
- Redeploy: `railway redeploy --yes` (may fail if build in progress)
- Cache issues: Add a cache bust comment to `requirements.txt` if Railway uses stale builds

### Python Dependencies
- **Google Generative AI SDK**: Don't pin `protobuf` version - let pip resolve it automatically. The SDK has specific protobuf requirements (`<6.0.0`) that conflict with newer versions.
- Always test dependency changes locally before deploying