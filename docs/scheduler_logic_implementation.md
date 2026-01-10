# Scheduler Logic Implementation Summary

This document summarizes how the implementation matches the requirements.

## Requirements vs Implementation

### 1. Stock ticker when added to watchlist, first enters stock_attributes table

**Status**: ✅ **Implemented**

- When a stock is added via `add_stocks_to_watchlist()`, it validates the ticker exists in yfinance
- Then calls `fetch_and_save_stock_prices()` which creates `stock_attributes` after successful data fetch
- `stock_attributes` is created with `earliest_date` and `latest_date` from the fetched data
- If no data is available, a minimal `stock_attributes` entry is still created

**Location**: `app/services/watchlist_service.py:add_stocks_to_watchlist()`, `app/services/stock_price_service.py:fetch_and_save_stock_prices()`

### 2. On first entry, fetch past 2 years of data and store in stock_price table

**Status**: ✅ **Implemented**

- When `fetch_and_save_stock_prices()` is called and `stock_attributes` doesn't exist, it fetches 2 years of data:
  ```python
  if attributes is None:
      start_date = datetime.now() - timedelta(days=730)
      end_date = datetime.now()
  ```

**Location**: `app/services/stock_price_service.py:fetch_and_save_stock_prices()` (line 268-272)

### 3. latest_date should be set to latest available date (today if trading day)

**Status**: ✅ **Implemented**

- `latest_date` is calculated from the fetched price data:
  ```python
  price_dates = [pd.Timestamp(idx).date() for idx in price_data.index]
  latest_date = max(price_dates)
  ```
- This will be today if it's a trading day and data is available, otherwise the last trading day

**Location**: `app/services/stock_price_service.py:fetch_and_save_stock_prices()` (line 554-556)

### 4. Scheduler refreshes today's data every hour during market hours

**Status**: ✅ **Implemented**

- Scheduler runs every 60 minutes using `IntervalTrigger(minutes=60)`
- `fetch_all_watchlist_stocks()` checks if market is open (9:30 AM - 4:00 PM ET)
- During market hours, it fetches today's data (intraday or daily) for all tickers
- If market is closed, it skips the fetch (logs "Market is closed. Skipped fetch.")

**Location**: `app/services/scheduler_service.py:start_scheduler()`, `fetch_all_watchlist_stocks()`

### 5. After market closes, updates end-of-day data

**Status**: ✅ **Implemented**

- A separate scheduled job runs at 4:00 PM ET using `CronTrigger(hour=16, minute=0)`
- This ensures end-of-day data is fetched after market close

**Location**: `app/services/scheduler_service.py:start_scheduler()` (line 197-203)

### 6. latest_date updated every time stock_price is updated

**Status**: ✅ **Implemented**

- `save_stock_prices()` updates `latest_date` in `stock_attributes` immediately after saving prices:
  ```python
  if latest_date > attributes.latest_date:
      attributes.latest_date = latest_date
  ```
- This happens in `save_stock_prices()` before dividend information is fetched, ensuring `latest_date` is always current

**Location**: `app/services/stock_price_service.py:save_stock_prices()` (line 242-256)

### 7. If scheduler missed days, next run patches missing data

**Status**: ✅ **Implemented**

- `fetch_and_save_stock_prices()` checks `attributes.latest_date` and fetches data from `latest_date + 1` to `today`
- If `latest_date` is stale (e.g., 3 days ago), the next scheduler run will fetch all missing days:
  ```python
  days_since_latest = (today - attributes.latest_date).days
  if days_since_latest > 0:
      next_date = attributes.latest_date + timedelta(days=1)
      # Fetch from next_date to today
  ```

**Location**: `app/services/stock_price_service.py:fetch_and_save_stock_prices()` (line 274-296)

### 8. Manual trigger fills missing data and makes data current

**Status**: ✅ **Implemented**

- `fetch_all_watchlist_stocks_manual(bypass_market_hours=True)` can be called at any time
- It calls `fetch_and_save_stock_prices()` for all tickers, which patches missing data
- `bypass_market_hours=True` allows it to run even when market is closed

**Location**: `app/services/scheduler_service.py:fetch_all_watchlist_stocks_manual()`, `app/main.py:/debug/scheduler-log/trigger`

### 9. Every scheduler run logs to scheduler_log

**Status**: ✅ **Implemented**

- `fetch_all_watchlist_stocks()` creates a `SchedulerLog` entry at the start
- Updates it with `end_time` and `notes` (success/error counts) at the end
- `fetch_all_watchlist_stocks_manual()` does the same

**Location**: `app/services/scheduler_service.py:fetch_all_watchlist_stocks()`, `fetch_all_watchlist_stocks_manual()`

### 10. Never fetch yfinance on demand except first time stock is added

**Status**: ✅ **Implemented**

- Stock detail page (`/stock/{ticker}`) uses `get_stock_chart_data()` and `get_stock_metrics_from_db()` which read from database
- Watchlist page uses `get_watchlist_stocks_with_metrics()` which reads from database
- Only `add_stocks_to_watchlist()` calls `fetch_and_save_stock_prices()` on demand (first time)
- All other data fetching is done by the scheduler

**Location**: 
- `app/main.py:/stock/{ticker}` - reads from DB
- `app/services/watchlist_service.py:get_watchlist_stocks_with_metrics()` - reads from DB
- `app/services/stock_chart_service.py:get_stock_chart_data()` - reads from DB

## Data Flow

1. **Stock Addition**:
   - User adds stock to watchlist → `add_stocks_to_watchlist()`
   - Validates ticker exists in yfinance (only on-demand call)
   - Calls `fetch_and_save_stock_prices()` → fetches 2 years of data
   - Saves to `stock_price` table
   - Creates `stock_attributes` with `earliest_date` and `latest_date`

2. **Scheduler Run (Every Hour)**:
   - `fetch_all_watchlist_stocks()` runs
   - Checks if market is open
   - For each ticker: calls `fetch_and_save_stock_prices()`
   - `fetch_and_save_stock_prices()` checks `latest_date` and fetches only new data
   - Updates `stock_price` table
   - Updates `latest_date` in `stock_attributes`
   - Logs to `scheduler_log`

3. **Post-Market Update (4:00 PM ET)**:
   - Same as hourly run, but ensures end-of-day data is captured

4. **Display**:
   - All pages read from `stock_price` and `stock_attributes` tables
   - No on-demand yfinance calls

## Key Implementation Details

### latest_date Update Timing

`latest_date` is updated in two places:
1. **Immediately after saving prices** in `save_stock_prices()` - ensures it's current even if dividend fetch fails
2. **After dividend fetch** in `fetch_and_save_stock_prices()` - updates with final date range

This ensures `latest_date` is always accurate.

### Missing Data Patching

When `latest_date` is stale:
- `fetch_and_save_stock_prices()` calculates `days_since_latest`
- If > 0, fetches from `latest_date + 1` to `today`
- Uses `period='5d'` fallback if `start/end` dates fail (handles weekends/holidays)

### Market Hours Logic

- Market hours: 9:30 AM - 4:00 PM ET (weekdays only)
- Scheduler runs every 60 minutes
- During market hours: fetches today's data (intraday or daily)
- After market hours: skips fetch (except post-market job at 4:00 PM)
