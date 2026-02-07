# Test Selection Strategy

## Overview

This document defines how to intelligently select which tests to run based on what changed, balancing speed with confidence.

## Test Categories & Markers

### Current Markers
- `@pytest.mark.browser` - Playwright browser tests (slowest, ~1.5 min total)
- `@pytest.mark.e2e` - End-to-end integration tests

### Proposed Additional Markers
```python
# Layer markers (what part of app is tested)
@pytest.mark.unit          # Pure logic, no I/O (fast: <1s each)
@pytest.mark.integration   # Database, external services (medium: 1-5s each)
@pytest.mark.api           # FastAPI endpoint tests (medium: 1-3s each)

# Feature markers (what functionality is tested)
@pytest.mark.watchlist     # Watchlist-related tests
@pytest.mark.stock_data    # Stock data fetching/processing
@pytest.mark.options       # Options analysis (covered calls, RR)
@pytest.mark.auth          # Authentication/authorization
@pytest.mark.scheduler     # Background job scheduler
@pytest.mark.llm           # LLM integration tests
```

## Test Selection Rules

### 1. File-Based Selection (Smart Defaults)

**Backend changes** → Run affected tests + smoke tests
```bash
# Changed: app/services/stock_service.py
# Run: All tests matching *stock*, plus smoke tests
pytest tests/test_stock_service.py tests/test_stock_detail_api.py -m "not browser"
pytest tests/test_e2e_user_flows.py::test_home_page_loads_and_navigation  # smoke
```

**UI/Template changes** → Run browser tests + affected API tests
```bash
# Changed: app/templates/stock_detail.html
# Run: All browser tests + stock detail API tests
pytest -m browser
pytest tests/test_stock_detail_api.py
```

**Model changes** → Run ALL tests (data model affects everything)
```bash
# Changed: app/models/watchlist.py
# Run: Full suite (models are foundational)
./scripts/test/run-tests-local.sh all
```

**Test-only changes** → Run modified tests only
```bash
# Changed: tests/test_watchlist_service.py
# Run: Just that test file
pytest tests/test_watchlist_service.py
```

### 2. Change-Based Test Selection Script

Create `scripts/test/smart-test-runner.sh`:

```bash
#!/bin/bash
# Intelligently select tests based on git changes

# Get changed files since last commit (or main branch)
CHANGED_FILES=$(git diff --name-only HEAD~1 2>/dev/null || git diff --name-only origin/main)

if [ -z "$CHANGED_FILES" ]; then
    echo "No changes detected, running full suite"
    ./scripts/test/run-tests-local.sh all
    exit $?
fi

echo "Changed files:"
echo "$CHANGED_FILES"
echo ""

# Determine test strategy
RUN_ALL=false
RUN_BROWSER=false
TEST_FILES=""
MARKERS=""

# Check for changes that require full suite
if echo "$CHANGED_FILES" | grep -q "app/models/\|app/database.py\|requirements.txt\|docker-compose"; then
    echo "🔴 Critical files changed - running FULL test suite"
    RUN_ALL=true
fi

# Check for UI changes
if echo "$CHANGED_FILES" | grep -q "app/templates/\|app/static/"; then
    echo "🎨 UI changes detected - including browser tests"
    RUN_BROWSER=true
fi

# Check for specific service changes
if echo "$CHANGED_FILES" | grep -q "app/services/watchlist"; then
    TEST_FILES="$TEST_FILES tests/test_watchlist*.py"
fi

if echo "$CHANGED_FILES" | grep -q "app/services/stock_service\|app/services/stock_price"; then
    TEST_FILES="$TEST_FILES tests/test_stock*.py"
fi

if echo "$CHANGED_FILES" | grep -q "app/services/options\|app/services/rr_watchlist"; then
    TEST_FILES="$TEST_FILES tests/test_options*.py tests/test_rr*.py"
fi

# Build pytest command
if [ "$RUN_ALL" = true ]; then
    ./scripts/test/run-tests-local.sh all
else
    CMD="pytest"

    if [ -n "$TEST_FILES" ]; then
        CMD="$CMD $TEST_FILES"
    else
        # No specific matches, run unit + integration (skip browser for speed)
        CMD="$CMD tests/ -m 'not browser'"
    fi

    if [ "$RUN_BROWSER" = true ]; then
        echo "🌐 Running browser tests..."
        docker-compose -f docker-compose.test.yml run --rm test-runner pytest -m browser
    fi

    echo "🚀 Running: $CMD"
    docker-compose -f docker-compose.test.yml run --rm test-runner $CMD
    EXIT_CODE=$?

    # Always run smoke tests
    echo "💨 Running smoke tests..."
    docker-compose -f docker-compose.test.yml run --rm test-runner \
        pytest tests/test_e2e_user_flows.py::TestE2EUserFlows::test_home_page_loads_and_navigation

    exit $EXIT_CODE
fi
```

### 3. Pre-Commit Hook (Local Fast Feedback)

Run subset of tests before allowing commit:

```bash
# .git/hooks/pre-commit (optional, can be skipped with --no-verify)
#!/bin/bash

echo "🔍 Running fast pre-commit checks..."

# Only run unit tests (no browser, no integration)
docker-compose -f docker-compose.test.yml run --rm test-runner \
    pytest tests/ -m "unit" --maxfail=3 -x

if [ $? -ne 0 ]; then
    echo "❌ Unit tests failed. Fix errors or use 'git commit --no-verify' to skip"
    exit 1
fi

echo "✅ Pre-commit checks passed"
```

### 4. CI/CD Pipeline Strategy

```yaml
# .github/workflows/tests.yml (example)

on: [push, pull_request]

jobs:
  quick-tests:
    # Run on every push for fast feedback
    runs-on: ubuntu-latest
    steps:
      - name: Run unit tests
        run: pytest tests/ -m "unit" --maxfail=5
      - name: Run integration tests
        run: pytest tests/ -m "integration" --maxfail=5

  browser-tests:
    # Run browser tests only on main branch or PRs
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' || github.event_name == 'pull_request'
    steps:
      - name: Run browser tests
        run: pytest tests/ -m "browser"

  full-regression:
    # Run full suite nightly or on release branches
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule' || startsWith(github.ref, 'refs/tags/')
    steps:
      - name: Run all tests
        run: pytest tests/ --random-order
```

## Recommended Workflow

### Local Development (Fast Iteration)

1. **During active development:**
   ```bash
   # Run only tests related to what you're working on
   pytest tests/test_watchlist_service.py -v
   ```

2. **Before committing:**
   ```bash
   # Run smart test runner (subset based on changes)
   ./scripts/test/smart-test-runner.sh
   ```

3. **Before pushing:**
   ```bash
   # Run full suite (mandatory)
   ./scripts/test/run-tests-local.sh all
   ```

### CI/CD (Automated)

1. **On every push to feature branch:**
   - Unit tests (~40s)
   - Integration tests (~1 min)
   - Smoke tests (~10s)
   - **Total: ~2 min** (vs 3.5 min full suite)

2. **On PR to main:**
   - Full suite including browser tests (~3.5 min)

3. **Nightly (scheduled):**
   - Full suite with `--random-order`
   - Run against production-like data
   - Performance regression tests

4. **On release tag:**
   - Full suite (3 times to check for flakiness)
   - Security scans
   - Performance benchmarks

## Benefits of This Strategy

### Speed Gains
- **Local iteration**: 40s (unit only) vs 3.5 min (full)
- **Smart pre-commit**: ~2 min (affected tests) vs 3.5 min
- **Still safe**: Full suite runs before push + on CI

### Confidence Maintained
- Full suite runs before merging to main
- Nightly full regressions catch integration issues
- Smart selection includes "blast radius" tests

### Developer Experience
- Faster feedback loop during development
- Can iterate 5-10x per hour instead of 2-3x
- Pre-commit catches obvious errors without waiting

## Migration Plan

### Phase 1: Add Markers (Week 1)
```bash
# Add markers to existing tests
# Start with obvious categories: unit, integration, api, browser
```

### Phase 2: Create Smart Runner (Week 1)
```bash
# Implement scripts/test/smart-test-runner.sh
# Test with various change scenarios
```

### Phase 3: Update CLAUDE.md (Week 1)
```bash
# Document new workflow
# Keep full suite as mandatory before push
```

### Phase 4: CI/CD Integration (Week 2)
```bash
# Set up GitHub Actions or equivalent
# Configure nightly runs
```

### Phase 5: Monitor & Tune (Ongoing)
```bash
# Track: Are we catching bugs with subset?
# Measure: How much time saved?
# Adjust: Which tests should always run?
```

## Implementation Checklist

- [ ] Add pytest markers to all existing tests
- [ ] Create `scripts/test/smart-test-runner.sh`
- [ ] Create pytest.ini configuration
- [ ] Update CLAUDE.md with new workflow
- [ ] Set up GitHub Actions (optional)
- [ ] Configure nightly test runs
- [ ] Create dashboard for test metrics
- [ ] Document exceptions (when to run full suite)

## Test Selection Decision Tree

```
Changed files?
├─ Models/Database/Requirements → RUN ALL TESTS (critical changes)
├─ Templates/Static files → Browser tests + Related API tests
├─ Services layer → Related service tests + Integration tests
├─ API endpoints → API tests + Smoke tests
├─ Tests only → Modified tests only
└─ Config/Docs → Smoke tests only
```

## Measuring Success

Track these metrics weekly:
- **Average local test time**: Target <2 min for pre-commit
- **CI build time**: Target <5 min for PR checks
- **Bug escape rate**: Should remain <5% (full suite catches most)
- **Flaky test rate**: Should be <2% (stable tests)

## Future Enhancements

1. **Test Impact Analysis**: Use `pytest-picked` to run only tests affected by changed code
2. **Parallel Execution**: Use `pytest-xdist` for multi-core execution
3. **Test Sharding**: Distribute browser tests across multiple runners
4. **Coverage-Based Selection**: Run tests that cover changed lines
