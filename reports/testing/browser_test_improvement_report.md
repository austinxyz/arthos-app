# Browser Test Improvement Report (Before vs After)

## Scope
- Playwright/browser/E2E test stabilization and cleanup
- Deterministic test data setup (reduced provider dependency)
- Removal of low-signal/redundant tests
- Added missing public watchlist browser coverage

## Baseline (Before)
- Browser/E2E subset (`-k "browser or e2e"`):
  - `48 passed, 3 skipped, 316 deselected in 181.54s`
- Full suite + coverage:
  - `364 passed, 3 skipped, 28 warnings in 217.56s`
  - `TOTAL 10731 statements, 4182 missed, 61% coverage`

## After Improvements
- Browser/E2E subset (`-k "browser or e2e"`):
  - `46 passed, 3 skipped, 316 deselected in 162.21s`
- Full suite + coverage:
  - `362 passed, 3 skipped, 28 warnings in 204.07s`
  - `TOTAL 10676 statements, 4096 missed, 62% coverage`

## Quantified Delta
- Browser/E2E runtime: `181.54s -> 162.21s` (`-19.33s`, ~`10.6%` faster)
- Full-suite runtime: `217.56s -> 204.07s` (`-13.49s`, ~`6.2%` faster)
- Overall coverage: `61% -> 62%` (`+1` point)
- Missed lines: `4182 -> 4096` (`-86` missed lines)
- Browser/E2E test count: net `-2` executed tests (removed low-value tests while adding focused coverage)

## High-Value Gaps Filled
- Added browser coverage for public watchlists:
  - `tests/test_public_watchlists_browser.py`
  - Validates only public entries appear in listing.
  - Validates public watchlist detail is read-only for anonymous users.
- Fixed structural contract validation for watchlist error rows:
  - `tests/test_watchlist_table_structure.py`
  - Validates effective column count (including `colspan`) instead of raw `<td>` count.
- Fixed E2E covered-calls assertions to match real UI/data contract:
  - `tests/test_e2e_user_flows.py`
  - Corrected column mapping for strike/premium/returns parsing.
  - Replaced brittle “all strikes within 10%” rule with ATM/OTM rule aligned to app behavior.
- Fixed UI table semantics in template:
  - `app/templates/watchlist_details.html`
  - Error row now uses correct `colspan` and owner-only Actions cell.

## Redundant / Low-Signal Tests Removed
- Removed provider-dependent watchlist browser tests that add flakiness and overlap service-level validation:
  - `test_add_stocks_sdsk_invalid_ticker`
  - `test_add_stocks_mixed_valid_sdsk`
- Removed assertion-light stock detail browser tests that provided weak signal:
  - `test_closest_strike_highlighted_in_risk_reversal_table`
  - `test_equidistant_strikes_both_highlighted`

## Remaining Noted Gap
- `scripts/test/run-tests-local.sh all` still fails at browser phase in this environment due:
  - Docker Compose flag incompatibility (`unknown flag: --network`)
  - Browser/full-suite commands run directly via `docker-compose -f docker-compose.test.yml ...` succeed.
