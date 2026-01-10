# Test Failure Analysis: test_delete_button_visible_for_error_rows

## The Failure

**Test**: `tests/test_watchlist_browser.py::TestWatchListBrowser::test_delete_button_visible_for_error_rows`

**Error in GitHub Actions**:
```
AssertionError: Error message should contain 'error' or 'no price data', got: No stock attributes found for ticker: SDSK
```

**Why it failed in GitHub Actions but not locally:**

## Root Cause Analysis

### Code Flow

1. **Test Setup**:
   - Test manually adds `WatchListStock` entry for "SDSK" to database
   - Does NOT create `StockAttributes` for SDSK (intentionally - to simulate invalid ticker)

2. **When Page Loads**:
   - Calls `get_watchlist_stocks_with_metrics(watchlist_id)`
   - For each stock, it checks in this order:
     ```python
     # Step 1: Check stock_attributes FIRST
     attributes = get_stock_attributes(ticker)
     if not attributes:
         return {"error": "No stock attributes found for ticker: {ticker}"}  # ← Returns here
         continue  # Never reaches step 2
     
     # Step 2: Check stock_price (only if attributes exist)
     if not current_price_record:
         return {"error": "No price data found for ticker: {ticker}"}
     ```

3. **The Issue**:
   - After refactoring to use `stock_attributes` table, the code checks attributes FIRST
   - If attributes don't exist, it returns early with "No stock attributes found"
   - The test was written expecting "no price data" error, but that code path is never reached

### Why It Passed Locally in Docker But Failed in GitHub Actions

**Critical Finding**: The test passed when run locally in Docker, but failed in GitHub Actions. This indicates a difference between the two environments.

**Possible reasons:**

1. **Test Execution Order**:
   - GitHub Actions runs tests in a different order than local Docker
   - Pytest execution order can vary based on:
     - File system order (which can differ between systems)
     - Test discovery order
     - Parallel execution (if enabled)
   - A previous test might have left `StockAttributes` for SDSK that wasn't cleaned up properly
   - The `setup_database` fixture should prevent this, but race conditions or timing issues could occur

2. **Database Transaction Isolation**:
   - PostgreSQL transaction isolation levels might differ
   - GitHub Actions might have different default settings
   - Concurrent test execution could cause isolation issues

3. **Fixture Execution Timing**:
   - The `autouse=True` fixture should run before each test
   - But if tests run in parallel or with different timing, cleanup might not complete
   - GitHub Actions might have different timing characteristics

4. **Code Version at Time of Local Test**:
   - The local Docker test might have run with code that had the fix already applied
   - But the code pushed to GitHub might have been from before the fix
   - This would explain why local passed but GitHub failed

5. **Test Data Population**:
   - The `setup_database` fixture populates test data for AAPL, MSFT, HD
   - If a previous test created `StockAttributes` for SDSK and cleanup didn't work, it might affect this test
   - GitHub Actions' clean environment might expose this issue more clearly

## The Fix

Updated the test assertion to accept all possible error message formats:

```python
# Before (too restrictive):
assert "error" in error_text.lower() or "no price data" in error_text.lower()

# After (more flexible):
assert any(keyword in error_text.lower() for keyword in [
    "error", 
    "no price data", 
    "no stock attributes"
])
```

## Key Learnings

1. **Error Message Order Matters**: When code checks multiple conditions, the order determines which error message is returned
2. **Test Assertions Should Match Current Code**: After refactoring, tests need to be updated to match new error message formats
3. **Clean Database State**: GitHub Actions always starts fresh, so it catches issues that might be hidden by leftover data locally
4. **Test in Docker Before Pushing**: Running tests in Docker (which mimics GitHub Actions) would have caught this earlier

## Prevention

- ✅ Always run tests in Docker before pushing (catches environment differences)
- ✅ Update test assertions when error message logic changes
- ✅ Make test assertions flexible enough to handle multiple valid error formats
- ✅ Review error message logic when refactoring code paths
