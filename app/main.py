"""FastAPI application for Arthos investment analysis."""
from contextlib import asynccontextmanager
from typing import Optional
from fastapi import FastAPI, Request, HTTPException, Query, Path as FPath
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates
from starlette.responses import RedirectResponse
from fastapi.responses import HTMLResponse
from pathlib import Path
from uuid import UUID
from app.services.stock_price_service import get_stock_metrics_from_db
from app.database import create_db_and_tables
from pydantic import BaseModel
import logging
import os
import json
import datetime


class JSONFormatter(logging.Formatter):
    """JSON formatter for Railway production logging."""

    def format(self, record):
        log_entry = {
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


# Configure logging for both local and production (Railway)
# Set LOG_LEVEL environment variable to 'DEBUG' for detailed logs, defaults to 'INFO'
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()

# Check if running in Railway (RAILWAY_ENVIRONMENT or RAILWAY_SERVICE_NAME is set)
is_railway = os.getenv('RAILWAY_ENVIRONMENT') or os.getenv('RAILWAY_SERVICE_NAME')

if is_railway:
    # Production (Railway): Use JSON format for proper log parsing
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        handlers=[handler],
        force=True  # Override any existing configuration
    )
else:
    # Local development: Use human-readable format
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format='%(levelname)s: %(name)s - %(message)s'
    )

logger = logging.getLogger(__name__)
logger.info(f"Logging configured at {log_level} level (JSON={is_railway})")

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed, skip loading .env file
    pass



@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for FastAPI app startup and shutdown."""
    # Startup
    create_db_and_tables()
    
    # Start the scheduler for fetching stock data every 60 minutes
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Attempting to start scheduler...")
        
        from app.services.scheduler_service import start_scheduler
        start_scheduler()
        
        logger.info("✓ Scheduler initialization completed successfully")
        print("✓ Scheduler started for fetching stock data every 60 minutes")
    except Exception as e:
        # Don't crash startup if scheduler fails
        import logging
        import traceback
        logger = logging.getLogger(__name__)
        logger.error(f"✗ Failed to start scheduler: {e}")
        logger.error(f"Stack trace:\n{traceback.format_exc()}")
        print(f"⚠ Warning: Could not start scheduler: {e}")
        print("Application will continue without scheduler")
    
    yield
    
    # Shutdown
    try:
        import logging
        logger = logging.getLogger(__name__)
        logger.info("Attempting to stop scheduler...")
        
        from app.services.scheduler_service import stop_scheduler
        stop_scheduler()
        
        logger.info("✓ Scheduler stopped successfully")
        print("✓ Scheduler stopped")
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.warning(f"Could not stop scheduler: {e}")
        print(f"⚠ Warning: Could not stop scheduler: {e}")


# Initialize FastAPI app with lifespan handler
app = FastAPI(
    title="Arthos",
    description="Investment Analysis Platform",
    lifespan=lifespan
)

# Admin Access Control Middleware
# Protects /debug/* endpoints - only allows access to ADMIN_EMAIL
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")


class AdminAccessMiddleware(BaseHTTPMiddleware):
    """Middleware to protect admin-only routes like /debug/*."""

    async def dispatch(self, request: Request, call_next):
        # Check if this is a protected route
        if request.url.path.startswith("/debug"):
            # Get user from session
            user = request.session.get("user") if hasattr(request, "session") else None

            # Check if user is logged in and has admin email
            if not user:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Admin access required. Please log in."}
                )

            user_email = user.get("email")
            if not ADMIN_EMAIL:
                # If ADMIN_EMAIL not configured, deny all access to debug
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Admin access not configured."}
                )

            if user_email != ADMIN_EMAIL:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "Admin access required. You are not authorized."}
                )

        return await call_next(request)


# Add Admin Access Middleware (must be added before SessionMiddleware)
app.add_middleware(AdminAccessMiddleware)

# Add Session Middleware
from starlette.middleware.sessions import SessionMiddleware
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400*30, same_site='lax', https_only=False)

# Include Routers
from app.routers import auth
from app.routers import watchlist_routes
from app.routers import notes_routes
from app.routers import insights_routes
from app.routers import stock_routes
from app.routers import rr_routes
from app.routers import debug_routes
from app.routers import option_routes

app.include_router(auth.router)
app.include_router(watchlist_routes.router)
app.include_router(notes_routes.router)
app.include_router(insights_routes.router)
app.include_router(stock_routes.router)
app.include_router(rr_routes.router)
app.include_router(debug_routes.router)
app.include_router(option_routes.router)

# Set up templates directory
templates_dir = Path(__file__).parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Mount static files (for CSS, JS, images, etc.)
static_dir = Path(__file__).parent.parent / "static"
static_dir.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/")
async def home(request: Request):
    """Homepage route."""
    from app.services.watchlist_service import get_top_movers

    account_id_str = request.session.get('account_id')

    try:
        top_movers = get_top_movers(limit=5, account_id=account_id_str)
    except Exception as e:
        print(f"Error fetching top movers: {e}")
        top_movers = {'oversold': [], 'overbought': [], 'is_user_data': False}

    return templates.TemplateResponse("index.html", {
        "request": request,
        "oversold": top_movers['oversold'],
        "overbought": top_movers['overbought'],
        "is_user_data": top_movers.get('is_user_data', False)
    })


@app.get("/portfolios", response_class=HTMLResponse)
async def portfolios_page(request: Request):
    """
    Display portfolios page (placeholder).

    Returns:
        HTML page for portfolios (coming soon)
    """
    return templates.TemplateResponse("portfolios.html", {"request": request})




