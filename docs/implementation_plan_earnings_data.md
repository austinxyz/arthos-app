# Implementation Plan: Adding Next Earnings Date to Stock Metrics

## Executive Summary

yfinance provides earnings data through two methods:
1. **`stock.info['earningsTimestamp']`** - Unix timestamp for next earnings date (recommended)
2. **`stock.get_earnings_dates()`** - DataFrame with historical and future earnings dates (requires `lxml`)

**Recommended Approach**: Use `stock.info['earningsTimestamp']` as it's simpler, more reliable, and doesn't require additional dependencies.

## Data Availability Analysis

### Testing Results

✅ **`stock.info['earningsTimestamp']`** - Available and reliable
- Returns Unix timestamp for next earnings date
- Available for major stocks (AAPL, MSFT, GOOGL, TSLA, NVDA tested)
- Some stocks may have past dates (e.g., META had 2025-10-29) - need to filter for future dates only
- ETFs and some stocks don't have earnings data (returns None) - handle gracefully
- Includes `isEarningsDateEstimate` flag to indicate if date is estimated
- Example: AAPL returns `1769720400` → `2026-01-29`

✅ **`stock.get_earnings_dates()`** - Available but requires `lxml`
- Returns DataFrame with historical and future earnings dates
- Includes EPS estimates and actuals
- Requires `lxml` dependency (not currently in requirements.txt)
- More data but more complex to parse

### Recommendation

**Use `stock.info['earningsTimestamp']`** because:
- ✅ Already fetching `stock.info` for dividend data
- ✅ No additional dependencies needed
- ✅ Simpler to implement
- ✅ Reliable across multiple tickers
- ✅ Includes estimate flag

## Implementation Plan

### Phase 1: Database Schema Changes

#### 1.1 Add `next_earnings_date` to `StockAttributes` Model

**File**: `app/models/stock_price.py`

```python
class StockAttributes(SQLModel, table=True):
    # ... existing fields ...
    next_earnings_date: Optional[date] = Field(
        default=None,
        description="Next earnings announcement date"
    )
    is_earnings_date_estimate: Optional[bool] = Field(
        default=None,
        description="Whether the earnings date is an estimate"
    )
```

#### 1.2 Database Migration

**File**: `app/database.py`

Add migration function to add new columns to existing `stock_attributes` table:
- `next_earnings_date` (DATE, nullable)
- `is_earnings_date_estimate` (BOOLEAN, nullable)

### Phase 2: Data Fetching and Storage

#### 2.1 Update `fetch_and_save_stock_prices()` Function

**File**: `app/services/stock_price_service.py`

In the section where we fetch dividend information from yfinance (around line 584-638):

```python
# After fetching dividend data, also fetch earnings data
earnings_timestamp = info.get('earningsTimestamp')
next_earnings_date = None
is_earnings_date_estimate = None

earnings_timestamp = info.get('earningsTimestamp')
next_earnings_date = None
is_earnings_date_estimate = None

if earnings_timestamp:
    try:
        # Convert Unix timestamp to date
        earnings_date = datetime.fromtimestamp(earnings_timestamp).date()
        today = date.today()
        
        # Only store if it's a future date
        if earnings_date > today:
            next_earnings_date = earnings_date
            is_earnings_date_estimate = info.get('isEarningsDateEstimate', False)
        # If date is today or past, don't store (earnings already happened or no upcoming earnings)
    except (ValueError, OSError) as e:
        # Invalid timestamp - log and skip
        logger.warning(f"Invalid earnings timestamp for {ticker_upper}: {e}")
```

#### 2.2 Update `update_stock_attributes()` Function

**File**: `app/services/stock_price_service.py`

Add parameters for earnings data:
```python
def update_stock_attributes(
    ticker: str, 
    earliest_date: date, 
    latest_date: date, 
    dividend_amt: Optional[Decimal] = None, 
    dividend_yield: Optional[Decimal] = None,
    current_price: Optional[float] = None,
    next_earnings_date: Optional[date] = None,
    is_earnings_date_estimate: Optional[bool] = None
):
    # ... update logic ...
```

#### 2.3 Update Scheduler Logic

**File**: `app/services/scheduler_service.py`

The scheduler already calls `fetch_and_save_stock_prices()` which will automatically update earnings data. No changes needed.

### Phase 3: Data Retrieval and Display

#### 3.1 Update `get_watchlist_stocks_with_metrics()`

**File**: `app/services/watchlist_service.py`

Add `next_earnings_date` and `is_earnings_date_estimate` to the metrics dictionary returned for each stock (around line 395-420).

#### 3.2 Update `get_stock_metrics_from_db()`

**File**: `app/services/stock_price_service.py`

Add `next_earnings_date` and `is_earnings_date_estimate` to the returned metrics dictionary (around line 820-831).

### Phase 4: UI Updates

#### 4.1 Watchlist Table

**File**: `app/templates/watchlist_details.html`

Add a new column "Next Earnings" to the stocks table:
- Display date in format: "Jan 29, 2026" or "N/A"
- Add "(Est.)" suffix if `is_earnings_date_estimate` is True
- Position: After "Dividend Yield" column

**Table Structure**:
```html
<th>Next Earnings</th>
...
<td>
    {% if metric.next_earnings_date %}
        {{ metric.next_earnings_date.strftime('%b %d, %Y') }}
        {% if metric.is_earnings_date_estimate %}<small class="text-muted">(Est.)</small>{% endif %}
    {% else %}
        <span class="text-muted">N/A</span>
    {% endif %}
</td>
```

#### 4.2 Stock Detail Page

**File**: `app/templates/stock_detail.html`

Add earnings date to the metrics cards section:
- Display in a metrics card similar to dividend yield
- Format: "Next Earnings: Jan 29, 2026 (Est.)" or "Next Earnings: N/A"
- Position: Near dividend yield or in a separate card

### Phase 5: Testing

#### 5.1 Unit Tests

**File**: `tests/test_stock_price_service.py`

- Test that `next_earnings_date` is fetched and stored correctly
- Test that `is_earnings_date_estimate` flag is stored
- Test that past earnings dates are not stored
- Test that missing earnings data is handled gracefully

#### 5.2 Integration Tests

**File**: `tests/test_watchlist_service.py`

- Test that `get_watchlist_stocks_with_metrics()` includes earnings data
- Test that earnings data appears in watchlist display

#### 5.3 Browser Tests

**File**: `tests/test_watchlist_browser.py`

- Test that earnings date column appears in watchlist table
- Test that earnings date displays correctly (with/without estimate flag)
- Test that "N/A" displays when earnings date is not available

**File**: `tests/test_stock_detail_browser.py`

- Test that earnings date appears on stock detail page
- Test formatting and estimate flag display

## Data Flow

### Current Flow (Dividend Data)
1. Stock added to watchlist → `fetch_and_save_stock_prices()` called
2. `fetch_and_save_stock_prices()` fetches `stock.info` from yfinance
3. Extracts `dividendRate` and `dividendYield`
4. Calls `update_stock_attributes()` to store in database
5. Scheduler runs hourly → calls `fetch_and_save_stock_prices()` → updates dividend data

### New Flow (Earnings Data)
1. Stock added to watchlist → `fetch_and_save_stock_prices()` called
2. `fetch_and_save_stock_prices()` fetches `stock.info` from yfinance
3. Extracts `earningsTimestamp` and `isEarningsDateEstimate`
4. Converts timestamp to date, validates it's in the future
5. Calls `update_stock_attributes()` to store in database
6. Scheduler runs hourly → calls `fetch_and_save_stock_prices()` → updates earnings data
7. Display pages read from `stock_attributes` table (no on-demand yfinance calls)

## Key Design Decisions

### 1. Storage Location
- **Decision**: Store in `stock_attributes` table
- **Rationale**: 
  - Earnings date is a stock attribute (like dividend yield)
  - Not time-series data (unlike stock prices)
  - Updated when we fetch from yfinance (same as dividend data)

### 2. Update Frequency
- **Decision**: Update every time we fetch from yfinance (scheduler + first-time addition)
- **Rationale**: 
  - Earnings dates can change (companies announce new dates)
  - Scheduler already runs hourly during market hours
  - No need for separate update mechanism

### 3. Date Validation
- **Decision**: Only store future earnings dates
- **Rationale**: 
  - Past earnings dates are not useful for display
  - If `earningsTimestamp` is in the past, it means no upcoming earnings scheduled
  - Keeps database clean

### 4. Estimate Flag
- **Decision**: Store and display `is_earnings_date_estimate` flag
- **Rationale**: 
  - Users should know if date is confirmed or estimated
  - Helps with decision-making (estimated dates may change)

### 5. Display Format
- **Decision**: "Jan 29, 2026" with "(Est.)" suffix if estimate
- **Rationale**: 
  - Human-readable format
  - Consistent with other date displays
  - Clear indication of estimate status

## Dependencies

### New Dependencies
- **None** - `stock.info` is already being used, no new dependencies needed

### Optional Dependencies (if using `get_earnings_dates()`)
- `lxml` - Required for `get_earnings_dates()` method (NOT recommended)

## Error Handling

### Scenarios to Handle

1. **Missing `earningsTimestamp`**:
   - Set `next_earnings_date = None`
   - Display "N/A" in UI

2. **Past `earningsTimestamp`**:
   - Don't store (set to None)
   - Display "N/A" in UI

3. **Invalid timestamp**:
   - Log warning, set to None
   - Display "N/A" in UI

4. **yfinance API failure**:
   - Don't fail the entire fetch
   - Log error, continue with other data
   - Existing earnings date remains in database

## Testing Strategy

### Test Data
- Use real tickers (AAPL, MSFT) that have earnings dates
- Test with tickers that may not have earnings dates
- Test with past earnings dates (should not be stored)

### Test Cases

1. **Unit Tests**:
   - `test_fetch_earnings_date_from_yfinance()`
   - `test_earnings_date_not_stored_if_past()`
   - `test_earnings_date_estimate_flag_stored()`
   - `test_missing_earnings_date_handled_gracefully()`

2. **Integration Tests**:
   - `test_watchlist_includes_earnings_date()`
   - `test_stock_detail_includes_earnings_date()`
   - `test_scheduler_updates_earnings_date()`

3. **Browser Tests**:
   - `test_earnings_date_column_displayed_in_watchlist()`
   - `test_earnings_date_formatted_correctly()`
   - `test_estimate_flag_displayed()`
   - `test_earnings_date_on_stock_detail_page()`

## Rollout Plan

### Step 1: Database Migration
- Add columns to `stock_attributes` table
- Test migration on local database

### Step 2: Backend Implementation
- Update `fetch_and_save_stock_prices()` to fetch earnings data
- Update `update_stock_attributes()` to store earnings data
- Update `get_watchlist_stocks_with_metrics()` to include earnings data
- Update `get_stock_metrics_from_db()` to include earnings data

### Step 3: Frontend Implementation
- Add "Next Earnings" column to watchlist table
- Add earnings date to stock detail page
- Test UI rendering

### Step 4: Testing
- Run all unit tests
- Run integration tests
- Run browser tests
- Test in Docker environment

### Step 5: Deployment
- Commit and push changes
- Verify in production
- Monitor for any issues

## Potential Issues and Mitigations

### Issue 1: Earnings Date Not Available for Some Stocks
- **Mitigation**: Display "N/A" gracefully, don't break the UI

### Issue 2: Earnings Date Changes Frequently
- **Mitigation**: Scheduler updates hourly, so changes will be reflected within an hour

### Issue 3: Estimate vs Confirmed Dates
- **Mitigation**: Display "(Est.)" flag so users know the date may change

### Issue 4: Timezone Handling
- **Mitigation**: `earningsTimestamp` is Unix timestamp, convert to date (timezone-naive) for storage

## Success Criteria

✅ Earnings date appears in watchlist table
✅ Earnings date appears on stock detail page
✅ Estimate flag is displayed when applicable
✅ "N/A" displays when earnings date is not available
✅ Data is updated by scheduler automatically
✅ No on-demand yfinance calls for display
✅ All tests pass
✅ Works in Docker and GitHub Actions

## Estimated Effort

- **Database Migration**: 30 minutes
- **Backend Implementation**: 2-3 hours
- **Frontend Implementation**: 1-2 hours
- **Testing**: 2-3 hours
- **Total**: ~6-8 hours

## Data Validation Results

### Test Results from Real Tickers

| Ticker | Earnings Date | Is Future | Is Estimate | Status |
|--------|--------------|-----------|-------------|--------|
| AAPL   | 2026-01-29   | Yes       | No          | ✅ Valid |
| MSFT   | 2026-01-28   | Yes       | No          | ✅ Valid |
| GOOGL  | 2026-02-04   | Yes       | No          | ✅ Valid |
| TSLA   | 2026-01-28   | Yes       | No          | ✅ Valid |
| NVDA   | 2026-02-25   | Yes       | No          | ✅ Valid |
| META   | 2025-10-29   | No        | Yes         | ❌ Past date (filter out) |
| BRK.A  | None         | N/A       | N/A         | ⚠️ No data (handle gracefully) |
| SPY    | None         | N/A       | N/A         | ⚠️ ETF (no earnings) |

### Key Observations

1. **Most stocks have earnings data**: Major stocks consistently have `earningsTimestamp`
2. **Some dates may be in the past**: Need to filter for future dates only (e.g., META had past date)
3. **ETFs don't have earnings**: ETFs like SPY return None (expected behavior)
4. **Estimate flag is available**: `isEarningsDateEstimate` indicates if date is confirmed or estimated
5. **Data is reliable**: For stocks that have earnings, the data appears consistent

### Edge Cases to Handle

- **Past earnings dates**: Filter out (don't store)
- **Missing earnings data**: Display "N/A" gracefully
- **ETFs and non-earnings stocks**: Handle None values
- **Invalid timestamps**: Log warning, skip storage

## Next Steps

1. Review and approve this implementation plan
2. Implement Phase 1 (Database Schema)
3. Implement Phase 2 (Data Fetching)
4. Implement Phase 3 (Data Retrieval)
5. Implement Phase 4 (UI Updates)
6. Implement Phase 5 (Testing)
7. Deploy and verify
