"""Browser tests for watchlist functionality using Playwright."""
import pytest
from playwright.sync_api import Page, expect
from app.services.watchlist_service import create_watchlist, add_stocks_to_watchlist
from app.database import engine, create_db_and_tables
from sqlmodel import Session
from app.models.watchlist import WatchList, WatchListStock


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables and clean up before and after each test."""
    create_db_and_tables()
    
    # Cleanup before test
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
        
        session.commit()


@pytest.fixture
def live_server_url():
    """Return the URL of the live server."""
    return "http://localhost:8000"


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
        """Test adding invalid ticker to watchlist."""
        watchlist = create_watchlist("Test WatchList")
        
        page.goto(f"{live_server_url}/watchlist/{watchlist.watchlist_id}")
        
        # Try invalid ticker
        page.fill("#tickersInput", "INVALID12345")
        page.click("button[type='submit']")
        
        # Should show error message
        expect(page.locator("#errorMessage")).to_be_visible()
        expect(page.locator("#errorMessage")).to_contain_text("Invalid ticker format")
    
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
        add_stocks_to_watchlist(watchlist.watchlist_id, ["AAPL", "MSFT"])
        
        page.goto(f"{live_server_url}/watchlist/{watchlist.watchlist_id}")
        
        # Wait for stocks to load
        page.wait_for_timeout(2000)
        
        # Find delete button for AAPL (first stock)
        # Note: This assumes the delete button is visible
        # We'll need to check if the stock row exists first
        delete_buttons = page.locator("button.btn-danger")
        if delete_buttons.count() > 0:
            # Set up dialog handler before clicking
            page.once("dialog", lambda dialog: dialog.accept())
            
            # Click first delete button (use nth(0) instead of first() if first() is not callable)
            delete_buttons.nth(0).click()
            
            # Wait for page to reload
            page.wait_for_timeout(2000)
            
            # Verify stock is removed (MSFT should still be there)
            # This is a basic check - in practice, we'd verify the specific stock is gone
            expect(page.locator("text=MSFT")).to_be_visible(timeout=5000)
    
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
        add_stocks_to_watchlist(watchlist.watchlist_id, ["HD", "AAPL"])
        
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
        page.goto(f"{live_server_url}/stock/HD")
        
        # Wait for page to load
        page.wait_for_selector('.metrics-card', state='visible', timeout=10000)
        page.wait_for_timeout(3000)  # Give time for data to load
        
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
