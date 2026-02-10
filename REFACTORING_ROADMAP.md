# Refactoring Roadmap for Token Optimization

This document tracks the progress of refactoring large files to reduce token usage during development.

## Completed Refactors

### ✅ 1. Watchlist Routes (Completed: Feb 10, 2026)
- **Original**: `app/main.py` (2,264 lines)
- **New**: `app/routers/watchlist_routes.py` (432 lines)
- **Reduction**: main.py reduced to 1,843 lines (18.6% reduction)
- **Token Savings**: 82% when editing watchlist features
- **Files**:
  - Created: `app/routers/__init__.py`, `app/routers/watchlist_routes.py`
  - Modified: `app/main.py` (added router include, removed watchlist code)

## Pending Refactors

### Priority 1: Remaining Main.py Routes

#### 2. Stock Routes
**Target**: `app/routers/stock_routes.py` (~300 lines)
- [ ] `/stock/{ticker}` - Stock detail page (large function ~200 lines)
- [ ] `/stock/{ticker}/refresh` - Force refresh stock data
- [ ] `/results` - Multi-ticker results page
- [ ] `/v1/stock` - Get stock data API
- [ ] `/validate-tickers` - Ticker validation API

**Estimated Impact**: 16% reduction in main.py, 84% token savings on stock route edits

#### 3. Risk Reversal (RR) Routes
**Target**: `app/routers/rr_routes.py` (~300 lines)
- [ ] `/rr-list` - RR watchlist list page
- [ ] `/rr/{rr_uuid}` - RR detail page
- [ ] `/save-rr` - Save RR to watchlist API
- [ ] `/v1/rr/{rr_uuid}` - Delete RR API
- [ ] `/rr-history-log` - RR history log page

**Estimated Impact**: 16% reduction in main.py, 84% token savings on RR route edits

#### 4. Notes Routes
**Target**: `app/routers/notes_routes.py` (~150 lines)
- [ ] `/v1/stock/{ticker}/notes` - Get stock notes API
- [ ] `/v1/stock/{ticker}/notes` - Create/update note API
- [ ] `/v1/stock/{ticker}/notes` - Delete note API
- [ ] Models: `StockNoteCreate`

**Estimated Impact**: 8% reduction in main.py, 92% token savings on notes route edits

#### 5. Insights Routes
**Target**: `app/routers/insights_routes.py` (~100 lines)
- [ ] `/v1/stock/{ticker}/insights` - Get LLM insights API

**Estimated Impact**: 5% reduction in main.py, 95% token savings on insights route edits

#### 6. LLM Routes
**Target**: `app/routers/llm_routes.py` (~200 lines)
- [ ] `/v1/llm/models` - List LLM models API
- [ ] `/v1/llm/models` - Create LLM model API
- [ ] `/v1/llm/models/{model_id}/activate` - Activate model API
- [ ] `/v1/llm/models/{model_id}` - Delete model API
- [ ] `/debug/llm-models` - LLM models management page
- [ ] `/debug/llm-playground` - LLM playground page
- [ ] Models: `LLMModelCreate`

**Estimated Impact**: 11% reduction in main.py, 89% token savings on LLM route edits

#### 7. Debug Routes
**Target**: `app/routers/debug_routes.py` (~400 lines)
- [ ] `/debug/stock-price` - Stock price debug page
- [ ] `/debug/fetch-stock-price` - Fetch stock price data API
- [ ] `/debug/database-status` - Database status API
- [ ] `/debug` - Debug index page
- [ ] `/debug/scheduler-log` - Scheduler log page

**Estimated Impact**: 22% reduction in main.py, 78% token savings on debug route edits

**After all main.py refactors**: main.py reduced from 1,843 lines to ~400 lines (78% total reduction)

---

### Priority 2: Stock Service Split

#### 8. Stock Data Service
**Target**: `app/services/stock_data_service.py` (~300 lines)
**Extract from**: `app/services/stock_service.py` (1,412 lines)
- [ ] `fetch_stock_data()` - Fetch historical stock data
- [ ] `fetch_intraday_data()` - Fetch intraday data
- [ ] `separate_daily_intraday()` - Separate daily/intraday data

**Estimated Impact**: 21% reduction in stock_service.py, 79% token savings

#### 9. Stock Metrics Service
**Target**: `app/services/stock_metrics_service.py` (~400 lines)
- [ ] `calculate_sma()` - Calculate simple moving average
- [ ] `calculate_devstep()` - Calculate deviation step
- [ ] `calculate_signal()` - Calculate buy/sell signal
- [ ] `calculate_5day_price_movement()` - 5-day price movement
- [ ] `get_multiple_stock_metrics()` - Multi-ticker metrics

**Estimated Impact**: 28% reduction in stock_service.py, 72% token savings

#### 10. Options Data Service
**Target**: `app/services/options_data_service.py` (~300 lines)
- [ ] `get_options_data()` - Get options chain data
- [ ] `get_all_options_data()` - Get all expirations
- [ ] `process_options_chain()` - Process options chain
- [ ] `build_option_dict()` - Build option dictionary
- [ ] `get_leaps_expirations()` - Get LEAPS expirations

**Estimated Impact**: 21% reduction in stock_service.py, 79% token savings

#### 11. Covered Call Service
**Target**: `app/services/covered_call_service.py` (~300 lines)
- [ ] `calculate_covered_call_returns()` - Calculate CC returns (v1)
- [ ] `calculate_covered_call_returns_v2()` - Calculate CC returns (v2)

**Estimated Impact**: 21% reduction in stock_service.py, 79% token savings

**After all stock_service refactors**: stock_service.py reduced from 1,412 lines to ~100 lines (93% reduction)

---

### Priority 3: Template Component Extraction

#### 12. Stock Detail Template Components
**Target**: Multiple template files
**Extract from**: `app/templates/stock_detail.html` (1,493 lines)
- [ ] `app/templates/stock/detail_header.html` (~150 lines) - Stock info, price, metrics
- [ ] `app/templates/stock/chart_section.html` (~200 lines) - Candlestick chart
- [ ] `app/templates/stock/insights_tab.html` (~250 lines) - LLM insights tab
- [ ] `app/templates/stock/covered_calls_tab.html` (~400 lines) - Covered calls table
- [ ] `app/templates/stock/risk_reversal_tab.html` (~400 lines) - Risk reversal strategies
- [ ] `app/templates/stock/stock_detail.html` (~100 lines) - Main template with includes

**Estimated Impact**: 73% token savings when editing specific tabs

#### 13. Watchlist Detail Template Components
**Target**: Multiple template files
**Extract from**: `app/templates/watchlist_details.html` (745 lines)
- [ ] `app/templates/watchlist/header.html` (~100 lines) - Title, actions, description
- [ ] `app/templates/watchlist/stocks_table.html` (~300 lines) - DataTables config
- [ ] `app/templates/watchlist/modals.html` (~200 lines) - Delete/add modals
- [ ] `app/templates/watchlist/scripts.html` (~150 lines) - JavaScript

**Estimated Impact**: 60% token savings when editing specific sections

---

### Priority 4: Database Migrations Split

#### 14. Stock Migrations
**Target**: `app/migrations/stock_migrations.py` (~400 lines)
**Extract from**: `app/database.py` (1,300 lines)
- [ ] `_migrate_stock_price_dma_columns()`
- [ ] `_migrate_stock_attributes_table()`
- [ ] `_migrate_stock_attributes_earnings_columns()`
- [ ] `_migrate_stock_attributes_dividend_date_column()`
- [ ] `_fix_dividend_yield_values()`
- [ ] `_migrate_stock_attributes_iv_columns()`
- [ ] `_migrate_stock_price_iv_column()`
- [ ] `_migrate_stock_attributes_trading_metrics_columns()`
- [ ] `_migrate_stock_attributes_insights_columns()`
- [ ] `_create_stock_price_index()`
- [ ] `_create_stock_attributes_index()`
- [ ] `_backfill_trading_metrics()`

**Estimated Impact**: 31% reduction in database.py, 69% token savings

#### 15. Watchlist Migrations
**Target**: `app/migrations/watchlist_migrations.py` (~300 lines)
- [ ] `_migrate_watchlist_account_column()`
- [ ] `_migrate_watchlist_is_public_column()`
- [ ] `_migrate_watchlist_stocks_entry_price_column()`
- [ ] `_migrate_watchlist_description_column()`
- [ ] `_create_watchlist_stock_notes_table()`

**Estimated Impact**: 23% reduction in database.py, 77% token savings

#### 16. RR Migrations
**Target**: `app/migrations/rr_migrations.py` (~300 lines)
- [ ] `_migrate_rr_history_price_columns()`
- [ ] `_migrate_rr_history_rename_net_cost()`
- [ ] `_migrate_rr_watchlist_collar_columns()`
- [ ] `_migrate_rr_history_collar_columns()`
- [ ] `_migrate_rr_watchlist_account_column()`

**Estimated Impact**: 23% reduction in database.py, 77% token savings

#### 17. Account Migrations
**Target**: `app/migrations/account_migrations.py` (~150 lines)
- [ ] `_create_account_table()`
- [ ] `_migrate_data_ownership_to_default_account()`

**Estimated Impact**: 12% reduction in database.py, 88% token savings

#### 18. Cache Migrations
**Target**: `app/migrations/cache_migrations.py` (~100 lines)
- [ ] `_create_options_cache_tables()`
- [ ] `_create_options_cache_indexes()`
- [ ] `_create_llm_model_tables()`

**Estimated Impact**: 8% reduction in database.py, 92% token savings

**After all database refactors**: database.py reduced from 1,300 lines to ~100 lines (92% reduction)

---

## Refactoring Guidelines

### When to Refactor
- **Incrementally**: Extract routers when working on related features (e.g., adding new watchlist feature → refactor all watchlist routes)
- **Not as separate task**: Refactoring should happen alongside feature work, not as standalone effort
- **Test after each**: Run targeted tests after each router extraction to ensure functionality preserved

### How to Refactor
1. Create new router/service/template file
2. Copy relevant code with minimal changes
3. Update imports in new file
4. Remove duplicated code from original file
5. Add router include (for routers) or update imports (for services)
6. Run targeted tests to verify functionality
7. Commit with test metrics

### Testing Strategy
- Run only new/modified tests during refactor
- Run full suite before commit (mandatory)
- Document test metrics in commit message

---

## Progress Tracking

**Completed**: 1/18 refactors (5.6%)
**Lines Reduced**: 421 lines from main.py (18.6% reduction in main.py)
**Token Savings Achieved**: 82% on watchlist route edits

**Next Priority**: Extract stock routes from main.py (estimated 16% additional reduction)

---

## Notes
- Refactoring script created but not used: `scripts/refactor_main_py.py` (manual editing proved more reliable)
- All refactors follow FastAPI router pattern established by existing `app/routers/auth.py`
- Token optimization guidelines documented in `CLAUDE.md`
