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
    
    def test_closest_strike_highlighted_in_options_table(self, page: Page, live_server_url):
        """Test that the closest strike price row is highlighted in Options Data table."""
        tickers = ["AAPL", "TSLA", "SHOP"]
        
        for ticker in tickers:
            page.goto(f"{live_server_url}/stock/{ticker}")
            page.wait_for_load_state("networkidle", timeout=30000)
            
            # Check if options table exists
            option_table = page.locator("table").filter(has_text="Put")
            if option_table.count() == 0:
                # Skip if no options data available
                continue
            
            # Get current price from metrics
            current_price_elem = page.locator(".metric-value").filter(has_text="$")
            if current_price_elem.count() == 0:
                continue
            
            # Find all strike price cells in options table
            strike_cells = page.locator("table").filter(has_text="Put").locator("td.fw-bold")
            if strike_cells.count() == 0:
                continue
            
            # Get all strike prices and find minimum distance
            strikes = []
            for i in range(strike_cells.count()):
                strike_text = strike_cells.nth(i).inner_text().strip()
                if strike_text.startswith("$"):
                    try:
                        strike_value = float(strike_text.replace("$", "").replace(",", ""))
                        strikes.append(strike_value)
                    except ValueError:
                        continue
            
            if len(strikes) == 0:
                continue
            
            # Get current price
            current_price_text = current_price_elem.first().inner_text().strip()
            try:
                current_price = float(current_price_text.replace("$", "").replace(",", ""))
            except ValueError:
                continue
            
            # Calculate minimum distance
            min_distance = min(abs(strike - current_price) for strike in strikes)
            
            # Find rows with closest strikes
            closest_strikes = [s for s in strikes if abs(s - current_price) == min_distance]
            
            # Check that at least one row is highlighted
            highlighted_rows = page.locator("table").filter(has_text="Put").locator("tr.table-warning")
            assert highlighted_rows.count() > 0, f"No highlighted rows found in Options Data table for {ticker}"
            
            # Verify that highlighted rows contain closest strikes
            highlighted_strikes = []
            for i in range(highlighted_rows.count()):
                row = highlighted_rows.nth(i)
                strike_cell = row.locator("td.fw-bold")
                if strike_cell.count() > 0:
                    strike_text = strike_cell.inner_text().strip()
                    if strike_text.startswith("$"):
                        try:
                            strike_value = float(strike_text.replace("$", "").replace(",", ""))
                            highlighted_strikes.append(strike_value)
                        except ValueError:
                            pass
            
            # At least one highlighted strike should be in the closest strikes list
            assert any(abs(hs - current_price) == min_distance for hs in highlighted_strikes), \
                f"Highlighted strikes {highlighted_strikes} don't match closest strikes {closest_strikes} for {ticker}"
    
    def test_closest_strike_highlighted_in_covered_calls_table(self, page: Page, live_server_url):
        """Test that the closest strike price row is highlighted in Covered Calls table."""
        tickers = ["AAPL", "TSLA", "SHOP"]
        
        for ticker in tickers:
            page.goto(f"{live_server_url}/stock/{ticker}")
            page.wait_for_load_state("networkidle", timeout=30000)
            
            # Check if covered calls table exists
            covered_calls_heading = page.locator("h4:has-text('Covered Calls')")
            if covered_calls_heading.count() == 0:
                continue
            
            # Find covered calls table
            covered_calls_table = page.locator("table").filter(has_text="Strike Price")
            if covered_calls_table.count() == 0:
                # Skip if no covered calls data
                continue
            
            # Get current price from metrics
            current_price_elem = page.locator(".metric-value").filter(has_text="$")
            if current_price_elem.count() == 0:
                continue
            
            current_price_text = current_price_elem.first().inner_text().strip()
            try:
                current_price = float(current_price_text.replace("$", "").replace(",", ""))
            except ValueError:
                continue
            
            # Get all strike prices from covered calls table
            strike_cells = covered_calls_table.locator("tbody tr td.fw-bold")
            if strike_cells.count() == 0:
                continue
            
            strikes = []
            for i in range(strike_cells.count()):
                strike_text = strike_cells.nth(i).inner_text().strip()
                if strike_text.startswith("$"):
                    try:
                        strike_value = float(strike_text.replace("$", "").replace(",", ""))
                        strikes.append(strike_value)
                    except ValueError:
                        continue
            
            if len(strikes) == 0:
                continue
            
            # Calculate minimum distance
            min_distance = min(abs(strike - current_price) for strike in strikes)
            closest_strikes = [s for s in strikes if abs(s - current_price) == min_distance]
            
            # Check that at least one row is highlighted
            highlighted_rows = covered_calls_table.locator("tbody tr.table-warning")
            assert highlighted_rows.count() > 0, f"No highlighted rows found in Covered Calls table for {ticker}"
            
            # Verify that highlighted rows contain closest strikes
            highlighted_strikes = []
            for i in range(highlighted_rows.count()):
                row = highlighted_rows.nth(i)
                strike_cell = row.locator("td.fw-bold")
                if strike_cell.count() > 0:
                    strike_text = strike_cell.inner_text().strip()
                    if strike_text.startswith("$"):
                        try:
                            strike_value = float(strike_text.replace("$", "").replace(",", ""))
                            highlighted_strikes.append(strike_value)
                        except ValueError:
                            pass
            
            # At least one highlighted strike should be in the closest strikes list
            assert any(abs(hs - current_price) == min_distance for hs in highlighted_strikes), \
                f"Highlighted strikes {highlighted_strikes} don't match closest strikes {closest_strikes} for {ticker}"
    
    def test_equidistant_strikes_both_highlighted(self, page: Page, live_server_url):
        """Test that if two strikes are equidistant from current price, both are highlighted."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)
        
        # Get current price
        current_price_elem = page.locator(".metric-value").filter(has_text="$")
        if current_price_elem.count() == 0:
            pytest.skip("Could not find current price")
        
        current_price_text = current_price_elem.first().inner_text().strip()
        try:
            current_price = float(current_price_text.replace("$", "").replace(",", ""))
        except ValueError:
            pytest.skip("Could not parse current price")
        
        # Check covered calls table
        covered_calls_table = page.locator("table").filter(has_text="Strike Price")
        if covered_calls_table.count() == 0:
            pytest.skip("No covered calls table found")
        
        # Get all strike prices
        strike_cells = covered_calls_table.locator("tbody tr td.fw-bold")
        if strike_cells.count() < 2:
            pytest.skip("Not enough strikes to test equidistant case")
        
        strikes = []
        for i in range(strike_cells.count()):
            strike_text = strike_cells.nth(i).inner_text().strip()
            if strike_text.startswith("$"):
                try:
                    strike_value = float(strike_text.replace("$", "").replace(",", ""))
                    strikes.append(strike_value)
                except ValueError:
                    continue
        
        if len(strikes) < 2:
            pytest.skip("Not enough valid strikes")
        
        # Calculate distances
        distances = {strike: abs(strike - current_price) for strike in strikes}
        min_distance = min(distances.values())
        
        # Count how many strikes have minimum distance
        closest_count = sum(1 for d in distances.values() if d == min_distance)
        
        # If there are multiple closest strikes, verify all are highlighted
        if closest_count > 1:
            highlighted_rows = covered_calls_table.locator("tbody tr.table-warning")
            assert highlighted_rows.count() >= closest_count, \
                f"Expected at least {closest_count} highlighted rows for {closest_count} equidistant strikes, but found {highlighted_rows.count()}"

