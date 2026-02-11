# Arthos

Arthos is a FastAPI app for stock analysis and watchlist workflows.  
It combines market data, technical metrics, options strategy views, and account-scoped watchlists.

## What It Does

- Analyze stocks with SMA, standard deviation signal, and historical price context
- Show stock detail pages with charting, options strategy snapshots, and notes
- Manage private/public watchlists and stocks in each watchlist
- Track Risk Reversal (and Collar) entries and history
- Generate cached LLM-based stock insights
- Support Google OAuth login for account-based data

## Tech Stack

- Python + FastAPI
- SQLModel + SQLite (default) or PostgreSQL
- Jinja2 templates + Bootstrap + Plotly
- Pytest (+ Playwright plugin for browser tests)

## Quick Start

```bash
git clone https://github.com/kgajjala/arthos-app.git
cd arthos-app

python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

pip install -r requirements.txt
python run.py
```

App URLs:

- Home: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Configuration

Default local DB is SQLite (`arthos.db`).  
Set `DATABASE_URL` for PostgreSQL in production.

Common environment variables:

- `DATABASE_URL` - DB connection string (optional locally, required in most hosted setups)
- `SECRET_KEY` - session signing key (set this in all non-local environments)
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` - Google OAuth login
- `ADMIN_EMAIL` - required for `/debug/*` admin access
- `OPENROUTER_API_KEY` - enables LLM insights
- `STOCK_DATA_PROVIDER` - `yfinance` (default) or `marketdata`
- `MARKETDATA_API_KEY` - required when using `marketdata`
- `LOG_LEVEL` - logging verbosity (`INFO` default)
- `SCHEDULER_AUTO_START` - scheduler enable flag (`true` default)

## Key Routes

Pages:

- `/` - home
- `/results?tickers=AAPL,MSFT` - batch results
- `/stock/{ticker}` - stock detail page
- `/watchlists` / `/watchlist/{watchlist_id}` - watchlist pages
- `/public-watchlists` / `/public-watchlist/{watchlist_id}` - public watchlist pages
- `/rr-list` / `/rr-details/{rr_uuid}` - RR pages

Auth:

- `/login` - Google login
- `/auth/google` - OAuth callback
- `/logout` - sign out

APIs:

- `/v1/stock?q=AAPL` - stock metrics
- `/validate/tickers?tickers=AAPL,MSFT` - ticker validation
- `/v1/watchlist` and `/v1/watchlist/{watchlist_id}` - watchlist CRUD
- `/v1/watchlist/{watchlist_id}/stocks` - add stocks
- `/v1/watchlist/{watchlist_id}/stocks/{ticker}` - remove stock
- `/v1/watchlist/{watchlist_id}/visibility` - public/private toggle
- `/v1/stock/{ticker}/notes` and note update/delete endpoints
- `/v1/stock/{ticker}/insights` - LLM insights

## Testing

Run all tests:

```bash
pytest
```

Run focused suites:

```bash
pytest tests/test_auth_flows.py -v
pytest tests/test_watchlist_api.py -v
pytest tests/test_stock_detail_api.py -v
```

## Project Layout

```text
app/
  main.py                 # FastAPI app + middleware + router includes
  database.py             # DB engine, table setup, migrations
  routers/                # API/page route modules
  services/               # Business logic
  models/                 # SQLModel models
  templates/              # Jinja templates
tests/                    # Unit, API, and browser tests
docs/                     # Specs, deployment, and internal docs
run.py                    # Local app runner
```

## Deployment

Primary target is Railway with PostgreSQL.

- Start here: `docs/deployment/DEPLOYMENT.md`
- GitHub Actions + Railway secrets are documented in `docs/deployment/`

## Notes for Contributors

- Watchlist, notes, RR, and insights features are account-scoped via session auth.
- `/debug/*` routes are blocked unless logged in as `ADMIN_EMAIL`.
- The scheduler starts on app boot by default and updates market data/cache.
