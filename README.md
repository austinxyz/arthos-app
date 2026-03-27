# Arthos

Arthos is an open-source investment analysis web app. It fetches stock market data, computes technical signals (SMA, standard deviation bands), tracks watchlists, analyzes options strategies (Risk Reversals, Covered Calls), and generates AI-powered stock insights.

**Live demo:** [my.arthos.app](https://my.arthos.app)

---

## Screenshots

### Homepage — Most Oversold / Overbought from your watchlists
![Homepage](docs/screenshots/homepage.png)

### Stock Metrics Results
![Results Page](docs/screenshots/results-page.png)

### Stock Detail — Chart, Signals, Dividends & Earnings
![Stock Detail](docs/screenshots/stock-detail.png)

### Public WatchLists
![Public WatchLists](docs/screenshots/public-watchlists.png)

---

## What It Does

| Feature | Description |
|---|---|
| **Stock analysis** | Fetch price history, compute 50/200-day SMAs and standard deviation signals |
| **Results page** | Compare multiple tickers side-by-side with signal badges and trading range |
| **Stock detail** | Interactive candlestick chart, options chain, covered calls, AI insights, notes |
| **Watchlists** | Create private/public watchlists, add stocks with entry prices, share publicly |
| **Options tracking** | Risk Reversal (RR) entry tracking with historical price snapshots |
| **AI insights** | LLM-generated analysis per ticker via OpenRouter (model configurable) |
| **Auth** | Google OAuth login; account-scoped data; admin-only debug routes |
| **Scheduler** | Background job refreshes prices/options/signals every 60 minutes |

---

## Tech Stack

- **Backend:** Python 3.9+, FastAPI, SQLModel, Starlette sessions
- **Frontend:** Jinja2 templates, Bootstrap 5, Plotly
- **Database:** SQLite (local dev) or PostgreSQL (production)
- **Data:** yfinance (default), MarketData API (optional)
- **Testing:** pytest, Playwright (browser/e2e)
- **Deployment:** Railway (primary), any platform supporting Python + PostgreSQL

---

## Fork & Deploy Your Own Instance

### 1. Fork the repo

```bash
git clone https://github.com/kgajjala/arthos-app.git
cd arthos-app
```

### 2. Set up locally

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```env
# Required for sessions (generate any random secret)
SECRET_KEY=your-random-secret-key

# Optional: Google OAuth (skip if you don't need login)
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# Optional: AI insights
OPENROUTER_API_KEY=your-openrouter-key

# Optional: admin access to /debug/* routes
ADMIN_EMAIL=you@example.com

# Optional: override default SQLite DB
# DATABASE_URL=postgresql://user:pass@localhost:5432/arthos
```

Run the app:

```bash
python run.py
```

Open [http://localhost:8000](http://localhost:8000). The app creates `arthos.db` (SQLite) automatically on first run.

---

### 3. Google OAuth setup (optional — needed for login)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → APIs & Services → Credentials
2. Create an OAuth 2.0 Client ID (Web application)
3. Add authorized redirect URI: `http://localhost:8000/auth/google` (and your production URL)
4. Copy the Client ID and Secret into your `.env`

Without Google OAuth, the app runs fine but login/watchlists/notes are unavailable.

---

### 4. Deploy to Railway

Railway is the easiest hosted option — it provides PostgreSQL and handles Python deploys automatically.

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login

# Create project and link PostgreSQL
railway init
railway add postgresql

# Deploy
railway up
```

Set these environment variables in the Railway dashboard:

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | ✅ | Auto-set by Railway PostgreSQL plugin |
| `SECRET_KEY` | ✅ | Random string for session signing |
| `GOOGLE_CLIENT_ID` | Optional | Google OAuth |
| `GOOGLE_CLIENT_SECRET` | Optional | Google OAuth |
| `OPENROUTER_API_KEY` | Optional | Enables AI insights |
| `ADMIN_EMAIL` | Optional | Grants access to `/debug/*` admin routes |
| `STOCK_DATA_PROVIDER` | Optional | `yfinance` (default) or `marketdata` |
| `MARKETDATA_API_KEY` | Optional | Required if using `marketdata` provider |

After deploying, add your Railway production URL to the Google OAuth authorized redirect URIs.

---

### 5. Deploy to any other platform (Heroku, Fly.io, Render, etc.)

The app is a standard ASGI app. Entry point: `app.main:app`.

```bash
# Example with uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Requirements:
- Python 3.9+
- PostgreSQL (recommended for production; SQLite works for single-user local setups)
- All env vars listed above

---

## Project Structure

```
arthos-app/
├── app/
│   ├── main.py               # FastAPI app, middleware, router includes
│   ├── database.py           # DB engine, table creation, migrations
│   ├── routers/              # Route handlers (one file per feature domain)
│   │   ├── watchlist_routes.py
│   │   ├── rr_routes.py
│   │   ├── stock_routes.py
│   │   ├── notes_routes.py
│   │   ├── insights_routes.py
│   │   └── debug_routes.py
│   ├── services/             # Business logic
│   │   ├── stock_service.py         # SMA, signal, devstep calculations
│   │   ├── stock_data_service.py    # Price fetching from providers
│   │   ├── options_data_service.py  # Options chain + LEAPS
│   │   ├── covered_call_service.py  # Covered call calculations
│   │   ├── risk_reversal_service.py # Risk reversal calculations
│   │   ├── watchlist_service.py     # Watchlist CRUD + top movers
│   │   ├── insights_service.py      # LLM insights
│   │   └── scheduler_service.py     # Background refresh job
│   ├── models/               # SQLModel table definitions
│   ├── providers/            # Stock data provider abstraction (yfinance, MarketData)
│   ├── templates/            # Jinja2 HTML templates
│   └── utils/                # Shared helpers
├── tests/                    # Unit, API, and Playwright browser tests
├── docs/                     # Developer docs and screenshots
├── scripts/                  # Test runners and deployment helpers
├── run.py                    # Local dev runner
├── railway_deploy.py         # Production migration script (runs before app starts)
└── requirements.txt
```

---

## Key Routes

**Pages**

| Route | Description |
|---|---|
| `/` | Homepage with Most Oversold/Overbought tables |
| `/results?tickers=AAPL,MSFT` | Multi-ticker comparison |
| `/stock/{ticker}` | Stock detail: chart, signals, options, insights, notes |
| `/watchlists` | Your private/public watchlists (login required) |
| `/public-watchlists` | Browse all public watchlists |
| `/rr-list` | Risk Reversal tracking list (login required) |
| `/rr-add` | Add a new Risk Reversal entry |

**APIs**

| Endpoint | Description |
|---|---|
| `GET /v1/stock?q=AAPL` | Stock metrics (price, SMA, signal, devstep) |
| `GET /v1/stock/{ticker}/insights` | AI insights for a ticker |
| `GET/POST /v1/watchlist` | List or create watchlists |
| `POST /v1/watchlist/{id}/stocks` | Add a stock to a watchlist |
| `GET /api/rr/expirations?ticker=AAPL` | LEAPS expiration dates |
| `GET /api/rr/options-chain?ticker=AAPL&expiration=2027-01-15` | Filtered options chain |

---

## Running Tests

Tests require Docker (uses PostgreSQL for production parity):

```bash
# Run full test suite
./scripts/test/run-tests-local.sh all

# Run only unit tests (faster)
./scripts/test/run-tests-local.sh unit

# Run a specific test file
./scripts/test/run-tests-local.sh tests/test_watchlist_service.py
```

See `docs/development/LOCAL_TESTING.md` for full testing docs.

---

## License

MIT
