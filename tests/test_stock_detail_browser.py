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
            # Check table headers
            expect(page.locator("th:has-text('Strike')")).to_be_visible()
            expect(page.locator("th:has-text('Last')")).to_be_visible()
            expect(page.locator("th:has-text('Bid')")).to_be_visible()
            expect(page.locator("th:has-text('Ask')")).to_be_visible()
        
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

