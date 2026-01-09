"""Pytest configuration and fixtures."""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from datetime import date, timedelta
from decimal import Decimal
from sqlmodel import Session
from app.database import engine
from app.models.stock_price import StockPrice, StockPriceWatermark


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


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
    
    with Session(engine) as session:
        # Create price data
        base_date = date.today() - timedelta(days=num_days)
        earliest_date = None
        latest_date = None
        
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
            
            price = StockPrice(
                price_date=price_date,
                ticker=ticker_upper,
                open_price=Decimal(str(open_price)).quantize(Decimal('0.0001')),
                close_price=Decimal(str(close_price)).quantize(Decimal('0.0001')),
                high_price=Decimal(str(high_price)).quantize(Decimal('0.0001')),
                low_price=Decimal(str(low_price)).quantize(Decimal('0.0001')),
                dma_50=dma_50,
                dma_200=dma_200
            )
            session.add(price)
            
            # Track date range
            if earliest_date is None or price_date < earliest_date:
                earliest_date = price_date
            if latest_date is None or price_date > latest_date:
                latest_date = price_date
        
        session.commit()
        
        # Create or update watermark
        watermark = session.get(StockPriceWatermark, ticker_upper)
        if watermark:
            watermark.earliest_date = earliest_date
            watermark.latest_date = latest_date
        else:
            watermark = StockPriceWatermark(
                ticker=ticker_upper,
                earliest_date=earliest_date,
                latest_date=latest_date
            )
            session.add(watermark)
        
        session.commit()
