"""Browser tests for stock detail page using Playwright."""
import pytest
from playwright.sync_api import Page, expect
from app.database import engine, create_db_and_tables
from sqlmodel import Session
from app.models.stock_price import StockPrice, StockAttributes
from tests.conftest import populate_test_stock_prices


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables and clean up before and after each test."""
    create_db_and_tables()
    
    # Populate test data for common tickers used in tests
    populate_test_stock_prices("AAPL")
    populate_test_stock_prices("MSFT")
    populate_test_stock_prices("GOOGL")
    populate_test_stock_prices("TSLA")
    populate_test_stock_prices("HD")
    populate_test_stock_prices("SHOP")
    
    yield
    
    # Cleanup after test
    with Session(engine) as session:
        from sqlmodel import select
        # Clean stock_price tables
        statement = select(StockPrice)
        all_prices = session.exec(statement).all()
        for price in all_prices:
            session.delete(price)
        
        statement = select(StockAttributes)
        all_attributes = session.exec(statement).all()
        for attributes in all_attributes:
            session.delete(attributes)
        
        session.commit()


@pytest.fixture
def live_server_url():
    """Return the URL of the live server."""
    import os
    # Use environment variable if set (for Docker), otherwise use localhost
    return os.getenv("TEST_SERVER_URL", "http://localhost:8000")


@pytest.mark.browser
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
        expect(page).to_have_title(f"Stock: {ticker} - Arthos", timeout=10000)
        
        # Check main heading
        expect(page.locator(f"h1:has-text('{ticker}')")).to_be_visible()
        
        # Check chart container exists
        expect(page.locator("#stockChart")).to_be_visible(timeout=10000)
        
        # Check metrics card exists
        expect(page.locator(".metrics-card")).to_be_visible()
        
        # Check all metric labels exist
        expect(page.locator(".metric-label:has-text('Current Price')")).to_be_visible()
        
        # Check that current price timestamp is displayed (if available)
        current_price_item = page.locator(".metric-item").filter(has_text="Current Price")
        expect(current_price_item).to_be_visible()
        # Check for timestamp above current price (could be date or date+time format)
        timestamp_element = current_price_item.locator(".text-muted.small")
        if timestamp_element.count() > 0:
            timestamp_text = timestamp_element.inner_text().strip()
            assert timestamp_text != "", "Timestamp should not be empty if displayed"
            # Timestamp should be in format YYYY-MM-DD or YYYY-MM-DD HH:MM:SS
            import re
            assert re.match(r'^\d{4}-\d{2}-\d{2}(\s+\d{2}:\d{2}:\d{2})?$', timestamp_text), \
                f"Timestamp format should be YYYY-MM-DD or YYYY-MM-DD HH:MM:SS, got: {timestamp_text}"
        
        # Verify that current price value is displayed
        current_price_value = current_price_item.locator(".metric-value")
        expect(current_price_value).to_be_visible()
        price_text = current_price_value.inner_text().strip()
        assert price_text.startswith("$"), f"Current price should start with $, got: {price_text}"
        
        expect(page.locator(".metric-label:has-text('SMA 50')")).to_be_visible()
        expect(page.locator(".metric-label:has-text('SMA 200')")).to_be_visible()
        expect(page.locator(".metric-label:has-text('Dividend Yield')")).to_be_visible()
        expect(page.locator(".metric-label:has-text('Signal')")).to_be_visible()
        expect(page.locator(".metric-label:has-text('Trading Range')")).to_be_visible()
        
        # Check for HR separator (should be after chart)
        hr_elements = page.locator("hr")
        expect(hr_elements.first).to_be_visible()
        
        # Check that tabs exist
        expect(page.locator("ul.nav-tabs")).to_be_visible(timeout=15000)
        expect(page.locator("button#option-data-tab")).to_be_visible()
        expect(page.locator("button#covered-calls-tab")).to_be_visible()
        
        # Check Option Data tab is active by default
        option_data_tab = page.locator("button#option-data-tab")
        option_data_tab_classes = option_data_tab.get_attribute("class") or ""
        assert "active" in option_data_tab_classes, f"Option Data tab should be active, but has classes: {option_data_tab_classes}"
        
        # Check Option Data tab content is visible
        option_data_pane = page.locator("#option-data.tab-pane")
        expect(option_data_pane).to_be_visible()
        option_data_pane_classes = option_data_pane.get_attribute("class") or ""
        assert "active" in option_data_pane_classes and "show" in option_data_pane_classes, \
            f"Option Data pane should have 'active' and 'show' classes, but has: {option_data_pane_classes}"
        
        # Check Covered Calls tab content exists but is not active initially
        covered_calls_tab_pane = page.locator("#covered-calls.tab-pane")
        expect(covered_calls_tab_pane).to_be_attached()  # Element exists in DOM
        # Should not have 'show active' classes initially (Bootstrap hides inactive tabs)
        classes = covered_calls_tab_pane.get_attribute("class") or ""
        # Initially, it should not have both 'show' and 'active' classes
        has_both = "show" in classes and "active" in classes
        assert not has_both, f"Covered Calls tab should not be active initially, but has classes: {classes}"
        
        # Check that option data table exists (even if empty)
        option_table = page.locator("table").filter(has_text="Put")
        if option_table.count() > 0:
            expect(option_table.first).to_be_visible()
            # Check table headers - scope to Option Data table to avoid matching Covered Calls table
            # Use .first to handle multiple matches (Put and Call both have Last/Bid/Ask headers)
            option_data_section = page.locator("#option-data")
            expect(option_data_section.locator("th:has-text('Strike')").first).to_be_visible()
            expect(option_data_section.locator("th:has-text('Last')").first).to_be_visible()
            expect(option_data_section.locator("th:has-text('Bid')").first).to_be_visible()
            expect(option_data_section.locator("th:has-text('Ask')").first).to_be_visible()
        
        # Check that covered calls table exists (need to switch to that tab first)
        covered_calls_tab = page.locator("button#covered-calls-tab")
        if covered_calls_tab.count() > 0:
            covered_calls_tab.click()
            page.wait_for_timeout(500)  # Wait for tab switch animation
            
            # Check table headers for covered calls
            expect(page.locator("th:has-text('Strike Price')")).to_be_visible(timeout=5000)
            expect(page.locator("th:has-text('Call Premium')")).to_be_visible()
            expect(page.locator("th:has-text('Total Return Exercised')")).to_be_visible()
            expect(page.locator("th:has-text('Total Return Not Exercised')")).to_be_visible()
            expect(page.locator("th:has-text('Return Breakdown')")).to_be_visible()
        
        # Check for any error messages
        error_messages = page.locator(".alert-danger, .text-danger, .error")
        if error_messages.count() > 0:
            error_text = error_messages.first.inner_text()
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
            
            # Make sure we're on the Option Data tab
            option_data_tab = page.locator("button#option-data-tab")
            if option_data_tab.count() > 0:
                option_data_tab.click()
                page.wait_for_timeout(500)  # Wait for tab switch
            
            # Check if options table exists
            option_table = page.locator("#option-data table").filter(has_text="Put")
            if option_table.count() == 0:
                # Skip if no options data available
                continue
            
            # Get current price from metrics
            current_price_elem = page.locator(".metric-value").filter(has_text="$")
            if current_price_elem.count() == 0:
                continue
            
            # Find all strike price cells in options table
            strike_cells = page.locator("#option-data table").filter(has_text="Put").locator("td.fw-bold")
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
            current_price_text = current_price_elem.first.inner_text().strip()
            try:
                current_price = float(current_price_text.replace("$", "").replace(",", ""))
            except ValueError:
                continue
            
            # Calculate minimum distance
            min_distance = min(abs(strike - current_price) for strike in strikes)
            
            # Find rows with closest strikes
            closest_strikes = [s for s in strikes if abs(s - current_price) == min_distance]
            
            # Check that at least one row is highlighted
            highlighted_rows = page.locator("#option-data table").filter(has_text="Put").locator("tr.table-warning")
            highlighted_count = highlighted_rows.count()
            
            # Debug output
            print(f"\n=== Debug Options Table for {ticker} ===")
            print(f"Current price: {current_price}")
            print(f"Strikes: {strikes}")
            print(f"Min distance: {min_distance}")
            print(f"Closest strikes: {closest_strikes}")
            print(f"Highlighted rows count: {highlighted_count}")
            
            assert highlighted_count > 0, f"No highlighted rows found in Options Data table for {ticker}. Current price: {current_price}, Strikes: {strikes}, Min distance: {min_distance}"
            
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
            
            # Use epsilon comparison for floating point precision
            epsilon = 0.01
            assert any(abs(abs(hs - current_price) - min_distance) < epsilon for hs in highlighted_strikes), \
                f"Highlighted strikes {highlighted_strikes} don't match closest strikes {closest_strikes} for {ticker}. " \
                f"Current price: {current_price}, Min distance: {min_distance}"
    
    def test_closest_strike_highlighted_in_covered_calls_table(self, page: Page, live_server_url):
        """Test that the closest strike price row is highlighted in Covered Calls table."""
        tickers = ["AAPL", "TSLA", "SHOP"]
        
        for ticker in tickers:
            page.goto(f"{live_server_url}/stock/{ticker}")
            page.wait_for_load_state("networkidle", timeout=30000)
            
            # Switch to Covered Calls tab
            covered_calls_tab = page.locator("button#covered-calls-tab")
            if covered_calls_tab.count() == 0:
                continue
            
            covered_calls_tab.click()
            page.wait_for_timeout(500)  # Wait for tab switch animation
            
            # Find covered calls table
            covered_calls_table = page.locator("#covered-calls table").filter(has_text="Strike Price")
            if covered_calls_table.count() == 0:
                # Skip if no covered calls data
                continue
            
            # Get current price from metrics
            current_price_elem = page.locator(".metric-value").filter(has_text="$")
            if current_price_elem.count() == 0:
                continue
            
            current_price_text = current_price_elem.first.inner_text().strip()
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
            highlighted_count = highlighted_rows.count()
            
            # Debug output
            print(f"\n=== Debug for {ticker} ===")
            print(f"Current price: {current_price}")
            print(f"Strikes: {strikes}")
            print(f"Min distance: {min_distance}")
            print(f"Closest strikes: {closest_strikes}")
            print(f"Highlighted rows count: {highlighted_count}")
            
            # Get all rows to see what's there
            all_rows = covered_calls_table.locator("tbody tr")
            print(f"Total rows: {all_rows.count()}")
            
            # Check each row for the class
            for i in range(all_rows.count()):
                row = all_rows.nth(i)
                classes = row.get_attribute("class") or ""
                has_warning = "table-warning" in classes
                strike_cell = row.locator("td.fw-bold")
                if strike_cell.count() > 0:
                    strike_text = strike_cell.inner_text().strip()
                    print(f"  Row {i}: strike={strike_text}, has_warning={has_warning}, classes={classes}")
            
            assert highlighted_count > 0, f"No highlighted rows found in Covered Calls table for {ticker}. Current price: {current_price}, Strikes: {strikes}, Min distance: {min_distance}"
            
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
            
            print(f"Highlighted strikes: {highlighted_strikes}")
            
            # Use epsilon comparison for floating point precision
            epsilon = 0.01
            assert any(abs(abs(hs - current_price) - min_distance) < epsilon for hs in highlighted_strikes), \
                f"Highlighted strikes {highlighted_strikes} don't match closest strikes {closest_strikes} for {ticker}. " \
                f"Current price: {current_price}, Min distance: {min_distance}"
    
    def test_equidistant_strikes_both_highlighted(self, page: Page, live_server_url):
        """Test that if two strikes are equidistant from current price, both are highlighted."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)
        
        # Get current price
        current_price_elem = page.locator(".metric-value").filter(has_text="$")
        if current_price_elem.count() == 0:
            pytest.skip("Could not find current price")
        
        current_price_text = current_price_elem.first.inner_text().strip()
        try:
            current_price = float(current_price_text.replace("$", "").replace(",", ""))
        except ValueError:
            pytest.skip("Could not parse current price")
        
        # Switch to Covered Calls tab
        covered_calls_tab = page.locator("button#covered-calls-tab")
        if covered_calls_tab.count() == 0:
            pytest.skip("Covered Calls tab not found")
        
        covered_calls_tab.click()
        page.wait_for_timeout(500)  # Wait for tab switch animation
        
        # Check covered calls table
        covered_calls_table = page.locator("#covered-calls table").filter(has_text="Strike Price")
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
    
    def test_tabs_functionality(self, page: Page, live_server_url):
        """Test that Bootstrap tabs work correctly for Option Data and Covered Calls."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)
        
        # Check tabs exist
        expect(page.locator("ul.nav-tabs")).to_be_visible()
        option_data_tab = page.locator("button#option-data-tab")
        covered_calls_tab = page.locator("button#covered-calls-tab")
        
        expect(option_data_tab).to_be_visible()
        expect(covered_calls_tab).to_be_visible()
        
        # Check Option Data tab is active by default
        option_data_tab_classes = option_data_tab.get_attribute("class") or ""
        assert "active" in option_data_tab_classes, f"Option Data tab should be active, but has classes: {option_data_tab_classes}"
        
        option_data_pane = page.locator("#option-data.tab-pane")
        option_data_pane_classes = option_data_pane.get_attribute("class") or ""
        assert "active" in option_data_pane_classes and "show" in option_data_pane_classes, \
            f"Option Data pane should have 'active' and 'show' classes, but has: {option_data_pane_classes}"
        
        # Check Covered Calls tab is not active initially
        covered_calls_pane = page.locator("#covered-calls.tab-pane")
        classes = covered_calls_pane.get_attribute("class") or ""
        has_both = "show" in classes and "active" in classes
        assert not has_both, f"Covered Calls should not be active initially, but has classes: {classes}"
        
        # Click Covered Calls tab
        covered_calls_tab.click()
        page.wait_for_timeout(500)  # Wait for Bootstrap tab animation
        
        # Check Covered Calls tab is now active
        covered_calls_tab_classes = covered_calls_tab.get_attribute("class") or ""
        assert "active" in covered_calls_tab_classes, f"Covered Calls tab should be active, but has classes: {covered_calls_tab_classes}"
        
        covered_calls_pane_classes = covered_calls_pane.get_attribute("class") or ""
        assert "active" in covered_calls_pane_classes and "show" in covered_calls_pane_classes, \
            f"Covered Calls pane should have 'active' and 'show' classes, but has: {covered_calls_pane_classes}"
        
        # Check Option Data tab is no longer active
        option_data_pane = page.locator("#option-data.tab-pane")
        classes = option_data_pane.get_attribute("class") or ""
        # Should not have both 'show' and 'active' classes after switching
        has_both = "show" in classes and "active" in classes
        assert not has_both, f"Option Data should not be active after switching tabs, but has classes: {classes}"
        
        # Click back to Option Data tab
        option_data_tab.click()
        page.wait_for_timeout(500)  # Wait for Bootstrap tab animation
        
        # Check Option Data tab is active again
        option_data_tab_classes = option_data_tab.get_attribute("class") or ""
        assert "active" in option_data_tab_classes, f"Option Data tab should be active again, but has classes: {option_data_tab_classes}"
        
        option_data_pane_classes = option_data_pane.get_attribute("class") or ""
        assert "active" in option_data_pane_classes and "show" in option_data_pane_classes, \
            f"Option Data pane should have 'active' and 'show' classes again, but has: {option_data_pane_classes}"
        
        # Check Covered Calls tab is no longer active
        classes = covered_calls_pane.get_attribute("class") or ""
        # Should not have both 'show' and 'active' classes after switching back
        has_both = "show" in classes and "active" in classes
        assert not has_both, f"Covered Calls should not be active after switching back, but has classes: {classes}"
    
    def test_tab_content_visibility(self, page: Page, live_server_url):
        """Test that tab content is only visible when the tab is active."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)
        
        # Initially, Option Data content should be visible
        option_data_pane = page.locator("#option-data.tab-pane")
        expect(option_data_pane).to_be_visible()
        
        # Check if Option Data table exists and is visible
        option_table = page.locator("#option-data table")
        if option_table.count() > 0:
            expect(option_table.first).to_be_visible()
        
        # Covered Calls content should exist but may not be visible initially (depends on Bootstrap)
        covered_calls_pane = page.locator("#covered-calls.tab-pane")
        expect(covered_calls_pane).to_be_attached()  # Element exists in DOM
        # Initially it should not be visible (Bootstrap hides inactive tabs)
        classes = covered_calls_pane.get_attribute("class") or ""
        has_both = "show" in classes and "active" in classes
        assert not has_both, f"Covered Calls should not be visible initially, but has classes: {classes}"
        
        # Switch to Covered Calls tab
        covered_calls_tab = page.locator("button#covered-calls-tab")
        covered_calls_tab.click()
        page.wait_for_timeout(500)
        
        # Covered Calls content should now be visible
        expect(covered_calls_pane).to_be_visible()
        
        # Check if Covered Calls table exists and is visible
        covered_calls_table = page.locator("#covered-calls table")
        if covered_calls_table.count() > 0:
            expect(covered_calls_table.first).to_be_visible()
    
    def test_current_price_timestamp_displayed(self, page: Page, live_server_url):
        """Test that the timestamp of current stock price data is displayed above Current Price."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)
        
        # Find the Current Price metric item
        current_price_item = page.locator(".metric-item").filter(has_text="Current Price")
        expect(current_price_item).to_be_visible()
        
        # Check for timestamp above current price
        timestamp_element = current_price_item.locator(".text-muted.small")
        timestamp_count = timestamp_element.count()
        
        # Timestamp should be displayed (if we have data)
        if timestamp_count > 0:
            timestamp_text = timestamp_element.inner_text().strip()
            assert timestamp_text != "", "Timestamp should not be empty if displayed"
            
            # Verify timestamp format (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS)
            import re
            assert re.match(r'^\d{4}-\d{2}-\d{2}(\s+\d{2}:\d{2}:\d{2})?$', timestamp_text), \
                f"Timestamp format should be YYYY-MM-DD or YYYY-MM-DD HH:MM:SS, got: {timestamp_text}"
            
            # Verify current price is displayed below timestamp
            current_price_value = current_price_item.locator(".metric-value")
            expect(current_price_value).to_be_visible()
            price_text = current_price_value.inner_text().strip()
            assert price_text.startswith("$"), f"Current price should start with $, got: {price_text}"
    
    def test_todays_candle_displayed_on_chart(self, page: Page, live_server_url):
        """Test that today's aggregated candle (from intraday data) is displayed on the chart."""
        from datetime import datetime
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)
        
        # Wait for chart to load
        expect(page.locator("#stockChart")).to_be_visible(timeout=10000)
        
        # Get today's date
        today = datetime.now().date().strftime('%Y-%m-%d')
        
        # Check if chart data includes today's date
        # We can verify this by checking the JavaScript chart data
        chart_data_script = page.locator("script").filter(has_text="candlestickData")
        if chart_data_script.count() > 0:
            script_content = chart_data_script.inner_text()
            # Check if today's date appears in the candlestick data
            # The date format in the chart data should be YYYY-MM-DD
            if today in script_content:
                # Today's date is in the chart data, which means today's aggregated candle is included
                # Verify the data structure is correct by checking for the date in the JSON
                assert f'"x":"{today}"' in script_content or f'"x": "{today}"' in script_content, \
                    f"Today's date {today} should be in chart candlestick data"
    
    def test_options_tables_have_datatables(self, page: Page, live_server_url):
        """Test that all options tables are initialized with DataTables and have search functionality."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)
        
        # Wait for DataTables to initialize
        page.wait_for_timeout(2000)
        
        # Check Option Data table has DataTables
        option_table = page.locator("#optionsDataTable")
        if option_table.count() > 0:
            # Check for DataTables search box
            search_input = page.locator("#optionsDataTable_filter input")
            expect(search_input).to_be_visible(timeout=5000)
            
            # Check for DataTables pagination
            pagination = page.locator("#optionsDataTable_paginate")
            expect(pagination).to_be_visible()
            
            # Check for page length selector
            length_select = page.locator("#optionsDataTable_length select")
            expect(length_select).to_be_visible()
            
            # Verify page length is set to 50
            length_value = length_select.input_value()
            assert length_value == "50", f"Expected page length 50, got {length_value}"
        
        # Switch to Covered Calls tab
        covered_calls_tab = page.locator("button#covered-calls-tab")
        if covered_calls_tab.count() > 0:
            covered_calls_tab.click()
            page.wait_for_timeout(1000)
            
            # Check Covered Calls table has DataTables
            covered_calls_table = page.locator("#coveredCallsTable")
            if covered_calls_table.count() > 0:
                search_input = page.locator("#coveredCallsTable_filter input")
                expect(search_input).to_be_visible(timeout=5000)
                
                length_select = page.locator("#coveredCallsTable_length select")
                expect(length_select).to_be_visible()
                
                length_value = length_select.input_value()
                assert length_value == "50", f"Expected page length 50, got {length_value}"
        
        # Switch to Risk Reversal tab
        risk_reversal_tab = page.locator("button#risk-reversal-tab")
        if risk_reversal_tab.count() > 0:
            risk_reversal_tab.click()
            page.wait_for_timeout(1000)
            
            # Check for ratio filter buttons
            ratio_filter_1_1 = page.locator("#ratioFilter1_1")
            ratio_filter_1_2 = page.locator("#ratioFilter1_2")
            ratio_filter_all = page.locator("#ratioFilterAll")
            
            if ratio_filter_1_1.count() > 0:
                expect(ratio_filter_1_1).to_be_visible()
                expect(ratio_filter_1_2).to_be_visible()
                expect(ratio_filter_all).to_be_visible()
                
                # Check that 1:1 is selected by default
                assert ratio_filter_1_1.is_checked(), "1:1 filter should be selected by default"
                
                # Check Risk Reversal tables have DataTables
                risk_reversal_tables = page.locator(".risk-reversal-table")
                if risk_reversal_tables.count() > 0:
                        # Get first table
                        first_table = risk_reversal_tables.first
                        first_table_id = first_table.get_attribute("id")
                        if first_table_id:
                            # Wait a bit for DataTables to initialize
                            page.wait_for_timeout(1500)
                            
                            # Check for DataTables search box
                            search_input = page.locator(f"#{first_table_id}_filter input")
                            expect(search_input).to_be_visible(timeout=5000)
                            
                            # Get initial row count with 1:1 filter
                            initial_rows = first_table.locator("tbody tr").count()
                            initial_1_1_rows = first_table.locator("tbody tr").filter(has_text="1:1").count()
                        
                        print(f"\n=== Risk Reversal Filter Test ===")
                        print(f"Initial rows (1:1 filter): {initial_rows}")
                        print(f"Initial 1:1 rows: {initial_1_1_rows}")
                        
                        # Test filtering - click 1:2 filter
                        ratio_filter_1_2.click()
                        page.wait_for_timeout(1500)  # Wait for filter to apply
                        
                        # Verify filter is applied
                        assert ratio_filter_1_2.is_checked(), "1:2 filter should be checked after clicking"
                        assert not ratio_filter_1_1.is_checked(), "1:1 filter should not be checked after switching"
                        
                        # Verify table filtered (should show different rows)
                        rows_after_1_2 = first_table.locator("tbody tr").count()
                        rows_with_1_2 = first_table.locator("tbody tr").filter(has_text="1:2").count()
                        
                        print(f"Rows after 1:2 filter: {rows_after_1_2}")
                        print(f"Rows with 1:2: {rows_with_1_2}")
                        
                        # If there are 1:2 strategies, verify they're shown
                        if rows_with_1_2 > 0:
                            assert rows_after_1_2 == rows_with_1_2, \
                                f"After 1:2 filter, all visible rows should be 1:2. Found {rows_after_1_2} rows, {rows_with_1_2} with 1:2"
                        
                        # Click All filter
                        ratio_filter_all.click()
                        page.wait_for_timeout(1500)
                        assert ratio_filter_all.is_checked(), "All filter should be checked after clicking"
                        
                        rows_after_all = first_table.locator("tbody tr").count()
                        print(f"Rows after All filter: {rows_after_all}")
                        
                        # All filter should show more or equal rows compared to 1:1 filter
                        assert rows_after_all >= initial_rows, \
                            f"All filter should show at least as many rows as 1:1 filter. Got {rows_after_all}, expected >= {initial_rows}"
                        
                        # Click back to 1:1
                        ratio_filter_1_1.click()
                        page.wait_for_timeout(1500)
                        assert ratio_filter_1_1.is_checked(), "1:1 filter should be checked after clicking back"
                        
                        rows_after_1_1_again = first_table.locator("tbody tr").count()
                        print(f"Rows after switching back to 1:1: {rows_after_1_1_again}")
                        
                        # Should match initial count
                        assert rows_after_1_1_again == initial_rows, \
                            f"After switching back to 1:1, should have same row count. Got {rows_after_1_1_again}, expected {initial_rows}"
    
    def test_options_table_column_count_fixed(self, page: Page, live_server_url):
        """Test that options table has consistent column count for all rows (fixes HD stock issue)."""
        # Test with HD stock which was reported to have the issue
        ticker = "HD"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)
        
        # Wait for DataTables to initialize
        page.wait_for_timeout(2000)
        
        # Check for console errors
        console_errors = []
        def handle_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text)
        page.on("console", handle_console)
        
        # Check Option Data table
        option_table = page.locator("#optionsDataTable")
        if option_table.count() > 0:
            # Get all rows
            rows = option_table.locator("tbody tr")
            row_count = rows.count()
            
            if row_count > 0:
                # Check each row has exactly 13 columns (6 put + 1 strike + 6 call)
                for i in range(min(10, row_count)):  # Check first 10 rows
                    row = rows.nth(i)
                    cells = row.locator("td")
                    cell_count = cells.count()
                    assert cell_count == 13, \
                        f"Row {i} should have 13 columns, but has {cell_count}. " \
                        f"Row HTML: {row.inner_html()[:200]}"
        
        # Check for DataTables errors
        page.wait_for_timeout(1000)
        datatables_errors = [err for err in console_errors if "DataTables" in err and "column count" in err.lower()]
        assert len(datatables_errors) == 0, \
            f"DataTables column count errors found: {datatables_errors}"
    
    def test_datatables_search_functionality(self, page: Page, live_server_url):
        """Test that DataTables search works correctly on options tables."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        
        # Test Option Data table search
        option_table = page.locator("#optionsDataTable")
        if option_table.count() > 0:
            search_input = page.locator("#optionsDataTable_filter input")
            if search_input.count() > 0:
                # Type a search term (e.g., a strike price)
                search_input.fill("100")
                page.wait_for_timeout(500)
                
                # Verify table filtered (should show fewer rows or no rows)
                # We can't easily verify the exact content, but we can check the table updated
                rows_after = option_table.locator("tbody tr").count()
                
                # Clear search
                search_input.fill("")
                page.wait_for_timeout(500)
                rows_after_clear = option_table.locator("tbody tr").count()
                
                # After clearing, should have same or more rows
                assert rows_after_clear >= rows_after, \
                    "After clearing search, should have same or more rows"
        
        # Test Covered Calls table search
        covered_calls_tab = page.locator("button#covered-calls-tab")
        if covered_calls_tab.count() > 0:
            covered_calls_tab.click()
            page.wait_for_timeout(1000)
            
            covered_calls_table = page.locator("#coveredCallsTable")
            if covered_calls_table.count() > 0:
                search_input = page.locator("#coveredCallsTable_filter input")
                if search_input.count() > 0:
                    search_input.fill("150")
                    page.wait_for_timeout(500)
                    
                    # Clear search
                    search_input.fill("")
                    page.wait_for_timeout(500)
    
    def test_risk_reversal_filter_functionality(self, page: Page, live_server_url):
        """Test that Risk Reversal ratio filter buttons work correctly."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        
        # Switch to Risk Reversal tab
        risk_reversal_tab = page.locator("button#risk-reversal-tab")
        if risk_reversal_tab.count() == 0:
            pytest.skip("Risk Reversal tab not found")
        
        risk_reversal_tab.click()
        page.wait_for_timeout(1500)  # Wait for tab switch and table initialization
        
        # Check for ratio filter buttons
        ratio_filter_1_1 = page.locator("#ratioFilter1_1")
        ratio_filter_1_2 = page.locator("#ratioFilter1_2")
        ratio_filter_all = page.locator("#ratioFilterAll")
        
        if ratio_filter_1_1.count() == 0:
            pytest.skip("Risk Reversal filter buttons not found")
        
        expect(ratio_filter_1_1).to_be_visible()
        expect(ratio_filter_1_2).to_be_visible()
        expect(ratio_filter_all).to_be_visible()
        
        # Check that 1:1 is selected by default
        assert ratio_filter_1_1.is_checked(), "1:1 filter should be selected by default"
        assert not ratio_filter_1_2.is_checked(), "1:2 filter should not be selected by default"
        assert not ratio_filter_all.is_checked(), "All filter should not be selected by default"
        
        # Get all Risk Reversal tables
        risk_reversal_tables = page.locator(".risk-reversal-table")
        if risk_reversal_tables.count() == 0:
            pytest.skip("No Risk Reversal tables found")
        
        # Get initial row count with 1:1 filter
        first_table = risk_reversal_tables.first
        initial_rows = first_table.locator("tbody tr").count()
        
        # Count rows with 1:1 ratio in the first table
        initial_1_1_rows = first_table.locator("tbody tr").filter(has_text="1:1").count()
        
        print(f"\n=== Risk Reversal Filter Test for {ticker} ===")
        print(f"Initial rows (1:1 filter): {initial_rows}")
        print(f"Initial 1:1 rows: {initial_1_1_rows}")
        
        # Test 1:2 filter
        ratio_filter_1_2.click()
        page.wait_for_timeout(1000)  # Wait for filter to apply
        
        assert ratio_filter_1_2.is_checked(), "1:2 filter should be checked after clicking"
        assert not ratio_filter_1_1.is_checked(), "1:1 filter should not be checked after switching"
        
        # Verify table filtered (should show different rows)
        rows_after_1_2 = first_table.locator("tbody tr").count()
        rows_with_1_2 = first_table.locator("tbody tr").filter(has_text="1:2").count()
        
        print(f"Rows after 1:2 filter: {rows_after_1_2}")
        print(f"Rows with 1:2: {rows_with_1_2}")
        
        # If there are 1:2 strategies, verify they're shown
        if rows_with_1_2 > 0:
            assert rows_after_1_2 == rows_with_1_2, \
                f"After 1:2 filter, all visible rows should be 1:2. Found {rows_after_1_2} rows, {rows_with_1_2} with 1:2"
        
        # Test All filter
        ratio_filter_all.click()
        page.wait_for_timeout(1000)
        assert ratio_filter_all.is_checked(), "All filter should be checked after clicking"
        
        rows_after_all = first_table.locator("tbody tr").count()
        print(f"Rows after All filter: {rows_after_all}")
        
        # All filter should show more or equal rows compared to 1:1 filter
        assert rows_after_all >= initial_rows, \
            f"All filter should show at least as many rows as 1:1 filter. Got {rows_after_all}, expected >= {initial_rows}"
        
        # Test switching back to 1:1
        ratio_filter_1_1.click()
        page.wait_for_timeout(1000)
        assert ratio_filter_1_1.is_checked(), "1:1 filter should be checked after clicking back"
        
        rows_after_1_1_again = first_table.locator("tbody tr").count()
        print(f"Rows after switching back to 1:1: {rows_after_1_1_again}")
        
        # Should match initial count
        assert rows_after_1_1_again == initial_rows, \
            f"After switching back to 1:1, should have same row count. Got {rows_after_1_1_again}, expected {initial_rows}"
        
        # Verify all visible rows have 1:1 ratio
        visible_1_1_rows = first_table.locator("tbody tr").filter(has_text="1:1").count()
        assert visible_1_1_rows == rows_after_1_1_again, \
            f"All visible rows should be 1:1. Found {rows_after_1_1_again} rows, {visible_1_1_rows} with 1:1"
    
    def test_risk_reversal_filter_functionality_msft(self, page: Page, live_server_url):
        """Test that Risk Reversal ratio filter buttons work correctly with MSFT stock - comprehensive test."""
        ticker = "MSFT"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(3000)  # Wait for page to fully load
        
        # Switch to Risk Reversal tab
        risk_reversal_tab = page.locator("button#risk-reversal-tab")
        if risk_reversal_tab.count() == 0:
            pytest.skip("Risk Reversal tab not found")
        
        risk_reversal_tab.click()
        page.wait_for_timeout(2000)  # Wait for tab switch and table initialization
        
        # Check for ratio filter buttons
        ratio_filter_1_1 = page.locator("#ratioFilter1_1")
        ratio_filter_1_2 = page.locator("#ratioFilter1_2")
        ratio_filter_all = page.locator("#ratioFilterAll")
        
        if ratio_filter_1_1.count() == 0:
            pytest.skip("Risk Reversal filter buttons not found")
        
        expect(ratio_filter_1_1).to_be_visible()
        expect(ratio_filter_1_2).to_be_visible()
        expect(ratio_filter_all).to_be_visible()
        
        # Check that 1:1 is selected by default
        assert ratio_filter_1_1.is_checked(), "1:1 filter should be selected by default"
        assert not ratio_filter_1_2.is_checked(), "1:2 filter should not be selected by default"
        assert not ratio_filter_all.is_checked(), "All filter should not be selected by default"
        
        # Get all Risk Reversal tables
        risk_reversal_tables = page.locator(".risk-reversal-table")
        if risk_reversal_tables.count() == 0:
            pytest.skip("No Risk Reversal tables found")
        
        # Get first table for testing
        first_table = risk_reversal_tables.first
        
        # Wait for table to be fully initialized
        page.wait_for_timeout(1000)
        
        # Get initial row count with 1:1 filter (default)
        initial_rows = first_table.locator("tbody tr:visible").count()
        initial_1_1_rows = first_table.locator("tbody tr:visible").filter(has_text="1:1").count()
        initial_1_2_rows = first_table.locator("tbody tr:visible").filter(has_text="1:2").count()
        
        print(f"\n=== Risk Reversal Filter Test for {ticker} ===")
        print(f"Initial visible rows (1:1 filter): {initial_rows}")
        print(f"Initial 1:1 rows: {initial_1_1_rows}")
        print(f"Initial 1:2 rows (should be 0): {initial_1_2_rows}")
        
        # Verify that initially only 1:1 rows are shown
        assert initial_1_2_rows == 0, f"Initially, 1:2 rows should be hidden. Found {initial_1_2_rows} visible 1:2 rows"
        assert initial_1_1_rows == initial_rows, \
            f"Initially, all visible rows should be 1:1. Found {initial_rows} total, {initial_1_1_rows} with 1:1"
        
        # Test 1: Filter 1:2 - should show only 1:2 rows
        print("\n--- Testing 1:2 filter ---")
        ratio_filter_1_2.click()
        page.wait_for_timeout(2000)  # Wait for filter to apply
        
        assert ratio_filter_1_2.is_checked(), "1:2 filter should be checked after clicking"
        assert not ratio_filter_1_1.is_checked(), "1:1 filter should not be checked after switching"
        
        # Verify table filtered - should show only 1:2 rows
        rows_after_1_2 = first_table.locator("tbody tr:visible").count()
        rows_with_1_2 = first_table.locator("tbody tr:visible").filter(has_text="1:2").count()
        rows_with_1_1_after_1_2 = first_table.locator("tbody tr:visible").filter(has_text="1:1").count()
        
        print(f"Rows after 1:2 filter: {rows_after_1_2}")
        print(f"Rows with 1:2: {rows_with_1_2}")
        print(f"Rows with 1:1 (should be 0): {rows_with_1_1_after_1_2}")
        
        # If there are 1:2 strategies, verify only they're shown
        if rows_with_1_2 > 0:
            assert rows_after_1_2 == rows_with_1_2, \
                f"After 1:2 filter, all visible rows should be 1:2. Found {rows_after_1_2} rows, {rows_with_1_2} with 1:2"
            assert rows_with_1_1_after_1_2 == 0, \
                f"After 1:2 filter, no 1:1 rows should be visible. Found {rows_with_1_1_after_1_2} visible 1:1 rows"
        else:
            # If no 1:2 strategies exist, table might be empty or show a message
            print("No 1:2 strategies found for this stock")
        
        # Test 2: Filter All - should show all rows
        print("\n--- Testing All filter ---")
        ratio_filter_all.click()
        page.wait_for_timeout(2000)
        assert ratio_filter_all.is_checked(), "All filter should be checked after clicking"
        
        rows_after_all = first_table.locator("tbody tr:visible").count()
        rows_with_1_1_after_all = first_table.locator("tbody tr:visible").filter(has_text="1:1").count()
        rows_with_1_2_after_all = first_table.locator("tbody tr:visible").filter(has_text="1:2").count()
        
        print(f"Rows after All filter: {rows_after_all}")
        print(f"Rows with 1:1: {rows_with_1_1_after_all}")
        print(f"Rows with 1:2: {rows_with_1_2_after_all}")
        
        # All filter should show more or equal rows compared to 1:1 filter
        assert rows_after_all >= initial_rows, \
            f"All filter should show at least as many rows as 1:1 filter. Got {rows_after_all}, expected >= {initial_rows}"
        
        # Verify both 1:1 and 1:2 are visible (if they exist)
        assert rows_with_1_1_after_all == initial_1_1_rows, \
            f"All filter should show all 1:1 rows. Got {rows_with_1_1_after_all}, expected {initial_1_1_rows}"
        
        # Test 3: Switch back to 1:1 - should show only 1:1 rows again
        print("\n--- Testing switch back to 1:1 filter ---")
        ratio_filter_1_1.click()
        page.wait_for_timeout(2000)
        assert ratio_filter_1_1.is_checked(), "1:1 filter should be checked after clicking back"
        
        rows_after_1_1_again = first_table.locator("tbody tr:visible").count()
        rows_with_1_1_again = first_table.locator("tbody tr:visible").filter(has_text="1:1").count()
        rows_with_1_2_again = first_table.locator("tbody tr:visible").filter(has_text="1:2").count()
        
        print(f"Rows after switching back to 1:1: {rows_after_1_1_again}")
        print(f"Rows with 1:1: {rows_with_1_1_again}")
        print(f"Rows with 1:2 (should be 0): {rows_with_1_2_again}")
        
        # Should match initial count
        assert rows_after_1_1_again == initial_rows, \
            f"After switching back to 1:1, should have same row count. Got {rows_after_1_1_again}, expected {initial_rows}"
        
        # Verify all visible rows have 1:1 ratio and no 1:2 rows are visible
        assert rows_with_1_1_again == rows_after_1_1_again, \
            f"All visible rows should be 1:1. Found {rows_after_1_1_again} rows, {rows_with_1_1_again} with 1:1"
        assert rows_with_1_2_again == 0, \
            f"After switching back to 1:1, no 1:2 rows should be visible. Found {rows_with_1_2_again} visible 1:2 rows"
        
        # Test 4: Test all combinations - 1:1 -> 1:2 -> All -> 1:1 -> 1:2
        print("\n--- Testing multiple filter switches ---")
        
        # 1:1 -> 1:2
        ratio_filter_1_2.click()
        page.wait_for_timeout(1500)
        rows_1_2 = first_table.locator("tbody tr:visible").count()
        assert ratio_filter_1_2.is_checked()
        
        # 1:2 -> All
        ratio_filter_all.click()
        page.wait_for_timeout(1500)
        rows_all = first_table.locator("tbody tr:visible").count()
        assert ratio_filter_all.is_checked()
        assert rows_all >= rows_1_2, "All filter should show at least as many rows as 1:2 filter"
        
        # All -> 1:1
        ratio_filter_1_1.click()
        page.wait_for_timeout(1500)
        rows_1_1_final = first_table.locator("tbody tr:visible").count()
        assert ratio_filter_1_1.is_checked()
        assert rows_1_1_final == initial_rows, \
            f"After multiple switches, 1:1 filter should show initial count. Got {rows_1_1_final}, expected {initial_rows}"
        
        # 1:1 -> 1:2 again
        ratio_filter_1_2.click()
        page.wait_for_timeout(1500)
        rows_1_2_final = first_table.locator("tbody tr:visible").count()
        assert ratio_filter_1_2.is_checked()
        if rows_with_1_2 > 0:
            assert rows_1_2_final == rows_with_1_2, \
                f"After multiple switches, 1:2 filter should show same count. Got {rows_1_2_final}, expected {rows_with_1_2}"
        
        print("\n=== All filter tests passed ===")

