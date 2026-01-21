---
description: Run Docker tests before pushing to main
---

# Pre-Push Testing Workflow

**MANDATORY**: All changes must pass Docker tests before pushing to main.

## Steps

1. Ensure all your changes are committed locally

2. Run the Docker test suite:
// turbo
```bash
docker-compose -f docker-compose.test.yml up test-runner --abort-on-container-exit
```

3. Wait for tests to complete. All tests must pass (exit code 0).

4. If tests fail:
   - Review the failure output
   - Fix the issues locally
   - Re-run the tests until they pass

5. Only after tests pass, push to main:
```bash
git push origin main
```

## Why This Is Required

On January 20, 2026, we spent most of a day debugging pandas Series ambiguity errors that would have been caught if we had:
- Run tests in Docker before pushing
- Had edge case tests for pandas operations

See: `docs/learnings/pandas_and_yfinance_pitfalls.md`

## Quick Reference

```bash
# Run all tests in Docker
docker-compose -f docker-compose.test.yml up test-runner --abort-on-container-exit

# Run specific test file (example)
docker-compose -f docker-compose.test.yml run test-runner pytest tests/test_stock_price_service.py -v

# Cleanup after tests
docker-compose -f docker-compose.test.yml down -v
```
