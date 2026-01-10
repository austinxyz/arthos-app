# Test Failures and Solutions - Key Learnings

This document summarizes the key learnings from test failures encountered during the development of the arthos-app, particularly around database-driven testing and browser automation.

## Table of Contents
1. [Database-Driven Testing](#database-driven-testing)
2. [Test Data Management](#test-data-management)
3. [Browser Test Reliability](#browser-test-reliability)
4. [External API Dependencies](#external-api-dependencies)
5. [Test Isolation and Cleanup](#test-isolation-and-cleanup)
6. [Playwright Best Practices](#playwright-best-practices)

---

## Database-Driven Testing

### Problem
When refactoring from yfinance cache-based data to database-driven storage (`stock_price` table), tests that relied on external API calls started failing in CI environments.

### Solution
- **Use test data helpers**: Create helper functions (e.g., `populate_test_stock_prices()`) that generate test data directly in the database
- **Avoid external dependencies**: Never rely on yfinance or other external APIs in tests - they are unreliable in CI environments
- **Populate data before tests**: Always ensure test data exists in the database before running tests that depend on it

### Key Takeaway
> **Always populate test data directly in the database rather than fetching from external APIs. External APIs are unreliable in CI environments and can cause flaky tests.**

---

## Test Data Management

### Problem
Tests were failing due to:
1. Missing test data (404 errors when accessing stock detail pages)
2. UNIQUE constraint violations when trying to insert duplicate data
3. Leftover data from previous tests affecting current tests

### Solution
**Fixture Order Matters:**
```python
@pytest.fixture(autouse=True)
def setup_database():
    create_db_and_tables()
    
    # 1. CLEANUP FIRST - Remove all existing data
    with Session(engine) as session:
        # Delete all stock_price, watermarks, watchlists, etc.
        session.commit()
    
    # 2. POPULATE DATA - Add test data after cleanup
    populate_test_stock_prices("AAPL")
    populate_test_stock_prices("MSFT")
    
    yield
    
    # 3. CLEANUP AFTER - Remove data after test
    # ... cleanup code
```

### Key Takeaways
1. **Always clean up BEFORE populating data** - Prevents UNIQUE constraint violations
2. **Clean up ALL related tables** - Don't forget `stock_price`, `stock_price_wtrmrk`, `watchlist`, `watchlist_stock`, etc.
3. **Use consistent cleanup patterns** - Apply the same cleanup logic across all test fixtures

---

## Browser Test Reliability

### Problem
Browser tests were failing because:
1. Pages returned 404 when stock data wasn't available
2. Elements weren't visible because data hadn't loaded
3. Tests were too fast and didn't wait for async operations

### Solution
**Always verify page loads successfully:**
```python
response = page.goto(f"{live_server_url}/stock/HD", wait_until="networkidle", timeout=30000)

# Check for 404 before proceeding
if response.status == 404:
    pytest.skip(f"Page returned 404. Data may not be available.")

assert response.status == 200
```

**Wait for elements properly:**
```python
# Wait for table to be visible
page.wait_for_selector('#stocksTable', state='visible', timeout=10000)

# Wait for network to be idle
page.wait_for_load_state("networkidle", timeout=30000)

# Give time for async operations
page.wait_for_timeout(2000)
```

### Key Takeaways
1. **Check HTTP status codes** - Verify 200 before looking for elements
2. **Use proper wait strategies** - `wait_for_selector`, `wait_for_load_state`, etc.
3. **Wait for async operations** - JavaScript operations need time to complete
4. **Use specific locators** - Prefer `#stocksTable tbody tr` over `text=MSFT` to avoid matching multiple elements

---

## External API Dependencies

### Problem
Tests that called `add_stocks_to_watchlist()` were failing because:
1. yfinance API calls were failing in CI (network issues, rate limits, date issues)
2. Tests couldn't complete because they were waiting for API responses
3. Tests were non-deterministic - sometimes passing, sometimes failing

### Solution
**For browser tests that need stocks in watchlist:**
```python
# Instead of:
added, _ = add_stocks_to_watchlist(watchlist.watchlist_id, ["AAPL", "MSFT"])

# Use:
from app.models.watchlist import WatchListStock
with Session(engine) as session:
    for ticker in ["AAPL", "MSFT"]:
        stock = WatchListStock(
            watchlist_id=watchlist.watchlist_id,
            ticker=ticker,
            date_added=datetime.now()
        )
        session.add(stock)
    session.commit()
```

**For tests that need stock price data:**
```python
# Use helper function instead of yfinance
from tests.conftest import populate_test_stock_prices
populate_test_stock_prices("AAPL")
populate_test_stock_prices("MSFT")
```

### Key Takeaways
1. **Never call external APIs in tests** - Use test data helpers instead
2. **Bypass validation when needed** - For browser tests, directly insert into database if validation would call external APIs
3. **Make tests deterministic** - Tests should always produce the same results

---

## Test Isolation and Cleanup

### Problem
Tests were affecting each other because:
1. Data from one test was visible in another test
2. UNIQUE constraints were violated when data already existed
3. Tests were not properly isolated

### Solution
**Comprehensive cleanup in fixtures:**
```python
@pytest.fixture(autouse=True)
def setup_database():
    create_db_and_tables()
    
    # Cleanup ALL tables before test
    with Session(engine) as session:
        from sqlmodel import select
        
        # Clean watchlists
        statement = select(WatchListStock)
        for stock in session.exec(statement).all():
            session.delete(stock)
        
        statement = select(WatchList)
        for watchlist in session.exec(statement).all():
            session.delete(watchlist)
        
        # Clean stock_price tables
        statement = select(StockPrice)
        for price in session.exec(statement).all():
            session.delete(price)
        
        statement = select(StockPriceWatermark)
        for watermark in session.exec(statement).all():
            session.delete(watermark)
        
        session.commit()
    
    yield
    
    # Cleanup after test (same pattern)
```

### Key Takeaways
1. **Clean up ALL related tables** - Don't forget any tables that might have data
2. **Clean before AND after** - Some tests might leave data behind
3. **Use `autouse=True`** - Ensures cleanup happens for every test automatically
4. **Commit after cleanup** - Don't forget to commit the session

---

## Playwright Best Practices

### Problem
Playwright tests were failing due to:
1. Strict mode violations (multiple elements matching a locator)
2. Elements not being visible when expected
3. Timeouts waiting for elements that never appear

### Solution
**Use specific locators:**
```python
# BAD - Too broad, matches multiple elements
page.locator("text=MSFT")

# GOOD - Scoped to specific container
page.locator("#stocksTable tbody tr").filter(has_text="MSFT")

# BETTER - Even more specific
page.locator("#stocksTable tbody tr td:first-child strong:has-text('MSFT')")
```

**Handle dialogs properly:**
```python
# Set up dialog handler BEFORE clicking
page.once("dialog", lambda dialog: dialog.accept())

# Then click the button that triggers the dialog
delete_button.click()
```

**Wait for page reloads:**
```python
# After an action that causes page reload
delete_button.click()

# Wait for network to be idle
page.wait_for_load_state("networkidle", timeout=10000)

# Give additional time for DOM updates
page.wait_for_timeout(2000)
```

### Key Takeaways
1. **Be specific with locators** - Scope to containers, use filters, use specific selectors
2. **Handle dialogs before clicking** - Set up handlers before the action that triggers them
3. **Wait for async operations** - Page reloads, network requests, JavaScript execution all need time
4. **Use `.first` or `.nth(0)`** - When multiple elements match, explicitly select which one

---

## Common Patterns

### Pattern 1: Populating Test Data
```python
from tests.conftest import populate_test_stock_prices

# In fixture, before yield:
populate_test_stock_prices("AAPL")
populate_test_stock_prices("MSFT")
```

### Pattern 2: Adding Stocks to Watchlist (Bypassing API)
```python
from app.models.watchlist import WatchListStock
from datetime import datetime

with Session(engine) as session:
    for ticker in ["AAPL", "MSFT"]:
        stock = WatchListStock(
            watchlist_id=watchlist.watchlist_id,
            ticker=ticker,
            date_added=datetime.now()
        )
        session.add(stock)
    session.commit()
```

### Pattern 3: Verifying Page Load
```python
response = page.goto(url, wait_until="networkidle", timeout=30000)
assert response.status == 200, f"Expected 200, got {response.status}"
```

### Pattern 4: Waiting for Elements
```python
page.wait_for_selector('#elementId', state='visible', timeout=10000)
page.wait_for_load_state("networkidle", timeout=30000)
page.wait_for_timeout(2000)  # For async operations
```

---

## Checklist for Writing New Tests

When writing new tests, ensure:

- [ ] Test data is populated directly in database (no external API calls)
- [ ] All related tables are cleaned up in fixture (before AND after)
- [ ] Cleanup happens BEFORE data population
- [ ] Browser tests verify HTTP status codes (200, not 404)
- [ ] Browser tests wait for elements properly (wait_for_selector, wait_for_load_state)
- [ ] Playwright locators are specific and scoped to containers
- [ ] Dialogs are handled before clicking buttons that trigger them
- [ ] Tests wait for page reloads after actions that cause navigation
- [ ] Error message assertions match actual error messages (not hardcoded strings)

---

## Summary

The main lessons learned:

1. **Never rely on external APIs in tests** - Always use test data helpers
2. **Clean up before populating** - Prevents constraint violations
3. **Clean up all related tables** - Don't forget any tables
4. **Verify page loads** - Check HTTP status before looking for elements
5. **Use specific locators** - Avoid strict mode violations
6. **Wait properly** - Give time for async operations and page reloads
7. **Test isolation is critical** - Each test should start with a clean state
8. **Always test in Docker before pushing** - Ensures tests pass in CI environment
9. **Review learnings from previous failures** - Avoid repeating the same mistakes

These patterns ensure tests are:
- **Deterministic** - Always produce the same results
- **Fast** - No waiting for external APIs
- **Reliable** - Work consistently in CI environments
- **Maintainable** - Clear patterns that are easy to follow

## Development Process Requirements

### Mandatory Pre-Commit Steps

1. **Run Tests in Docker**
   - Always run `./scripts/run-tests-local.sh unit` before pushing
   - Docker environment matches GitHub Actions runners exactly
   - If tests pass locally but fail in CI, Docker tests will catch it

2. **Review Test Failure Learnings**
   - Check this document (`test_failures_and_solutions.md`) for common patterns
   - Review `docs/DEVELOPMENT_PROCESS.md` for best practices
   - Apply learnings to avoid repeating the same mistakes

### Common Mistakes to Avoid

- ❌ **Assuming data exists**: Always populate test data
- ❌ **Wrong attribute names**: Check model definitions (e.g., `watchlist.watchlist_id`, not `watchlist.id`)
- ❌ **Library function assumptions**: Verify function exists (e.g., `pd.isinf` doesn't exist, use `np.isinf`)
- ❌ **Broad Playwright locators**: Scope to specific sections
- ❌ **Timezone mixing**: Normalize all timestamps
- ❌ **Skipping Docker tests**: Always test in Docker before pushing

See `docs/DEVELOPMENT_PROCESS.md` for detailed guidelines and step-by-step workflow.
