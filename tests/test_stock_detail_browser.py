"""Browser tests for stock detail page using Playwright."""
import pytest
from playwright.sync_api import Page, expect
from app.database import engine, create_db_and_tables
from sqlmodel import Session
from app.models.stock_cache import StockCache


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables and clean up before and after each test."""
    create_db_and_tables()
    
    # Cleanup cache before test
    with Session(engine) as session:
        from sqlmodel import select
        statement = select(StockCache)
        all_entries = session.exec(statement).all()
        for entry in all_entries:
            session.delete(entry)
        session.commit()
    
    yield
    
    # Cleanup cache after test
    with Session(engine) as session:
        from sqlmodel import select
        statement = select(StockCache)
        all_entries = session.exec(statement).all()
        for entry in all_entries:
            session.delete(entry)
        session.commit()


@pytest.fixture
def live_server_url():
    """Return the URL of the live server."""
    return "http://localhost:8000"


class TestStockDetailBrowser:
    """Browser tests for stock detail page."""
    
    def test_stock_detail_page_loads_with_all_sections(self, page: Page, live_server_url):
        """Test that the stock detail page loads with all expected sections."""
        # Test with a well-known stock that should have options data
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        
        # Wait for page to load
        page.wait_for_load_state("networkidle", timeout=30000)
        
        # Check page title
        expect(page).to_have_title(f"{ticker} - Stock Details - Arthos", timeout=10000)
        
        # Check main heading
        expect(page.locator(f"h1:has-text('{ticker}')")).to_be_visible()
        
        # Check chart container exists
        expect(page.locator("#stockChart")).to_be_visible(timeout=10000)
        
        # Check metrics card exists
        expect(page.locator(".metrics-card")).to_be_visible()
        
        # Check all metric labels exist
        expect(page.locator(".metric-label:has-text('Current Price')")).to_be_visible()
        expect(page.locator(".metric-label:has-text('SMA 50')")).to_be_visible()
        expect(page.locator(".metric-label:has-text('SMA 200')")).to_be_visible()
        expect(page.locator(".metric-label:has-text('Dividend Yield')")).to_be_visible()
        expect(page.locator(".metric-label:has-text('Signal')")).to_be_visible()
        expect(page.locator(".metric-label:has-text('Trading Range')")).to_be_visible()
        
        # Check for HR separator (should be after chart)
        hr_elements = page.locator("hr")
        expect(hr_elements.first()).to_be_visible()
        
        # Check Option Data section exists
        expect(page.locator("h4:has-text('Option Data')")).to_be_visible(timeout=15000)
        
        # Check Covered Calls section exists
        expect(page.locator("h4:has-text('Covered Calls')")).to_be_visible(timeout=15000)
        
        # Check that option data table exists (even if empty)
        option_table = page.locator("table").filter(has_text="Put")
        if option_table.count() > 0:
            expect(option_table.first()).to_be_visible()
            # Check table headers
            expect(page.locator("th:has-text('Strike')")).to_be_visible()
            expect(page.locator("th:has-text('Last')")).to_be_visible()
            expect(page.locator("th:has-text('Bid')")).to_be_visible()
            expect(page.locator("th:has-text('Ask')")).to_be_visible()
        
        # Check that covered calls table exists
        covered_calls_table = page.locator("table").filter(has_text="Covered Calls")
        covered_calls_heading = page.locator("h4:has-text('Covered Calls')")
        if covered_calls_heading.count() > 0:
            # Check table headers for covered calls
            expect(page.locator("th:has-text('Strike Price')")).to_be_visible()
            expect(page.locator("th:has-text('Call Premium')")).to_be_visible()
            expect(page.locator("th:has-text('Total Return Exercised')")).to_be_visible()
            expect(page.locator("th:has-text('Total Return Not Exercised')")).to_be_visible()
            expect(page.locator("th:has-text('Return Breakdown')")).to_be_visible()
        
        # Check for any error messages
        error_messages = page.locator(".alert-danger, .text-danger, .error")
        if error_messages.count() > 0:
            error_text = error_messages.first().inner_text()
            pytest.fail(f"Error found on page: {error_text}")
        
        # Check console for errors
        console_errors = []
        page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
        
        # Take a screenshot for debugging if test fails
        page.screenshot(path=f"test_stock_detail_{ticker}.png", full_page=True)
        
        # If there are console errors, fail the test
        if console_errors:
            pytest.fail(f"Console errors found: {console_errors}")

