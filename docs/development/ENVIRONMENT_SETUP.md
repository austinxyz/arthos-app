# Environment Setup

This guide covers local setup for running Arthos in development.

## Prerequisites

- Python 3.9+
- `pip`
- `git`

## 1. Clone the Repository

```bash
git clone https://github.com/kgajjala/arthos-app.git
cd arthos-app
```

## 2. Create and Activate a Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (PowerShell):

```powershell
.venv\Scripts\Activate.ps1
```

## 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Configure Environment Variables

Create a `.env` file in project root (or export in shell).

Recommended variables:

- `DATABASE_URL` (optional locally; defaults to `sqlite:///arthos.db`)
- `SECRET_KEY` (required for secure session signing)
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` (required for OAuth login)
- `ADMIN_EMAIL` (required for `/debug/*` access)
- `OPENROUTER_API_KEY` (required for stock insights)
- `STOCK_DATA_PROVIDER` (`yfinance` default, `marketdata` optional)
- `MARKETDATA_API_KEY` (required when provider is `marketdata`)
- `LOG_LEVEL` (default `INFO`)
- `SCHEDULER_AUTO_START` (`true` by default)

## 5. Start the Application

```bash
python run.py
```

Or:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 6. Open the App

- App: `http://localhost:8000`
- Swagger docs: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Database Notes

- Local default: SQLite (`arthos.db`), auto-created on first run.
- Production target: PostgreSQL via `DATABASE_URL`.
- The app runs table creation/migrations at startup (`create_db_and_tables()`).

## Quick Troubleshooting

- `ModuleNotFoundError`: activate virtual environment and reinstall dependencies.
- Port `8000` in use: run uvicorn with another port.
- OAuth not working: check `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and callback URL.
- Debug pages blocked: verify you are logged in as `ADMIN_EMAIL`.
