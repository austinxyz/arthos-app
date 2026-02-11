# Arthos

Arthos is a FastAPI-based investment analysis application for stock research, watchlist management, options strategy tracking, and AI-assisted insights.

## Product Features

### 1. Stock Analysis

- Fetch and analyze stock data with technical metrics
- 50-day and 200-day moving averages
- Standard deviation-based signal classification
- Multi-ticker analysis through results pages and API

### 2. Stock Detail Experience

- Dedicated detail page per ticker (`/stock/{ticker}`)
- Interactive candlestick chart with SMA overlays
- Standard deviation bands and metrics panel
- Force-refresh endpoint for recalculating stock/options/insight data

### 3. Watchlists

- Create, rename, describe, and delete watchlists
- Add/remove stocks with validation and duplicate handling
- Private and public watchlist support
- Public read-only pages for shared watchlists

### 4. Stock Notes

- Add/edit/delete notes per stock within a watchlist
- View all notes for a ticker across user watchlists
- Notes are account-scoped

### 5. Options Strategy Tracking

- Risk Reversal (RR) and Collar workflows
- RR list and RR detail pages with historical tracking
- Cached options strategy calculations and refresh support

### 6. AI Insights

- LLM-generated stock insights endpoint (`/v1/stock/{ticker}/insights`)
- Cached insights with refresh support
- Admin model-management endpoints for active LLM model control

### 7. Authentication and Access Control

- Google OAuth login/logout flow
- Session-based account scoping for user data
- Admin-only protection for `/debug/*` routes via `ADMIN_EMAIL`

### 8. Scheduler and Caching

- Background scheduler refreshes stock/options/related data
- Database-backed caches to reduce repeated external API calls
- Supports `yfinance` by default and optional MarketData provider

## Core Routes

### Pages

- `/` - home
- `/results?tickers=AAPL,MSFT` - multi-ticker results
- `/stock/{ticker}` - stock detail page
- `/watchlists` and `/watchlist/{watchlist_id}` - user watchlists
- `/public-watchlists` and `/public-watchlist/{watchlist_id}` - shared watchlists
- `/rr-list` and `/rr-details/{rr_uuid}` - risk reversal pages

### Auth

- `/login`
- `/auth/google`
- `/logout`

### APIs

- `/v1/stock`
- `/validate/tickers`
- `/v1/watchlist` and related watchlist CRUD endpoints
- `/v1/stock/{ticker}/notes` and note write/delete endpoints
- `/v1/stock/{ticker}/insights`
- `/v1/llm-models` admin model management endpoints

## Screenshots

### Homepage
![Homepage](docs/screenshots/homepage.png)

### Results Page
![Results Page](docs/screenshots/results-page.png)

### Stock Detail Page
![Stock Detail Page](docs/screenshots/stock-detail.png)

### Watchlists
![Portfolios List](docs/screenshots/portfolios-list.png)
![Create WatchList](docs/screenshots/create-portfolio.png)
![WatchList Details](docs/screenshots/portfolio-details.png)

## Setup, Testing, and Deployment Docs

- Environment setup: `docs/development/ENVIRONMENT_SETUP.md`
- Local testing: `docs/development/LOCAL_TESTING.md`
- Development docs index: `docs/development/`
- Deployment (Railway): `docs/deployment/DEPLOYMENT.md`
- Repository structure: `docs/REPO_STRUCTURE.md`

## Tech Stack

- Backend: FastAPI, SQLModel, Starlette sessions
- Data providers: yfinance (default), MarketData (optional)
- Frontend: Jinja2 templates, Bootstrap, Plotly
- Database: SQLite (local) or PostgreSQL
- Testing: pytest (+ browser/e2e suites in repo)

## License

This project is part of the Arthos investment analysis platform.
