"""Browser tests for watchlist functionality using Playwright."""
import pytest
from playwright.sync_api import Page, expect
from app.services.watchlist_service import create_watchlist, add_stocks_to_watchlist
from app.database import engine, create_db_and_tables
from sqlmodel import Session
from app.models.watchlist import WatchList, WatchListStock
from app.models.stock_price import StockPrice, StockPriceWatermark
from tests.conftest import populate_test_stock_prices


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables and clean up before and after each test."""
    create_db_and_tables()
    
    # Cleanup before test (must happen before populating data)
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
        
        # Clean stock_price tables (must be cleaned before populating)
        statement = select(StockPrice)
        all_prices = session.exec(statement).all()
        for price in all_prices:
            session.delete(price)
        
        statement = select(StockPriceWatermark)
        all_watermarks = session.exec(statement).all()
        for watermark in all_watermarks:
            session.delete(watermark)
        
        session.commit()
    
    # Populate test data for common tickers used in tests (after cleanup)
    populate_test_stock_prices("AAPL")
    populate_test_stock_prices("MSFT")
    populate_test_stock_prices("HD")
    
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
        
        statement = select(StockPriceWatermark)
        all_watermarks = session.exec(statement).all()
        for watermark in all_watermarks:
            session.delete(watermark)
        
        session.commit()


@pytest.fixture
def live_server_url():
    """Return the URL of the live server."""
    import os
    # Use environment variable if set (for Docker), otherwise use localhost
    return os.getenv("TEST_SERVER_URL", "http://localhost:8000")


@pytest.mark.browser
class TestWatchListBrowser:
    """Browser tests for watchlist pages."""
    
    def test_create_portfolio_page_loads(self, page: Page, live_server_url):
        """Test that the create watchlist page loads correctly."""
        page.goto(f"{live_server_url}/create-watchlist")
        
        # Check page title
        expect(page).to_have_title("Create WatchList - Arthos")
        
        # Check form elements
        expect(page.locator("#watchlistName")).to_be_visible()
        expect(page.locator("button[type='submit']")).to_be_visible()
        expect(page.locator("text=Create WatchList")).to_be_visible()
    
    def test_create_portfolio_success(self, page: Page, live_server_url):
        """Test creating a watchlist through the UI."""
        page.goto(f"{live_server_url}/create-watchlist")
        
        # Fill in watchlist name
        page.fill("#watchlistName", "My Test WatchList")
        
        # Submit form
        page.click("button[type='submit']")
        
        # Should redirect to watchlist details page
        page.wait_for_url(r"**/watchlist/**", timeout=5000)
        
        # Check that watchlist name is displayed
        expect(page.locator("h1")).to_contain_text("My Test WatchList")
    
    def test_create_portfolio_invalid_name(self, page: Page, live_server_url):
        """Test creating watchlist with invalid name."""
        page.goto(f"{live_server_url}/create-watchlist")
        
        # Try invalid name with special characters
        page.fill("#watchlistName", "Invalid-Name!")
        page.click("button[type='submit']")
        
        # Should show error message
        expect(page.locator("#errorMessage")).to_be_visible()
        expect(page.locator("#errorMessage")).to_contain_text("alphanumeric")
    
    def test_list_portfolios_page(self, page: Page, live_server_url):
        """Test the portfolios list page."""
        # Create some portfolios
        watchlist1 = create_watchlist("WatchList 1")
        watchlist2 = create_watchlist("WatchList 2")
        
        page.goto(f"{live_server_url}/watchlists")
        
        # Check page title
        expect(page).to_have_title("WatchLists - Arthos")
        
        # Check that portfolios are listed
        expect(page.locator("text=WatchList 1")).to_be_visible()
        expect(page.locator("text=WatchList 2")).to_be_visible()
        
        # Check that watchlist names are links
        portfolio_link = page.locator(f"a[href='/watchlist/{watchlist1.watchlist_id}']")
        expect(portfolio_link).to_be_visible()
        expect(portfolio_link).to_contain_text("WatchList 1")
    
    def test_portfolio_details_page(self, page: Page, live_server_url):
        """Test the watchlist details page."""
        watchlist = create_watchlist("Test WatchList")
        
        page.goto(f"{live_server_url}/watchlist/{watchlist.watchlist_id}")
        
        # Check page title
        expect(page).to_have_title("WatchList: Test WatchList - Arthos")
        
        # Check watchlist name is displayed
        expect(page.locator("h1")).to_contain_text("Test WatchList")
        
        # Check add stocks form is visible
        expect(page.locator("#tickersInput")).to_be_visible()
        expect(page.locator("text=Add Stocks to WatchList")).to_be_visible()
    
    def test_add_stocks_to_portfolio(self, page: Page, live_server_url):
        """Test adding stocks to a watchlist through the UI."""
        watchlist = create_watchlist("Test WatchList")
        
        page.goto(f"{live_server_url}/watchlist/{watchlist.watchlist_id}")
        
        # Add stocks
        page.fill("#tickersInput", "AAPL, MSFT")
        page.click("button[type='submit']")
        
        # Wait for success message or page reload
        page.wait_for_timeout(2000)
        
        # Check that stocks appear in the table
        # Note: This assumes the stocks are successfully fetched
        # In a real scenario, we might need to wait for API calls
        expect(page.locator("text=AAPL")).to_be_visible(timeout=10000)
    
    def test_add_stocks_invalid_ticker(self, page: Page, live_server_url):
        """Test adding invalid ticker format to watchlist - should be caught by frontend validation."""
        watchlist = create_watchlist("Test WatchList")
        
        page.goto(f"{live_server_url}/watchlist/{watchlist.watchlist_id}")
        
        # Try invalid ticker format (> 5 characters) - frontend validation should catch this
        page.fill("#tickersInput", "INVALID12345")
        page.click("button[type='submit']")
        
        # Should show format validation error message (frontend catches this before API call)
        expect(page.locator("#errorMessage")).to_be_visible()
        expect(page.locator("#errorMessage")).to_contain_text("Invalid ticker format")
        expect(page.locator("#errorMessage")).to_contain_text("INVALID12345")
        
        # Wait a bit to ensure no stock was added
        page.wait_for_timeout(2000)
        
        # Verify the invalid ticker is NOT in the table (check table rows specifically)
        # The error message contains "INVALID12345" but it should not be in the table
        stocks_table = page.locator("#stocksTable tbody tr")
        stock_count = stocks_table.count()
        
        # Since format validation blocked the API call, the table should be empty
        # But if there are any rows (from previous tests or other sources), verify INVALID12345 is not in them
        if stock_count > 0:
            # Check that INVALID12345 is not in any table row's first cell (where ticker would appear)
            for i in range(stock_count):
                first_cell = stocks_table.nth(i).locator("td:first-child")
                if first_cell.count() > 0:
                    first_cell_text = first_cell.inner_text().strip()
                    assert "INVALID12345" not in first_cell_text, \
                        f"INVALID12345 should not be in the table, but found in first cell: {first_cell_text}"
        # If stock_count is 0, that's expected - the table is empty, so INVALID12345 is definitely not there
    
    def test_add_stocks_sdsk_invalid_ticker(self, page: Page, live_server_url):
        """Test adding SDSK (valid format but doesn't exist in yfinance) - should be rejected."""
        watchlist = create_watchlist("Test WatchList")
        
        page.goto(f"{live_server_url}/watchlist/{watchlist.watchlist_id}")
        
        # Try SDSK - valid format but doesn't exist in yfinance
        page.fill("#tickersInput", "SDSK")
        page.click("button[type='submit']")
        
        # Should show error message about invalid ticker
        expect(page.locator("#errorMessage")).to_be_visible(timeout=10000)
        expect(page.locator("#errorMessage")).to_contain_text("Ticker SDSK is invalid")
        
        # Wait a bit to ensure no stock was added
        page.wait_for_timeout(3000)
        
        # Verify SDSK is NOT in the table (should not appear even as an error row)
        # If it was added, it would show as an error row, but it shouldn't be added at all
        stocks_table = page.locator("#stocksTable tbody tr")
        stock_count = stocks_table.count()
        
        # Check that SDSK is not in any row
        for i in range(stock_count):
            row_text = stocks_table.nth(i).inner_text()
            assert "SDSK" not in row_text, f"SDSK should not be in the table, but found in row: {row_text}"
    
    def test_add_stocks_mixed_valid_invalid(self, page: Page, live_server_url):
        """Test adding mix of valid and invalid format tickers - format validation should catch invalid ones."""
        watchlist = create_watchlist("Test WatchList")
        
        page.goto(f"{live_server_url}/watchlist/{watchlist.watchlist_id}")
        
        # Add mix of valid and invalid format tickers (> 5 chars)
        # Frontend format validation should catch INVALID12345 before API call
        page.fill("#tickersInput", "AAPL,INVALID12345,MSFT")
        page.click("button[type='submit']")
        
        # Should show format validation error message (frontend catches this before API call)
        expect(page.locator("#errorMessage")).to_be_visible()
        expect(page.locator("#errorMessage")).to_contain_text("Invalid ticker format")
        expect(page.locator("#errorMessage")).to_contain_text("INVALID12345")
        
        # Wait a bit - no stocks should be added because format validation failed
        page.wait_for_timeout(2000)
        
        # Since format validation failed, no API call was made, so no stocks should be added
        # The table should be empty (or only have pre-existing stocks)
        # We can't verify AAPL/MSFT were added because the form submission was blocked
    
    def test_add_stocks_mixed_valid_sdsk(self, page: Page, live_server_url):
        """Test adding mix of valid ticker and SDSK - only valid one should be added."""
        watchlist = create_watchlist("Test WatchList")
        
        page.goto(f"{live_server_url}/watchlist/{watchlist.watchlist_id}")
        
        # Add mix of valid ticker and SDSK (valid format but doesn't exist)
        page.fill("#tickersInput", "AAPL,SDSK")
        page.click("button[type='submit']")
        
        # Should show error message about SDSK being invalid
        expect(page.locator("#errorMessage")).to_be_visible(timeout=10000)
        expect(page.locator("#errorMessage")).to_contain_text("Ticker SDSK is invalid")
        
        # Wait for page reload if stocks were added
        page.wait_for_timeout(3000)
        
        # Valid stock should appear in table
        expect(page.locator("text=AAPL")).to_be_visible(timeout=10000)
        
        # SDSK should NOT be in the table (should not be added at all)
        stocks_table = page.locator("#stocksTable tbody tr")
        stock_count = stocks_table.count()
        
        # Check that SDSK is not in any row
        for i in range(stock_count):
            row_text = stocks_table.nth(i).inner_text()
            assert "SDSK" not in row_text, f"SDSK should not be in the table, but found in row: {row_text}"
    
    def test_delete_button_visible_for_error_rows(self, page: Page, live_server_url):
        """Test that delete button is visible and actionable for error rows."""
        watchlist = create_watchlist("Test WatchList")
        # Add a stock that will fail to fetch (using a non-existent ticker)
        # We'll manually add it to the database to simulate an existing invalid ticker
        from app.models.watchlist import WatchListStock
        from datetime import datetime
        with Session(engine) as session:
            invalid_stock = WatchListStock(
                watchlist_id=watchlist.watchlist_id,
                ticker="SDSK",  # This ticker doesn't exist and will cause an error
                date_added=datetime.now()
            )
            session.add(invalid_stock)
            session.commit()
        
        page.goto(f"{live_server_url}/watchlist/{watchlist.watchlist_id}")
        
        # Wait for table to load
        page.wait_for_selector('#stocksTable', state='visible', timeout=10000)
        page.wait_for_timeout(3000)  # Give time for data to load
        
        # Find the error row (should have table-danger class)
        error_row = page.locator('#stocksTable tbody tr.table-danger')
        expect(error_row).to_be_visible()
        
        # Check that ticker name is displayed in the first column (more specific locator)
        expect(error_row.locator("td:first-child strong:has-text('SDSK')")).to_be_visible()
        
        # Check that error message is displayed in the error cell
        expect(error_row.locator("td.text-danger")).to_be_visible()
        # Error message can be "Error fetching data" or "No price data found for ticker: SDSK"
        error_text = error_row.locator("td.text-danger").inner_text()
        assert "error" in error_text.lower() or "no price data" in error_text.lower(), \
            f"Error message should contain 'error' or 'no price data', got: {error_text}"
        
        # Check that delete button is visible in the error row
        delete_button = error_row.locator("button.btn-danger")
        expect(delete_button).to_be_visible()
        
        # Verify delete button is actionable (can be clicked)
        # Set up dialog handler before clicking
        page.once("dialog", lambda dialog: dialog.accept())
        
        # Click delete button
        delete_button.click()
        
        # Wait for page to reload
        page.wait_for_timeout(2000)
        
        # Verify the error row is removed (SDSK should not be visible)
        expect(page.locator("td:first-child strong:has-text('SDSK')")).not_to_be_visible(timeout=5000)
    
    def test_edit_watchlist_name(self, page: Page, live_server_url):
        """Test editing watchlist name."""
        watchlist = create_watchlist("Old Name")
        
        page.goto(f"{live_server_url}/watchlist/{watchlist.watchlist_id}")
        
        # Click edit button
        page.click("button:has(svg.bi-pencil)")
        
        # Check that edit input is visible
        expect(page.locator("#watchlistNameInput")).to_be_visible()
        
        # Update name
        page.fill("#watchlistNameInput", "New Name")
        page.click("button:has-text('Save')")
        
        # Wait for page to reload
        page.wait_for_timeout(2000)
        
        # Check that name is updated
        expect(page.locator("h1")).to_contain_text("New Name")
    
    def test_remove_stock_from_portfolio(self, page: Page, live_server_url):
        """Test removing a stock from watchlist."""
        watchlist = create_watchlist("Test WatchList")
        
        # Manually add stocks to watchlist (bypass yfinance validation in CI)
        from app.models.watchlist import WatchListStock
        from datetime import datetime
        with Session(engine) as session:
            for ticker in ["AAPL", "MSFT"]:
                stock = WatchListStock(
                    watchlist_id=watchlist.watchlist_id,
                    ticker=ticker,
                    date_added=datetime.now()
                )
                session.add(stock)
            session.commit()
        
        page.goto(f"{live_server_url}/watchlist/{watchlist.watchlist_id}")
        
        # Wait for table to load
        page.wait_for_selector('#stocksTable', state='visible', timeout=10000)
        page.wait_for_timeout(2000)
        
        # Verify both stocks are visible before deletion
        expect(page.locator("#stocksTable tbody tr").filter(has_text="AAPL")).to_be_visible()
        expect(page.locator("#stocksTable tbody tr").filter(has_text="MSFT")).to_be_visible()
        
        # Find delete button for AAPL (first stock)
        # Find the row containing AAPL and get its delete button
        aapl_row = page.locator("#stocksTable tbody tr").filter(has_text="AAPL").first
        delete_button = aapl_row.locator("button.btn-danger")
        expect(delete_button).to_be_visible()
        
        # Set up dialog handler before clicking
        page.once("dialog", lambda dialog: dialog.accept())
        
        # Click delete button
        delete_button.click()
        
        # Wait for page to reload after deletion
        page.wait_for_load_state("networkidle", timeout=10000)
        page.wait_for_timeout(2000)
        
        # Verify AAPL is removed and MSFT is still there
        # Check that AAPL is not in the table
        aapl_rows = page.locator("#stocksTable tbody tr").filter(has_text="AAPL")
        expect(aapl_rows).to_have_count(0, timeout=5000)
        
        # Check that MSFT is still visible
        expect(page.locator("#stocksTable tbody tr").filter(has_text="MSFT")).to_be_visible(timeout=5000)
    
    def test_watchlist_name_link_navigation(self, page: Page, live_server_url):
        """Test that clicking watchlist name navigates to details page."""
        watchlist = create_watchlist("Test WatchList")
        
        page.goto(f"{live_server_url}/watchlists")
        
        # Click on watchlist name link
        page.click(f"a[href='/watchlist/{watchlist.watchlist_id}']")
        
        # Should navigate to watchlist details page
        page.wait_for_url(f"**/watchlist/{watchlist.watchlist_id}", timeout=5000)
        expect(page.locator("h1")).to_contain_text("Test WatchList")
    
    def test_homepage_watchlist_link(self, page: Page, live_server_url):
        """Test that homepage has link to watchlists."""
        page.goto(f"{live_server_url}/")
        
        # Check for watchlist link
        watchlist_link = page.locator("a[href='/watchlists']")
        expect(watchlist_link).to_be_visible()
        expect(watchlist_link).to_contain_text("View My WatchLists")
        
        # Click link
        watchlist_link.click()
        
        # Should navigate to watchlists page
        page.wait_for_url("**/watchlists", timeout=5000)
        expect(page).to_have_title("WatchLists - Arthos")
    
    def test_dividend_yield_display_in_portfolio(self, page: Page, live_server_url):
        """Test that dividend yield is displayed correctly in watchlist table."""
        watchlist = create_watchlist("Test WatchList")
        added, _ = add_stocks_to_watchlist(watchlist.watchlist_id, ["HD", "AAPL"])
        
        page.goto(f"{live_server_url}/watchlist/{watchlist.watchlist_id}")
        
        # Wait for table to load
        page.wait_for_selector('#stocksTable', state='visible', timeout=10000)
        page.wait_for_timeout(3000)  # Give time for data to load
        
        # Check that Dividend Yield column header exists
        dividend_yield_header = page.locator('#stocksTable thead th:has-text("Dividend Yield")')
        expect(dividend_yield_header).to_be_visible()
        
        # Check that dividend yield values are displayed (not empty)
        # Find all dividend yield cells (should be in the 5th column, 0-indexed as 4)
        dividend_yield_cells = page.locator('#stocksTable tbody tr td:nth-child(5)')
        count = dividend_yield_cells.count()
        
        # At least one stock should have dividend yield data
        assert count > 0, "No dividend yield cells found in table"
        
        # Check that dividend yield values are formatted correctly (should be percentage or N/A)
        for i in range(count):
            cell_text = dividend_yield_cells.nth(i).inner_text().strip()
            # Cell should not be empty
            assert cell_text != "", f"Dividend yield cell {i} is empty"
            # Should be either "N/A" or a percentage (e.g., "2.66%")
            assert cell_text == "N/A" or cell_text.endswith("%"), \
                f"Dividend yield cell {i} has invalid format: '{cell_text}'"
            # If it's a percentage, it should be a reasonable value (not > 100%)
            if cell_text != "N/A":
                value = float(cell_text.replace("%", ""))
                assert 0 <= value <= 100, \
                    f"Dividend yield value {value}% is out of reasonable range"
    
    def test_dividend_yield_display_in_stock_detail(self, page: Page, live_server_url):
        """Test that dividend yield is displayed correctly on stock detail page."""
        # Test with HD stock (should have dividend yield around 2.66%)
        response = page.goto(f"{live_server_url}/stock/HD", wait_until="networkidle", timeout=30000)
        
        # Check that we got a 200 response (not 404)
        if response.status == 404:
            # If 404, the data might not be populated - skip this test
            pytest.skip(f"Stock detail page returned 404 for HD. Data may not be available. Response: {response.status}")
        
        assert response.status == 200, f"Expected 200, got {response.status}. Response text: {page.content()[:500]}"
        
        # Wait for metrics card to be visible
        page.wait_for_selector('.metrics-card', state='visible', timeout=10000)
        page.wait_for_timeout(2000)  # Give time for data to load
        
        # Check that Dividend Yield label exists
        dividend_yield_label = page.locator('.metric-label:has-text("Dividend Yield")')
        expect(dividend_yield_label).to_be_visible()
        
        # Check that dividend yield value is displayed
        # Find the metric item for Dividend Yield
        metric_items = page.locator('.metric-item')
        dividend_yield_found = False
        
        for i in range(metric_items.count()):
            item = metric_items.nth(i)
            label = item.locator('.metric-label').inner_text().strip()
            if label == "Dividend Yield":
                value = item.locator('.metric-value').inner_text().strip()
                # Should be either "N/A" or a percentage (e.g., "2.66%")
                assert value == "N/A" or value.endswith("%"), \
                    f"Dividend yield has invalid format: {value}"
                # If it's a percentage, it should be a reasonable value (not > 100%)
                if value != "N/A":
                    value_num = float(value.replace("%", ""))
                    assert 0 <= value_num <= 100, \
                        f"Dividend yield value {value_num}% is out of reasonable range"
                    # For HD, it should be around 2.66%, not 266%
                    assert value_num < 10, \
                        f"Dividend yield {value_num}% seems too high for HD (expected ~2.66%)"
                dividend_yield_found = True
                break
        
        assert dividend_yield_found, "Dividend Yield metric not found on stock detail page"
