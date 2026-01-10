# Development Process and Best Practices

This document outlines the development process and best practices to ensure code quality and prevent test failures.

## Pre-Commit Checklist

Before committing and pushing code to `main`, ensure the following:

### 1. ✅ Run Tests Locally in Docker

**Always run tests in Docker before pushing** to ensure they pass in the same environment as GitHub Actions runners.

```bash
# Run all unit tests in Docker
./scripts/run-tests-local.sh unit

# Run all tests (unit + browser) in Docker
./scripts/run-tests-local.sh all

# Run specific test file
./scripts/run-tests-local.sh tests/test_specific.py
```

**Why?** Docker mimics the GitHub Actions environment exactly. If tests pass locally but fail in CI, it's usually due to:
- Missing test data setup
- Environment differences
- Database state issues
- Missing dependencies

### 2. ✅ Incorporate Learnings from Test Failures

**Review and apply learnings** from previous test failures to avoid repeating the same mistakes.

**Common Patterns to Avoid:**

#### Database-Driven Testing
- ✅ **DO**: Populate test data using `populate_test_stock_prices()` from `tests/conftest.py`
- ❌ **DON'T**: Rely on external APIs (yfinance) for test data
- ❌ **DON'T**: Assume data exists in the database

**Example:**
```python
@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables and populate test data."""
    create_db_and_tables()
    populate_test_stock_prices("AAPL")
    populate_test_stock_prices("MSFT")
    yield
    # Cleanup...
```

#### Test Isolation
- ✅ **DO**: Clean up database before AND after each test
- ✅ **DO**: Use `autouse=True` fixtures for consistent setup
- ❌ **DON'T**: Assume clean database state between tests

#### Model Attribute Names
- ✅ **DO**: Use correct attribute names (e.g., `watchlist.watchlist_id`, not `watchlist.id`)
- ❌ **DON'T**: Assume attribute names match your expectations

**Check the model definition:**
```python
# app/models/watchlist.py
class WatchList(SQLModel, table=True):
    watchlist_id: UUID = Field(primary_key=True)  # Not 'id'!
```

#### Library Function Availability
- ✅ **DO**: Use `np.isinf()` from numpy, not `pd.isinf()` (pandas doesn't have it)
- ✅ **DO**: Check library documentation for correct function names
- ❌ **DON'T**: Assume all libraries have the same functions

**Example:**
```python
import numpy as np
import pandas as pd

# ✅ Correct
assert not (pd.isna(value) or np.isinf(value))

# ❌ Wrong
assert not (pd.isna(value) or pd.isinf(value))  # pd.isinf doesn't exist!
```

#### Playwright Locators
- ✅ **DO**: Use specific locators to avoid strict mode violations
- ✅ **DO**: Scope locators to specific sections (e.g., `#option-data th`)
- ✅ **DO**: Use `.first` property for duplicate elements
- ❌ **DON'T**: Use overly broad locators that match multiple elements

**Example:**
```python
# ✅ Correct - scoped to specific section
option_section = page.locator("#option-data")
strike_header = option_section.locator("th:has-text('Strike')").first

# ❌ Wrong - matches multiple elements
strike_header = page.locator("th:has-text('Strike')")  # Strict mode violation!
```

#### Timezone Handling
- ✅ **DO**: Normalize all timestamps to timezone-naive for consistency
- ✅ **DO**: Use `tz_localize(None)` after fetching from yfinance
- ❌ **DON'T**: Mix timezone-aware and timezone-naive timestamps

**Example:**
```python
# ✅ Correct
if df.index.tz is not None:
    df.index = df.index.tz_localize(None)

# ❌ Wrong - causes comparison errors
df.index  # May be timezone-aware, causing comparison issues
```

## Development Workflow

### Step-by-Step Process

1. **Make Code Changes**
   - Write/update code
   - Update tests if needed

2. **Run Tests Locally (Non-Docker)**
   ```bash
   pytest tests/ -v -k "not browser and not e2e"
   ```
   Quick validation before Docker testing.

3. **Run Tests in Docker**
   ```bash
   ./scripts/run-tests-local.sh unit
   ```
   **This is mandatory** - ensures tests pass in CI environment.

4. **Review Test Failures**
   - If tests fail, check `docs/learnings/test_failures_and_solutions.md`
   - Apply relevant learnings
   - Fix the issue
   - Re-run tests

5. **Commit and Push**
   ```bash
   git add -A
   git commit -m "Descriptive commit message"
   git push origin main
   ```

## Common Test Failure Patterns

### Pattern 1: Missing Test Data
**Symptom:** `No price data found for ticker: AAPL`
**Solution:** Add `populate_test_stock_prices("AAPL")` in test fixture

### Pattern 2: Wrong Attribute Name
**Symptom:** `AttributeError: 'WatchList' object has no attribute 'id'`
**Solution:** Use `watchlist.watchlist_id` instead of `watchlist.id`

### Pattern 3: Library Function Not Found
**Symptom:** `AttributeError: module 'pandas' has no attribute 'isinf'`
**Solution:** Use `np.isinf()` from numpy instead

### Pattern 4: Playwright Strict Mode Violation
**Symptom:** `strict mode violation: locator(...) resolved to 2 elements`
**Solution:** Scope locator to specific section or use `.first`

### Pattern 5: Timezone Comparison Error
**Symptom:** `Cannot compare tz-naive and tz-aware timestamps`
**Solution:** Normalize all timestamps to timezone-naive

## Reference Documents

- **Test Failures and Solutions**: `docs/learnings/test_failures_and_solutions.md`
- **Scheduler Logic**: `docs/scheduler_logic_implementation.md`
- **YFinance API Differences**: `docs/yfinance_api_differences.md`
- **Local Testing Guide**: `LOCAL_TESTING.md`

## Quick Reference: Test Commands

```bash
# Unit tests only (fast)
./scripts/run-tests-local.sh unit

# All tests (unit + browser)
./scripts/run-tests-local.sh all

# Specific test file
./scripts/run-tests-local.sh tests/test_specific.py

# Local (non-Docker) quick test
pytest tests/test_specific.py -v

# Run with specific marker
pytest tests/ -v -m "not browser and not e2e"
```

## Remember

> **Always run tests in Docker before pushing to main.**
> 
> **Always review learnings from previous test failures.**
> 
> **If tests pass locally but fail in CI, check Docker test results first.**
