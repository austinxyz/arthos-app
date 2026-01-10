# Test Order Independence

## Problem

Tests were failing in GitHub Actions but passing locally in Docker due to test execution order dependencies. Multiple tests were using the same ticker "SDSK", which could cause conflicts when tests run in different orders.

## Solution

### 1. Use Unique Test Data

**Before (Order-Dependent)**:
```python
# Multiple tests using same ticker "SDSK"
def test_add_stocks_sdsk_invalid_ticker(self, ...):
    page.fill("#tickersInput", "SDSK")  # ← Same ticker

def test_add_stocks_mixed_valid_sdsk(self, ...):
    page.fill("#tickersInput", "AAPL,SDSK")  # ← Same ticker

def test_delete_button_visible_for_error_rows(self, ...):
    invalid_stock = WatchListStock(ticker="SDSK")  # ← Same ticker
```

**After (Order-Independent)**:
```python
# Each test uses unique ticker
def test_add_stocks_sdsk_invalid_ticker(self, ...):
    invalid_ticker = "INVALIDT1"  # ← Unique
    page.fill("#tickersInput", invalid_ticker)

def test_add_stocks_mixed_valid_sdsk(self, ...):
    invalid_ticker = "INVALIDT2"  # ← Unique
    page.fill("#tickersInput", f"AAPL,{invalid_ticker}")

def test_delete_button_visible_for_error_rows(self, ...):
    invalid_ticker = "INVALIDT3"  # ← Unique
    invalid_stock = WatchListStock(ticker=invalid_ticker)
```

### 2. Add pytest-random-order Plugin

Added `pytest-random-order==1.1.0` to catch order dependencies:

```bash
# Install
pip install pytest-random-order

# Run tests in random order
pytest --random-order

# Or enable by default in pytest.ini
random_order_enabled = true
```

## Best Practices

### ✅ DO:
- Use unique test data for each test (unique tickers, unique watchlist names, etc.)
- Use descriptive names that indicate the test purpose (e.g., `INVALIDT1`, `INVALIDT2`)
- Run tests with `--random-order` periodically to catch order dependencies
- Ensure each test cleans up after itself (via fixtures)

### ❌ DON'T:
- Reuse the same test data across multiple tests
- Assume tests will run in a specific order
- Rely on state from previous tests
- Use hardcoded values that might conflict

## Testing for Order Dependencies

```bash
# Run tests in random order multiple times
for i in {1..10}; do
    pytest --random-order tests/test_watchlist_browser.py
done

# If all runs pass, tests are likely order-independent
```

## Key Learnings

1. **Test Isolation is Critical**: Each test should be completely independent
2. **Unique Test Data**: Use unique identifiers for each test to avoid conflicts
3. **Random Order Testing**: Use `pytest-random-order` to catch order dependencies
4. **GitHub Actions vs Local**: Different execution orders can expose hidden dependencies

## References

- `pytest-random-order` documentation: https://pypi.org/project/pytest-random-order/
- Test isolation best practices: `docs/learnings/test_failures_and_solutions.md`
