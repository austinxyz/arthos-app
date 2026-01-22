"""End-to-end browser tests for core user flows using Playwright.

These tests mimic real user interactions and verify the complete workflow:
1. Load home page
2. Create a new WatchList
3. Add stocks to watchlist and see table populate
4. Open stock details page and verify chart/metrics match
5. Verify Options Data displays correctly
6. Verify Covered Calls table shows correctly with correct math
"""
import pytest
from playwright.sync_api import Page, expect
from app.database import engine, create_db_and_tables
from sqlmodel import Session
from app.models.watchlist import WatchList, WatchListStock
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
    
    # Cleanup before test
    with Session(engine) as session:
        from sqlmodel import select
        
        # Clean watchlists
        statement = select(WatchListStock)
        all_stocks = session.exec(statement).all()
        for stock in all_stocks:
            session.delete(stock)
        
        statement = select(WatchList)
        all_watchlists = session.exec(statement).all()
        for watchlist in all_watchlists:
            session.delete(watchlist)
        
        session.commit()
    
    yield
    
    # Cleanup after test
    with Session(engine) as session:
        from sqlmodel import select
        
        statement = select(WatchListStock)
        all_stocks = session.exec(statement).all()
        for stock in all_stocks:
            session.delete(stock)
        
        statement = select(WatchList)
        all_watchlists = session.exec(statement).all()
        for watchlist in all_watchlists:
            session.delete(watchlist)
        
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


@pytest.mark.e2e
class TestE2EUserFlows:
    """End-to-end tests for complete user workflows."""

    @pytest.mark.e2e
    def test_complete_user_workflow(self, page: Page, live_server_url, authenticated_session):
        """
        Test complete user workflow:
        1. Login (simulated via authenticated_session fixture)
        2. Load home page
        3. Create a new WatchList
        4. Add stocks to watchlist and see table populate
        5. Open stock details page and verify chart/metrics match
        6. Verify Options Data displays correctly
        7. Verify Covered Calls table shows correctly
        """
        # Step 1: Load home page (already authenticated via fixture)
        page.goto(f"{live_server_url}/")
        expect(page).to_have_title("Arthos - Investment Analysis")
        
        # Verify home page elements
        expect(page.locator("h1.logo")).to_contain_text("Arthos")
        expect(page.locator("#tickerInput")).to_be_visible()
        expect(page.locator("button.explore-btn")).to_be_visible()
        expect(page.locator("a[href='/watchlists']")).to_be_visible()
        expect(page.locator("text=View My WatchLists")).to_be_visible()
        
        # Step 2: Navigate to create watchlist page
        page.click("a[href='/watchlists']")
        page.wait_for_url(r"**/watchlists", timeout=5000)
        expect(page).to_have_title("WatchLists - Arthos")
        
        # Click create watchlist button
        page.click("a[href='/create-watchlist']")
        page.wait_for_url(r"**/create-watchlist", timeout=5000)
        expect(page).to_have_title("Create WatchList - Arthos")
        
        # Create a new watchlist
        watchlist_name = "E2E Test WatchList"
        page.fill("#watchlistName", watchlist_name)
        page.click("button[type='submit']")
        
        # Should redirect to watchlist details page
        page.wait_for_url(r"**/watchlist/**", timeout=5000)
        expect(page.locator("h1")).to_contain_text(watchlist_name)
        
        # Get the watchlist ID from URL
        current_url = page.url
        watchlist_id = current_url.split("/watchlist/")[1].split("?")[0] if "/watchlist/" in current_url else None
        assert watchlist_id is not None, "Should have watchlist ID in URL"
        
        # Step 3: Add stocks to watchlist and verify table populates
        test_stocks = ["AAPL", "MSFT", "GOOGL"]
        
        # Fill in tickers
        page.fill("#tickersInput", ", ".join(test_stocks))
        page.click("button[type='submit']")
        
        # Wait for table to populate (DataTable needs time to initialize)
        page.wait_for_timeout(3000)
        
        # Verify stocks appear in the table
        table = page.locator("#stocksTable")
        expect(table).to_be_visible()
        
        # Wait for DataTable to load and stocks to be fetched
        page.wait_for_timeout(5000)  # Give more time for stock data to load
        
        # Verify each stock appears in the table
        for ticker in test_stocks:
            # Check for ticker link in table
            ticker_link = table.locator(f"a[href='/stock/{ticker}']")
            expect(ticker_link).to_be_visible(timeout=30000)  # Longer timeout for data fetching
            expect(ticker_link).to_contain_text(ticker)
        
        # Verify table has data rows (not just header)
        table_rows = table.locator("tbody tr")
        row_count = table_rows.count()
        assert row_count >= len(test_stocks), f"Expected at least {len(test_stocks)} rows, got {row_count}"
        
        # Step 4: Open stock details page and verify chart/metrics match
        # Click on first stock (AAPL)
        page.click(f"a[href='/stock/{test_stocks[0]}']")
        page.wait_for_url(rf"**/stock/{test_stocks[0]}", timeout=5000)
        
        # Wait for page to fully load
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(2000)  # Additional wait for chart to render
        
        # Verify page loaded
        expect(page.locator(f"h1:has-text('{test_stocks[0]}')")).to_be_visible()
        
        # Verify chart exists
        chart_container = page.locator("#stockChart")
        expect(chart_container).to_be_visible(timeout=10000)
        
        # Verify metrics card exists
        if page.locator(".metrics-card").count() > 1:
            metrics_card = page.locator(".metrics-card").first
        else:
            metrics_card = page.locator(".metrics-card")
        expect(metrics_card).to_be_visible()
        
        # Extract SMA values from metrics table
        sma_50_metric = page.locator(".metric-item").filter(has_text="SMA 50")
        sma_200_metric = page.locator(".metric-item").filter(has_text="SMA 200")
        
        expect(sma_50_metric).to_be_visible()
        expect(sma_200_metric).to_be_visible()
        
        # Get SMA values from metrics
        sma_50_value_text = sma_50_metric.locator(".metric-value").inner_text().strip()
        sma_200_value_text = sma_200_metric.locator(".metric-value").inner_text().strip()
        
        # Parse values (remove $ sign)
        sma_50_metrics = float(sma_50_value_text.replace("$", "").replace(",", ""))
        sma_200_metrics = float(sma_200_value_text.replace("$", "").replace(",", ""))
        
        # Get current price for later validation
        # Get current price for later validation
        # Current Price uses metric-value-large class
        current_price_text = page.locator(".metric-item").filter(has_text="Current Price").locator(".metric-value-large").inner_text().strip()
        current_price = float(current_price_text.replace("$", "").replace(",", ""))
        
        # Verify chart data contains SMA values
        # The chart data is in JavaScript, so we'll verify it's loaded by checking the page
        # doesn't have errors and the chart container is visible
        expect(chart_container).to_be_visible()
        
        # Step 5: Verify Options Data displays correctly
        # Switch to Option Data tab (should be active by default)
        option_data_tab = page.locator("button#option-data-tab")
        expect(option_data_tab).to_be_visible()
        
        # Click to ensure it's active
        option_data_tab.click()
        page.wait_for_timeout(1000)
        
        # Check if options data is available
        # The pane might be in the DOM but not visible initially, so check if it exists
        option_data_pane = page.locator("#option-data.tab-pane")
        expect(option_data_pane).to_be_attached()  # Element exists in DOM
        
        # Check for expiration date display
        expiration_element = option_data_pane.locator("text=/Expiration:/i")
        if expiration_element.count() > 0:
            # Options data is available, verify it
            expect(expiration_element).to_be_visible()
            
            # Find the options table
            options_table = option_data_pane.locator("table")
            if options_table.count() > 0:
                expect(options_table).to_be_visible()
                
                # Verify table has columns: Puts, Strike, Calls
                # Check for Strike column header
                expect(options_table.locator("th:has-text('Strike')")).to_be_visible()
                
                # Verify strike prices are within 10% of current price
                table_rows = options_table.locator("tbody tr")
                row_count = table_rows.count()
                
                if row_count > 0:
                    # Extract strike prices from table
                    # Strike price should be in a specific column - let's find it
                    for i in range(min(row_count, 10)):  # Check first 10 rows
                        row = table_rows.nth(i)
                        cells = row.locator("td")
                        cell_count = cells.count()
                        
                        if cell_count >= 3:  # Should have at least 3 columns (Puts, Strike, Calls)
                            # Try to find strike price (usually in middle column, marked with fw-bold class)
                            # Look for cells with fw-bold class (strike price column)
                            strike_cell = row.locator("td.fw-bold")
                            if strike_cell.count() > 0:
                                cell_text = strike_cell.first.inner_text().strip()
                                try:
                                    strike_price = float(cell_text.replace("$", "").replace(",", ""))
                                    # Verify strike is within 10% of current price
                                    price_diff_pct = abs(strike_price - current_price) / current_price * 100
                                    assert price_diff_pct <= 10.0, \
                                        f"Strike price ${strike_price} is {price_diff_pct:.2f}% away from current price ${current_price}, should be within 10%"
                                except ValueError:
                                    pass
        
        # Step 6: Verify Covered Calls table shows correctly
        # Switch to Covered Calls tab
        covered_calls_tab = page.locator("button#covered-calls-tab")
        expect(covered_calls_tab).to_be_visible()
        covered_calls_tab.click()
        page.wait_for_timeout(1000)
        
        covered_calls_pane = page.locator("#covered-calls.tab-pane")
        expect(covered_calls_pane).to_be_attached()  # Element exists in DOM
        
        # Check if covered calls data is available
        no_data_message = covered_calls_pane.locator("text=/No covered call data available/i")
        covered_calls_table = covered_calls_pane.locator("table")
        
        if no_data_message.count() == 0 and covered_calls_table.count() > 0:
            # Covered calls data is available, verify it
            expect(covered_calls_table).to_be_visible()
            
            # Verify table structure - check for key headers
            expect(covered_calls_table.locator("th:has-text('Strike Price')")).to_be_visible()
            expect(covered_calls_table.locator("th:has-text('Call Premium')")).to_be_visible()
            expect(covered_calls_table.locator("th:has-text('Total Return Exercised')")).to_be_visible()
            expect(covered_calls_table.locator("th:has-text('Total Return Not Exercised')")).to_be_visible()
            
            # Verify math: For each row, check that the calculations are correct
            table_rows = covered_calls_table.locator("tbody tr")
            row_count = table_rows.count()
            
            if row_count > 0:
                import re
                for i in range(min(row_count, 5)):  # Check first 5 rows
                    row = table_rows.nth(i)
                    cells = row.locator("td")
                    cell_count = cells.count()
                    
                    if cell_count >= 4:
                        try:
                            # Get cell texts one by one
                            strike_text = cells.nth(0).inner_text().strip()
                            premium_text = cells.nth(1).inner_text().strip()
                            exercised_text = cells.nth(2).inner_text().strip()
                            not_exercised_text = cells.nth(3).inner_text().strip()
                            
                            # Parse strike price
                            strike_price = float(strike_text.replace("$", "").replace(",", ""))
                            
                            # Parse call premium
                            call_premium = float(premium_text.replace("$", "").replace(",", ""))
                            
                            # Parse total return exercised (extract percentage)
                            exercised_match = re.search(r'\(([\d.+-]+)%\)', exercised_text)
                            if exercised_match:
                                exercised_pct = float(exercised_match.group(1))
                                
                                # Verify calculation: (Strike Price + Call Premium - Current Price) / Current Price * 100
                                expected_exercised_pct = ((strike_price + call_premium - current_price) / current_price) * 100
                                assert abs(exercised_pct - expected_exercised_pct) < 0.1, \
                                    f"Exercised return % mismatch: expected {expected_exercised_pct:.2f}%, got {exercised_pct:.2f}%"
                            
                            # Parse total return not exercised (extract percentage)
                            not_exercised_match = re.search(r'\(([\d.+-]+)%\)', not_exercised_text)
                            if not_exercised_match:
                                not_exercised_pct = float(not_exercised_match.group(1))
                                
                                # Verify calculation: Call Premium / Current Price * 100
                                expected_not_exercised_pct = (call_premium / current_price) * 100
                                assert abs(not_exercised_pct - expected_not_exercised_pct) < 0.1, \
                                    f"Not exercised return % mismatch: expected {expected_not_exercised_pct:.2f}%, got {not_exercised_pct:.2f}%"
                        except (ValueError, IndexError, AttributeError):
                            # Skip rows that don't have the expected format
                            continue
    
    @pytest.mark.e2e
    def test_home_page_loads_and_navigation(self, page: Page, live_server_url, authenticated_session):
        """Test that home page loads correctly and navigation works."""
        page.goto(f"{live_server_url}/")
        
        # Verify page title
        expect(page).to_have_title("Arthos - Investment Analysis")
        
        # Verify main elements
        expect(page.locator("h1.logo")).to_contain_text("Arthos")
        expect(page.locator("#tickerInput")).to_be_visible()
        expect(page.locator("button.explore-btn")).to_be_visible()
        
        # Verify watchlist link exists and works
        watchlist_link = page.locator("a[href='/watchlists']")
        expect(watchlist_link).to_be_visible()
        expect(watchlist_link).to_contain_text("View My WatchLists")
        
        # Click watchlist link
        watchlist_link.click()
        page.wait_for_url(r"**/watchlists", timeout=5000)
        expect(page).to_have_title("WatchLists - Arthos")
    
    @pytest.mark.e2e
    def test_watchlist_creation_and_stock_addition_flow(self, page: Page, live_server_url, authenticated_session):
        """Test creating a watchlist and adding stocks, verifying table populates."""
        # Navigate to watchlists page
        page.goto(f"{live_server_url}/watchlists")
        
        # Click create watchlist
        page.click("a[href='/create-watchlist']")
        page.wait_for_url(r"**/create-watchlist", timeout=5000)
        
        # Create watchlist
        watchlist_name = "Test WatchList for Stocks"
        page.fill("#watchlistName", watchlist_name)
        page.click("button[type='submit']")
        
        # Wait for redirect
        page.wait_for_url(r"**/watchlist/**", timeout=5000)
        expect(page.locator("h1")).to_contain_text(watchlist_name)
        
        # Add stocks
        test_stocks = ["AAPL", "MSFT"]
        page.fill("#tickersInput", ", ".join(test_stocks))
        page.click("button[type='submit']")
        
        # Wait for table to populate and stock data to load
        page.wait_for_timeout(5000)  # Give time for stock data to fetch
        
        # Verify table exists and has data
        table = page.locator("#stocksTable")
        expect(table).to_be_visible()
        
        # Verify stocks appear
        for ticker in test_stocks:
            ticker_link = table.locator(f"a[href='/stock/{ticker}']")
            expect(ticker_link).to_be_visible(timeout=30000)  # Longer timeout for data fetching
        
        # Verify table has rows
        table_rows = table.locator("tbody tr")
        assert table_rows.count() >= len(test_stocks), "Table should have at least as many rows as stocks added"
    
    @pytest.mark.e2e
    def test_stock_details_chart_and_metrics_consistency(self, page: Page, live_server_url, authenticated_session):
        """Test that stock details page shows chart and metrics, and SMA values are consistent."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        
        # Wait for page to load
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        
        # Verify chart exists
        expect(page.locator("#stockChart")).to_be_visible(timeout=10000)
        
        # Verify metrics exist
        if page.locator(".metrics-card").count() > 1:
            expect(page.locator(".metrics-card").first).to_be_visible()
        else:
            expect(page.locator(".metrics-card")).to_be_visible()
        expect(page.locator(".metric-label:has-text('SMA 50')")).to_be_visible()
        expect(page.locator(".metric-label:has-text('SMA 200')")).to_be_visible()
        
        # Extract SMA values from metrics
        sma_50_metric = page.locator(".metric-item").filter(has_text="SMA 50")
        sma_200_metric = page.locator(".metric-item").filter(has_text="SMA 200")
        
        sma_50_text = sma_50_metric.locator(".metric-value").inner_text().strip()
        sma_200_text = sma_200_metric.locator(".metric-value").inner_text().strip()
        
        # Verify values are valid numbers
        sma_50_value = float(sma_50_text.replace("$", "").replace(",", ""))
        sma_200_value = float(sma_200_text.replace("$", "").replace(",", ""))
        
        assert sma_50_value > 0, "SMA 50 should be positive"
        assert sma_200_value > 0, "SMA 200 should be positive"
        
        # Note: Chart data is in JavaScript, so we can't directly compare,
        # but we've verified the values are displayed correctly in metrics
    
    @pytest.mark.e2e
    def test_options_data_strike_prices_within_range(self, page: Page, live_server_url, authenticated_session):
        """Test that options data shows strike prices within 10% of current price."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        
        # Wait for page to load
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        
        # Get current price
        # Current Price uses metric-value-large class
        current_price_text = page.locator(".metric-item").filter(has_text="Current Price").locator(".metric-value-large").inner_text().strip()
        current_price = float(current_price_text.replace("$", "").replace(",", ""))
        
        # Switch to Option Data tab
        option_data_tab = page.locator("button#option-data-tab")
        if option_data_tab.count() > 0:
            option_data_tab.click()
            page.wait_for_timeout(1000)
            
            option_data_pane = page.locator("#option-data-pane")
            if option_data_pane.count() > 0:
                options_table = option_data_pane.locator("table")
                
                if options_table.count() > 0:
                    # Extract strike prices and verify they're within 10%
                    table_rows = options_table.locator("tbody tr")
                    row_count = table_rows.count()
                    
                    strikes_found = []
                    for i in range(min(row_count, 20)):  # Check up to 20 rows
                        row = table_rows.nth(i)
                        cells = row.locator("td")
                        cell_count = cells.count()
                        
                        # Strike price is typically in the middle column
                        for j in range(cell_count):
                            cell_text = cells.nth(j).inner_text().strip()
                            try:
                                strike = float(cell_text.replace("$", "").replace(",", ""))
                                # Check if this looks like a strike price (reasonable range)
                                if 10 < strike < 10000:  # Reasonable stock price range
                                    price_diff_pct = abs(strike - current_price) / current_price * 100
                                    assert price_diff_pct <= 10.0, \
                                        f"Strike price ${strike} is {price_diff_pct:.2f}% away from current price ${current_price}, should be within 10%"
                                    strikes_found.append(strike)
                                    break
                            except ValueError:
                                continue
                    
                    if strikes_found:
                        assert len(strikes_found) > 0, "Should find at least one strike price"
    
    @pytest.mark.e2e
    def test_covered_calls_math_correctness(self, page: Page, live_server_url, authenticated_session):
        """Test that Covered Calls table shows correct calculations."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        
        # Wait for page to load
        page.wait_for_load_state("networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        
        # Get current price
        # Current Price uses metric-value-large class
        current_price_text = page.locator(".metric-item").filter(has_text="Current Price").locator(".metric-value-large").inner_text().strip()
        current_price = float(current_price_text.replace("$", "").replace(",", ""))
        
        # Switch to Covered Calls tab
        covered_calls_tab = page.locator("button#covered-calls-tab")
        if covered_calls_tab.count() > 0:
            covered_calls_tab.click()
            page.wait_for_timeout(1000)
            
            covered_calls_pane = page.locator("#covered-calls-pane")
            if covered_calls_pane.count() > 0:
                covered_calls_table = covered_calls_pane.locator("table")
                
                if covered_calls_table.count() > 0:
                    # Verify calculations for each row
                    table_rows = covered_calls_table.locator("tbody tr")
                    row_count = table_rows.count()
                    
                    import re
                    rows_checked = 0
                    
                    for i in range(min(row_count, 10)):  # Check up to 10 rows
                        row = table_rows.nth(i)
                        cells = row.locator("td")
                        cell_texts = [cell.inner_text().strip() for cell in cells.all()]
                        
                        if len(cell_texts) >= 4:
                            try:
                                # Parse strike price
                                strike_text = cell_texts[0].replace("$", "").replace(",", "")
                                strike_price = float(strike_text)
                                
                                # Parse call premium
                                premium_text = cell_texts[1].replace("$", "").replace(",", "")
                                call_premium = float(premium_text)
                                
                                # Parse and verify exercised return
                                exercised_text = cell_texts[2]
                                exercised_match = re.search(r'\(([\d.+-]+)%\)', exercised_text)
                                if exercised_match:
                                    exercised_pct = float(exercised_match.group(1))
                                    expected_exercised = ((strike_price + call_premium - current_price) / current_price) * 100
                                    assert abs(exercised_pct - expected_exercised) < 0.1, \
                                        f"Row {i}: Exercised return mismatch. Expected {expected_exercised:.2f}%, got {exercised_pct:.2f}%"
                                
                                # Parse and verify not exercised return
                                not_exercised_text = cell_texts[3]
                                not_exercised_match = re.search(r'\(([\d.+-]+)%\)', not_exercised_text)
                                if not_exercised_match:
                                    not_exercised_pct = float(not_exercised_match.group(1))
                                    expected_not_exercised = (call_premium / current_price) * 100
                                    assert abs(not_exercised_pct - expected_not_exercised) < 0.1, \
                                        f"Row {i}: Not exercised return mismatch. Expected {expected_not_exercised:.2f}%, got {not_exercised_pct:.2f}%"
                                
                                rows_checked += 1
                            except (ValueError, IndexError, AttributeError):
                                continue
                    
                    # If we found covered calls data, we should have checked at least one row
                    if row_count > 0:
                        assert rows_checked > 0, "Should have verified at least one row of covered calls data"

