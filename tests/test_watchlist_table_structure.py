"""Test to verify watchlist details table structure matches DataTables requirements."""
import pytest
from playwright.sync_api import Page, expect
from app.services.watchlist_service import create_watchlist, add_stocks_to_watchlist
from app.database import engine, create_db_and_tables
from sqlmodel import Session
from app.models.watchlist import WatchList, WatchListStock
from app.models.stock_price import StockPrice, StockAttributes
from tests.conftest import populate_test_stock_prices


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
    
    # Populate test data
    populate_test_stock_prices("AAPL")
    populate_test_stock_prices("MSFT")
    
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
    """Get the live server URL from environment or use default."""
    import os
    return os.getenv("TEST_SERVER_URL", "http://localhost:8000")


@pytest.mark.browser
def test_watchlist_table_column_count(page: Page, live_server_url):
    """Test that watchlist details table has correct column count for DataTables."""
    # Create a watchlist
    watchlist = create_watchlist("Test WatchList")
    
    # Add stocks to watchlist
    add_stocks_to_watchlist(watchlist.watchlist_id, ["AAPL", "MSFT"])
    
    # Navigate to watchlist details page
    page.goto(f"{live_server_url}/watchlist/{watchlist.watchlist_id}")
    
    # Wait for table to be visible
    table = page.locator("#stocksTable")
    expect(table).to_be_visible()
    
    # Count header columns
    header_cells = page.locator("#stocksTable thead th")
    header_count = header_cells.count()
    print(f"Header columns: {header_count}")
    
    # Count body row columns (first data row)
    first_row_cells = page.locator("#stocksTable tbody tr:first-child td")
    first_row_count = first_row_cells.count()
    print(f"First row columns: {first_row_count}")
    
    # Verify column counts match
    assert header_count == first_row_count, f"Header has {header_count} columns but first row has {first_row_count} columns"
    assert header_count == 10, f"Expected 10 columns but found {header_count}"
    
    # Check that DataTables initialized without errors
    # DataTables warning would appear in console, but we can check if table is functional
    # by checking if sorting works (DataTables adds click handlers)
    signal_header = page.locator("#stocksTable thead th[data-column='signal']")
    expect(signal_header).to_be_visible()
    
    # Verify no DataTables errors in console
    # Note: This is a basic check - actual console errors would need to be captured differently
    print("Table structure verified - no column count mismatch detected")


@pytest.mark.browser
def test_watchlist_table_with_error_row(page: Page, live_server_url):
    """Test that error rows have correct column count."""
    # Create a watchlist
    watchlist = create_watchlist("Test WatchList")
    
    # Add a valid stock and an invalid one
    # The invalid one should show an error row
    add_stocks_to_watchlist(watchlist.watchlist_id, ["AAPL", "INVALIDTICKER123"])
    
    # Navigate to watchlist details page
    page.goto(f"{live_server_url}/watchlist/{watchlist.watchlist_id}")
    
    # Wait for table to be visible
    table = page.locator("#stocksTable")
    expect(table).to_be_visible()
    
    # Count header columns
    header_cells = page.locator("#stocksTable thead th")
    header_count = header_cells.count()
    
    # Find error row (should have class table-danger)
    error_row = page.locator("#stocksTable tbody tr.table-danger").first()
    
    if error_row.count() > 0:
        # Count columns in error row
        error_row_cells = error_row.locator("td")
        error_row_count = error_row_cells.count()
        
        # Check for colspan
        error_cell = error_row.locator("td.text-danger")
        if error_cell.count() > 0:
            colspan = error_cell.get_attribute("colspan")
            print(f"Error row has {error_row_count} cells, error cell colspan={colspan}")
            
            # Verify total columns match header
            assert error_row_count == header_count, \
                f"Error row has {error_row_count} columns but header has {header_count}"
    
    print("Error row structure verified")
