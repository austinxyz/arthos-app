"""Pytest configuration and fixtures."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from datetime import date, timedelta
from decimal import Decimal
from sqlmodel import Session, delete, select
from app.database import engine, create_db_and_tables
from app.models.stock_price import StockPrice, StockAttributes

# Import centralized auth fixtures to make them available to all tests
from tests.fixtures.auth_fixtures import test_account, authenticated_session, unauthenticated_session


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


def _cleanup_all_tables(session):
    """
    Helper to clean up all test-related tables in correct order.
    Respects foreign key constraints by deleting child tables first.
    """
    from app.models.watchlist import WatchList, WatchListStock
    from app.models.watchlist_stock_notes import WatchlistStockNote
    from app.models.rr_watchlist import RRWatchlist, RRHistory
    from app.models.scheduler_log import SchedulerLog
    from app.models.rr_history_log import RRHistoryLog
    from app.models.account import Account

    # Delete in order respecting foreign keys
    tables_to_clean = [
        WatchlistStockNote,  # FK to WatchList
        WatchListStock,  # FK to WatchList
        WatchList,
        RRHistory,       # FK to RRWatchlist
        RRWatchlist,
        StockPrice,
        StockAttributes,
        SchedulerLog,
        RRHistoryLog,
        Account,
    ]

    for model in tables_to_clean:
        for item in session.exec(select(model)).all():
            session.delete(item)

    session.commit()


@pytest.fixture
def setup_database():
    """
    Consolidated database setup fixture.
    Creates tables and cleans up all test data before and after tests.
    Use this fixture for tests that need a clean database state.
    """
    create_db_and_tables()

    # Cleanup before test
    with Session(engine) as session:
        _cleanup_all_tables(session)

    import os
    import requests
    test_server_url = os.getenv("TEST_SERVER_URL")
    if test_server_url:
        try:
            requests.post(f"{test_server_url}/_test/clear-cache", timeout=5)
        except Exception as e:
            pass

    yield

    # Cleanup after test
    with Session(engine) as session:
        _cleanup_all_tables(session)


@pytest.fixture
def page():
    """Create a Playwright browser page."""
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        yield page
        context.close()
        browser.close()


def populate_test_stock_prices(ticker: str, num_days: int = 365, base_price: float = 150.0):
    """
    Helper function to populate test stock price data directly in the database.
    This avoids relying on yfinance which can be unreliable in CI environments.
    
    Args:
        ticker: Stock ticker symbol
        num_days: Number of days of data to create (default: 365)
        base_price: Base price to start from (default: 150.0)
    """
    ticker_upper = ticker.upper()
    
    # Precompute price data
    base_date = date.today() - timedelta(days=num_days)
    earliest_date = base_date
    latest_date = base_date + timedelta(days=num_days - 1)
    prices = []
    
    for i in range(num_days):
        price_date = base_date + timedelta(days=i)
        
        # Create a simple price pattern (slight upward trend with some variation)
        price_variation = (i % 10) * 0.5  # Small variation
        close_price = base_price + (i * 0.1) + price_variation
        open_price = close_price - 0.5
        high_price = close_price + 0.5
        low_price = close_price - 1.0
        
        # Calculate moving averages (simplified)
        dma_50 = None
        dma_200 = None
        if i >= 49:  # Have enough data for 50-day MA
            # Simple calculation: average of last 50 days
            dma_50 = Decimal(str(base_price + ((i - 24.5) * 0.1)))
        if i >= 199:  # Have enough data for 200-day MA
            dma_200 = Decimal(str(base_price + ((i - 99.5) * 0.1)))
        
        prices.append(StockPrice(
            price_date=price_date,
            ticker=ticker_upper,
            open_price=Decimal(str(open_price)).quantize(Decimal('0.0001')),
            close_price=Decimal(str(close_price)).quantize(Decimal('0.0001')),
            high_price=Decimal(str(high_price)).quantize(Decimal('0.0001')),
            low_price=Decimal(str(low_price)).quantize(Decimal('0.0001')),
            dma_50=dma_50,
            dma_200=dma_200
        ))
    
    with Session(engine) as session:
        # Remove any existing data for this ticker to avoid duplicate key errors
        session.exec(delete(StockPrice).where(StockPrice.ticker == ticker_upper))
        session.exec(delete(StockAttributes).where(StockAttributes.ticker == ticker_upper))
        
        # Insert fresh data
        session.add_all(prices)
        session.add(StockAttributes(
            ticker=ticker_upper,
            earliest_date=earliest_date,
            latest_date=latest_date,
            dividend_amt=None,
            dividend_yield=None
        ))
        
        session.commit()


@pytest.fixture
def test_user(setup_database):
    """Create a test user/account."""
    from app.models.account import Account
    from uuid import uuid4
    from datetime import datetime

    account_id = uuid4()
    with Session(engine) as session:
        user = Account(
            id=str(account_id),  # Convert UUID to string for SQLite compatibility
            email="testuser@example.com",
            google_sub="123456789",
            full_name="Test User",
            picture_url="http://example.com/pic.jpg",
            last_login_at=datetime.now()
        )
        session.add(user)
        session.commit()
        session.refresh(user)
    return user


@pytest.fixture
def auth_client(test_user):
    """
    Return a TestClient with a logged-in user session.
    Creates a fresh TestClient and uses a test endpoint to set up the session.
    """
    from app.main import app as main_app
    from fastapi import Request
    from fastapi.testclient import TestClient

    # Check if test endpoint already exists, if not add it
    test_endpoint_path = "/__test__/setup-session/{user_id}"

    # Remove the endpoint if it exists to avoid conflicts
    routes_to_remove = [route for route in main_app.routes if hasattr(route, 'path') and '/__test__/setup-session' in route.path]
    for route in routes_to_remove:
        main_app.routes.remove(route)

    # Add a test-only endpoint to set up sessions with user_id parameter
    @main_app.get(test_endpoint_path)
    async def setup_test_session(user_id: str, request: Request):
        """Test-only endpoint to set up session."""
        from app.models.account import Account
        from sqlmodel import Session
        from app.database import engine

        with Session(engine) as session:
            # Use string user_id directly - SQLite stores UUIDs as VARCHAR
            account = session.get(Account, user_id)
            if account:
                request.session["account_id"] = str(account.id)
                request.session["user"] = {
                    "name": account.full_name,
                    "email": account.email,
                    "picture": account.picture_url
                }
                return {"status": "session_set", "account_id": str(account.id)}
            return {"status": "user_not_found"}

    # Create a new TestClient
    client = TestClient(main_app)

    # Use the test endpoint to set up the session
    response = client.get(f"/__test__/setup-session/{test_user.id}")
    assert response.status_code == 200, f"Failed to set up test session: {response.text}"
    assert response.json()["status"] == "session_set", f"Session not set properly: {response.json()}"

    # Now the client has a valid session cookie
    return client
