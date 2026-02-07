# Test Metrics Report Template

This template should be included in every code change commit message or PR description.

## Test Metrics Report

### Test Coverage Changes
- ✨ **New tests added**: `X`
- 📝 **Existing tests updated**: `Y`
- 🗑️ **Tests removed**: `Z`
- 📊 **Net change**: `+X-Z` tests

### Test Execution
- 🎯 **Tests selected for execution**: `N` tests (subset/full)
- ⏱️ **Time taken**: `Xm Ys` (or `Xs`)
- ⚡ **Test throughput**: `X.Y tests/sec`

### Test Results
- ✅ **Passed**: `N`
- ❌ **Failed**: `0` (or details if any)
- ⏭️ **Skipped**: `N`

### Performance
- 💰 **Time saved vs full suite**: `Xs (Y%)`

### Test Selection Rationale
Brief explanation of why these tests were selected:
- [ ] Full suite (critical files changed)
- [ ] Smart selection (related tests only)
- [ ] Browser tests included (UI changes)
- [ ] Specific test file (targeted change)

---

## Example Report

### Test Coverage Changes
- ✨ **New tests added**: `3`
- 📝 **Existing tests updated**: `5`
- 🗑️ **Tests removed**: `1`
- 📊 **Net change**: `+2` tests

### Test Execution
- 🎯 **Tests selected for execution**: `87` tests (subset)
- ⏱️ **Time taken**: `1m 23s`
- ⚡ **Test throughput**: `1.05 tests/sec`

### Test Results
- ✅ **Passed**: `87`
- ❌ **Failed**: `0`
- ⏭️ **Skipped**: `3`

### Performance
- 💰 **Time saved vs full suite**: `112s (57%)`

### Test Selection Rationale
- [x] Smart selection (watchlist service changed)
- [x] Related integration tests included
- [ ] Browser tests not needed (no UI changes)
