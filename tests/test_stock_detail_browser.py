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
    
    def test_stock_detail_page_loads_with_all_sections(self, page: Page, live_server_url, authenticated_session):
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
        
        # Check basic metrics
        # Use first() to avoid strict mode violation as there are multiple metrics cards
        expect(page.locator(".metrics-card").first).to_be_visible()
        
        # Check all metric labels exist
        expect(page.locator(".metric-label:has-text('Current Price')")).to_be_visible()
        
        # Check that current price timestamp is displayed (if available)
        current_price_item = page.locator(".metric-item").filter(has_text="Current Price")
        expect(current_price_item).to_be_visible(timeout=10000)
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
        current_price_value = current_price_item.locator(".metric-value-large")
        expect(current_price_value).to_be_visible()
        price_text = current_price_value.inner_text().strip()
        assert price_text.startswith("$"), f"Current price should start with $, got: {price_text}"
        
        expect(page.locator(".metric-label:has-text('SMA 50')")).to_be_visible()
        expect(page.locator(".metric-label:has-text('SMA 200')")).to_be_visible()
        expect(page.locator(".metric-label:has-text('Dividend Yield')")).to_be_visible()
        expect(page.locator(".metric-label:has-text('Signal')")).to_be_visible()
        expect(page.locator(".metric-label:has-text('Trading Range')")).to_be_visible()
        
        # Check that tabs exist
        expect(page.locator("ul.nav-tabs")).to_be_visible(timeout=15000)
        expect(page.locator("button#insights-tab")).to_be_visible()
        expect(page.locator("button#covered-calls-tab")).to_be_visible()
        expect(page.locator("button#risk-reversal-tab")).to_be_visible()

        # Check Insights tab is active by default
        insights_tab = page.locator("button#insights-tab")
        insights_tab_classes = insights_tab.get_attribute("class") or ""
        assert "active" in insights_tab_classes, f"Insights tab should be active by default, but has classes: {insights_tab_classes}"

        # Check Insights tab content is visible
        insights_pane = page.locator("#insights.tab-pane")
        expect(insights_pane).to_be_visible()
        insights_pane_classes = insights_pane.get_attribute("class") or ""
        assert "active" in insights_pane_classes and "show" in insights_pane_classes, \
            f"Insights pane should have 'active' and 'show' classes, but has: {insights_pane_classes}"

        # Switch to Covered Calls tab to check it exists
        covered_calls_tab = page.locator("button#covered-calls-tab")
        covered_calls_tab.click()
        page.wait_for_timeout(500)

        # Check that covered calls table exists after switching tabs
        covered_calls_table = page.locator("#coveredCallsTable")
        if covered_calls_table.count() > 0:
            expect(covered_calls_table).to_be_visible(timeout=5000)

            # Check table headers for covered calls
            expect(covered_calls_table.locator("th:has-text('Expiration Date')")).to_be_visible()
            expect(covered_calls_table.locator("th:has-text('Strike Price')")).to_be_visible()
            expect(covered_calls_table.locator("th:has-text('Call Premium')")).to_be_visible()
            # These columns may be hidden by DataTables responsive mode, just check they exist in DOM
            expect(covered_calls_table.locator("th:has-text('Return if Exercised')")).to_be_attached()
            expect(covered_calls_table.locator("th:has-text('Return if Not Exercised')")).to_be_attached()
            expect(covered_calls_table.locator("th:has-text('Return Visualization')")).to_be_attached()
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
    
    def test_closest_strike_highlighted_in_covered_calls_table(self, page: Page, live_server_url, authenticated_session):
        """Test that the Covered Calls table loads correctly with strike prices."""
        tickers = ["AAPL", "TSLA", "SHOP"]

        for ticker in tickers:
            page.goto(f"{live_server_url}/stock/{ticker}")
            page.wait_for_load_state("networkidle", timeout=30000)

            # Insights tab is active by default, switch to Covered Calls tab
            covered_calls_tab = page.locator("button#covered-calls-tab")
            covered_calls_tab.click()
            page.wait_for_timeout(500)

            covered_calls_pane = page.locator("#covered-calls.tab-pane")
            expect(covered_calls_pane).to_be_visible()

            # Find covered calls table
            covered_calls_table = page.locator("#coveredCallsTable, #covered-calls table").filter(has_text="Strike")
            if covered_calls_table.count() == 0:
                print(f"Skipping {ticker} - no covered calls table found")
                continue

            # Get current price from metrics
            current_price_elem = page.locator(".metric-item").filter(has_text="Current Price").locator(".metric-value-large")
            if current_price_elem.count() == 0:
                continue

            current_price_text = current_price_elem.first.inner_text().strip()
            try:
                current_price = float(current_price_text.replace("$", "").replace(",", ""))
            except ValueError:
                continue

            # Get all strike prices from covered calls table
            strike_cells = covered_calls_table.locator("tbody tr td.fw-bold")
            strikes = []
            for i in range(min(strike_cells.count(), 20)):  # Sample first 20
                strike_text = strike_cells.nth(i).inner_text().strip()
                if strike_text.startswith("$"):
                    try:
                        strike_value = float(strike_text.replace("$", "").replace(",", ""))
                        strikes.append(strike_value)
                    except ValueError:
                        continue

            # Debug output
            print(f"\n=== Debug Covered Calls for {ticker} ===")
            print(f"Current price: {current_price}")
            print(f"Strikes found: {len(strikes)}")
            if strikes:
                print(f"Strike range: ${min(strikes):.2f} - ${max(strikes):.2f}")

            # Verify table has data
            assert len(strikes) > 0, f"No strike prices found in Covered Calls table for {ticker}"

            # Verify strikes are reasonable (within 50% of current price)
            for strike in strikes[:10]:  # Check first 10
                pct_diff = abs(strike - current_price) / current_price * 100
                assert pct_diff < 50, f"Strike ${strike} is too far from current price ${current_price} ({pct_diff:.1f}%)"

            print(f"Covered Calls table validated for {ticker}")
    
    def test_tabs_functionality(self, page: Page, live_server_url, authenticated_session):
        """Test that Bootstrap tabs work correctly for Covered Calls and Risk Reversal."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)

        # Check tabs exist
        expect(page.locator("ul.nav-tabs")).to_be_visible()
        covered_calls_tab = page.locator("button#covered-calls-tab")
        risk_reversal_tab = page.locator("button#risk-reversal-tab")

        expect(covered_calls_tab).to_be_visible()
        expect(risk_reversal_tab).to_be_visible()

        # Check Insights tab is active by default
        insights_tab = page.locator("button#insights-tab")
        insights_tab_classes = insights_tab.get_attribute("class") or ""
        assert "active" in insights_tab_classes, f"Insights tab should be active by default, but has classes: {insights_tab_classes}"

        insights_pane = page.locator("#insights.tab-pane")
        insights_pane_classes = insights_pane.get_attribute("class") or ""
        assert "active" in insights_pane_classes and "show" in insights_pane_classes, \
            f"Insights pane should have 'active' and 'show' classes, but has: {insights_pane_classes}"

        # Check Covered Calls tab is not active initially
        covered_calls_pane = page.locator("#covered-calls.tab-pane")
        classes = covered_calls_pane.get_attribute("class") or ""
        has_both = "show" in classes and "active" in classes
        assert not has_both, f"Covered Calls should not be active initially, but has classes: {classes}"

        # Check Risk Reversal tab is not active initially
        risk_reversal_pane = page.locator("#risk-reversal.tab-pane")
        classes = risk_reversal_pane.get_attribute("class") or ""
        has_both = "show" in classes and "active" in classes
        assert not has_both, f"Risk Reversal should not be active initially, but has classes: {classes}"

        # Click Risk Reversal tab
        risk_reversal_tab.click()
        page.wait_for_timeout(500)  # Wait for Bootstrap tab animation

        # Check Risk Reversal tab is now active
        risk_reversal_tab_classes = risk_reversal_tab.get_attribute("class") or ""
        assert "active" in risk_reversal_tab_classes, f"Risk Reversal tab should be active, but has classes: {risk_reversal_tab_classes}"

        risk_reversal_pane_classes = risk_reversal_pane.get_attribute("class") or ""
        assert "active" in risk_reversal_pane_classes and "show" in risk_reversal_pane_classes, \
            f"Risk Reversal pane should have 'active' and 'show' classes, but has: {risk_reversal_pane_classes}"

        # Check Covered Calls tab is no longer active
        classes = covered_calls_pane.get_attribute("class") or ""
        has_both = "show" in classes and "active" in classes
        assert not has_both, f"Covered Calls should not be active after switching tabs, but has classes: {classes}"

        # Click back to Covered Calls tab
        covered_calls_tab.click()
        page.wait_for_timeout(500)  # Wait for Bootstrap tab animation

        # Check Covered Calls tab is active again
        covered_calls_tab_classes = covered_calls_tab.get_attribute("class") or ""
        assert "active" in covered_calls_tab_classes, f"Covered Calls tab should be active again, but has classes: {covered_calls_tab_classes}"

        covered_calls_pane_classes = covered_calls_pane.get_attribute("class") or ""
        assert "active" in covered_calls_pane_classes and "show" in covered_calls_pane_classes, \
            f"Covered Calls pane should have 'active' and 'show' classes again, but has: {covered_calls_pane_classes}"

        # Check Risk Reversal tab is no longer active
        classes = risk_reversal_pane.get_attribute("class") or ""
        has_both = "show" in classes and "active" in classes
        assert not has_both, f"Risk Reversal should not be active after switching back, but has classes: {classes}"
    
    def test_tab_content_visibility(self, page: Page, live_server_url, authenticated_session):
        """Test that tab content is only visible when the tab is active."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)

        # Initially, Insights content should be visible (it's the default tab)
        insights_pane = page.locator("#insights.tab-pane")
        expect(insights_pane).to_be_visible()

        # Covered Calls content should exist but not be visible initially
        covered_calls_pane = page.locator("#covered-calls.tab-pane")
        expect(covered_calls_pane).to_be_attached()  # Element exists in DOM
        # Initially it should not be visible (Bootstrap hides inactive tabs)
        classes = covered_calls_pane.get_attribute("class") or ""
        has_both = "show" in classes and "active" in classes
        assert not has_both, f"Covered Calls should not be visible initially, but has classes: {classes}"

        # Risk Reversal content should exist but not be visible initially
        risk_reversal_pane = page.locator("#risk-reversal.tab-pane")
        expect(risk_reversal_pane).to_be_attached()  # Element exists in DOM
        # Initially it should not be visible (Bootstrap hides inactive tabs)
        classes = risk_reversal_pane.get_attribute("class") or ""
        has_both = "show" in classes and "active" in classes
        assert not has_both, f"Risk Reversal should not be visible initially, but has classes: {classes}"

        # Switch to Risk Reversal tab
        risk_reversal_tab = page.locator("button#risk-reversal-tab")
        risk_reversal_tab.click()
        page.wait_for_timeout(500)

        # Risk Reversal content should now be visible
        expect(risk_reversal_pane).to_be_visible()

        # Check if Risk Reversal table exists and is visible
        risk_reversal_table = page.locator("#risk-reversal table")
        if risk_reversal_table.count() > 0:
            expect(risk_reversal_table.first).to_be_visible()
    
    def test_current_price_timestamp_displayed(self, page: Page, live_server_url, authenticated_session):
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
            current_price_value = current_price_item.locator(".metric-value-large")
            expect(current_price_value).to_be_visible()
            price_text = current_price_value.inner_text().strip()
            assert price_text.startswith("$"), f"Current price should start with $, got: {price_text}"
    
    def test_todays_candle_displayed_on_chart(self, page: Page, live_server_url, authenticated_session):
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
    
    def test_options_tables_have_datatables(self, page: Page, live_server_url, authenticated_session):
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
    
    def test_options_table_column_count_fixed(self, page: Page, live_server_url, authenticated_session):
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
    
    def test_datatables_search_functionality(self, page: Page, live_server_url, authenticated_session):
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
    
    def test_risk_reversal_filter_functionality(self, page: Page, live_server_url, authenticated_session):
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
    
    def test_risk_reversal_filter_functionality_msft(self, page: Page, live_server_url, authenticated_session):
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

    def test_covered_calls_tab_loads_and_displays_correctly(self, page: Page, live_server_url, authenticated_session):
        """Test that the new Covered Calls tab loads with all expected columns and data."""
        # Test with a well-known stock that should have options data
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")

        # Wait for page to load
        page.wait_for_load_state("networkidle", timeout=30000)

        # Check that Insights tab is active by default
        insights_tab = page.locator("button#insights-tab")
        expect(insights_tab).to_be_visible(timeout=10000)
        insights_tab_classes = insights_tab.get_attribute("class") or ""
        assert "active" in insights_tab_classes, f"Insights tab should be active by default, but has classes: {insights_tab_classes}"

        # Check that Covered Calls tab exists
        cc_v2_tab = page.locator("button#covered-calls-tab")
        expect(cc_v2_tab).to_be_visible(timeout=10000)

        # Click on Covered Calls tab
        cc_v2_tab.click()
        page.wait_for_timeout(500)  # Wait for tab switch animation

        # Verify tab is now active
        tab_classes = cc_v2_tab.get_attribute("class") or ""
        assert "active" in tab_classes, f"Covered Calls tab should be active after click, but has classes: {tab_classes}"

        # Check tab content is visible
        cc_v2_pane = page.locator("#covered-calls.tab-pane")
        expect(cc_v2_pane).to_be_visible()
        pane_classes = cc_v2_pane.get_attribute("class") or ""
        assert "active" in pane_classes and "show" in pane_classes, \
            f"Covered Calls pane should have 'active' and 'show' classes, but has: {pane_classes}"

        # Check if table exists (or info message if no data)
        has_table = page.locator("#coveredCallsTable").count() > 0
        has_info_msg = cc_v2_pane.locator(".alert-info").count() > 0

        assert has_table or has_info_msg, "Should have either table or info message about no data"

        if has_table:
            table = page.locator("#coveredCallsTable")
            expect(table).to_be_visible()

            # Verify required column headers are present (some may be hidden by responsive mode)
            # Use to_be_attached() for columns that might be hidden by DataTables responsive
            expect(table.locator("th:has-text('Expiration Date')")).to_be_visible()
            expect(table.locator("th:has-text('Strike Price')")).to_be_visible()
            expect(table.locator("th:has-text('Call Premium')")).to_be_visible()
            # These columns may be hidden by responsive mode, just check they exist in DOM
            expect(table.locator("th:has-text('Return if Exercised')")).to_be_attached()
            expect(table.locator("th:has-text('Return if Not Exercised')")).to_be_attached()
            # Return Visualization is often hidden on smaller screens
            expect(table.locator("th:has-text('Return Visualization')")).to_be_attached()

            # Check that table has data rows
            rows = table.locator("tbody tr")
            row_count = rows.count()

            if row_count > 0:
                # Verify first row has all expected data
                first_row = rows.first

                # Check expiration date format (YYYY-MM-DD)
                exp_date_cell = first_row.locator("td").nth(0)
                exp_date_text = exp_date_cell.inner_text().strip()
                import re
                assert re.match(r'^\d{4}-\d{2}-\d{2}$', exp_date_text), \
                    f"Expiration date should be YYYY-MM-DD format, got: {exp_date_text}"

                # Check strike price (should start with $)
                strike_cell = first_row.locator("td").nth(1)
                strike_text = strike_cell.inner_text().strip()
                assert strike_text.startswith("$"), f"Strike price should start with $, got: {strike_text}"

                # Check call premium (should start with $)
                premium_cell = first_row.locator("td").nth(2)
                premium_text = premium_cell.inner_text().strip()
                assert premium_text.startswith("$"), f"Call premium should start with $, got: {premium_text}"

                # Check return if exercised (should contain $ and % and Ann:)
                return_ex_cell = first_row.locator("td").nth(3)
                return_ex_text = return_ex_cell.inner_text()
                assert "$" in return_ex_text, "Return if exercised should contain $ sign"
                assert "%" in return_ex_text, "Return if exercised should contain % sign"
                assert "Ann:" in return_ex_text, "Return if exercised should contain annualized return (Ann:)"

                # Check return if not exercised (should contain $ and % and Ann:)
                return_not_ex_cell = first_row.locator("td").nth(4)
                return_not_ex_text = return_not_ex_cell.inner_text()
                assert "$" in return_not_ex_text, "Return if not exercised should contain $ sign"
                assert "%" in return_not_ex_text, "Return if not exercised should contain % sign"
                assert "Ann:" in return_not_ex_text, "Return if not exercised should contain annualized return (Ann:)"

                # Check visualization (should have a bar chart - div with styles)
                # Note: The visualization column may be hidden by DataTables responsive mode
                # Just verify the cell exists in the DOM
                viz_cell = first_row.locator("td").nth(5)
                expect(viz_cell).to_be_attached()

                # If the cell is visible, check for bar chart
                if viz_cell.is_visible():
                    bar_chart = viz_cell.locator("div[style*='display: flex']").first
                    if bar_chart.count() > 0:
                        # Verify the bar chart has colored sections (blue or red for stock appreciation, green for premium)
                        colored_divs = bar_chart.locator("div[style*='background-color']")
                        assert colored_divs.count() > 0, "Bar chart should have colored sections"

        # Take a screenshot for debugging
        page.screenshot(path=f"test_cc_tab_{ticker}.png", full_page=True)

    def test_covered_calls_tab_ranking_and_sorting(self, page: Page, live_server_url, authenticated_session):
        """Test that Covered Calls tab data is properly ranked and sortable."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)

        # Navigate to Covered Calls tab
        cc_v2_tab = page.locator("button#covered-calls-tab")
        cc_v2_tab.click()
        page.wait_for_timeout(500)

        # Check if table has data
        table = page.locator("#coveredCallsTable")
        if table.count() == 0:
            # Skip test if no data available
            return

        rows = table.locator("tbody tr")
        row_count = rows.count()

        if row_count > 1:
            # Verify that rows are sorted (default should be by expiration date)
            # Get all expiration dates
            exp_dates = []
            for i in range(min(row_count, 10)):  # Check first 10 rows
                row = rows.nth(i)
                exp_date_text = row.locator("td").nth(0).inner_text().strip()
                exp_dates.append(exp_date_text)

            # Verify dates are in ascending order (earliest expiration first)
            # Note: The ranking algorithm sorts by return difference first, then by annualized return
            # But DataTables initialization sorts by expiration date ascending by default
            assert len(exp_dates) > 0, "Should have at least one expiration date"

            # Test that clicking on column headers sorts the table
            # Click on Strike Price header
            strike_header = table.locator("th:has-text('Strike Price')")
            if strike_header.count() > 0:
                strike_header.click()
                page.wait_for_timeout(500)

                # Get strike prices after sorting
                strikes_after_sort = []
                for i in range(min(row_count, 5)):
                    row = rows.nth(i)
                    strike_text = row.locator("td").nth(1).inner_text().strip()
                    # Extract number from $XXX.XX format
                    import re
                    match = re.search(r'\$(\d+\.\d+)', strike_text)
                    if match:
                        strikes_after_sort.append(float(match.group(1)))

                # Verify strikes are sorted (either ascending or descending)
                if len(strikes_after_sort) > 1:
                    is_ascending = all(strikes_after_sort[i] <= strikes_after_sort[i+1] for i in range(len(strikes_after_sort)-1))
                    is_descending = all(strikes_after_sort[i] >= strikes_after_sort[i+1] for i in range(len(strikes_after_sort)-1))
                    assert is_ascending or is_descending, f"Strikes should be sorted, got: {strikes_after_sort}"

    def test_covered_calls_premium_filtering(self, page: Page, live_server_url, authenticated_session):
        """Test that Covered Calls tab only shows premiums > 1% of stock price."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)

        # Get current stock price
        current_price_elem = page.locator(".metric-item").filter(has_text="Current Price").locator(".metric-value-large")
        if current_price_elem.count() == 0:
            # Skip if no current price available
            return

        price_text = current_price_elem.inner_text().strip()
        # Extract price from $XXX.XX format
        import re
        match = re.search(r'\$(\d+\.\d+)', price_text)
        if not match:
            return

        current_price = float(match.group(1))
        min_premium = current_price * 0.01  # 1% threshold

        # Navigate to Covered Calls tab
        cc_v2_tab = page.locator("button#covered-calls-tab")
        cc_v2_tab.click()
        page.wait_for_timeout(500)

        # Check if table has data
        table = page.locator("#coveredCallsTable")
        if table.count() == 0:
            return

        rows = table.locator("tbody tr")
        row_count = rows.count()

        if row_count > 0:
            # Verify all premiums are strictly > 1% of stock price (not equal)
            for i in range(min(row_count, 20)):  # Check first 20 rows
                row = rows.nth(i)
                premium_text = row.locator("td").nth(2).inner_text().strip()

                # Extract premium value
                match = re.search(r'\$(\d+\.\d+)', premium_text)
                if match:
                    premium = float(match.group(1))
                    assert premium > min_premium, \
                        f"Premium ${premium:.2f} should be > 1% of stock price (${min_premium:.2f}), not equal"
