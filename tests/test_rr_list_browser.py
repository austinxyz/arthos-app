"""Browser tests for RR Watchlist list page using Playwright."""
import pytest
from playwright.sync_api import Page, expect
from datetime import datetime, date, timedelta
from decimal import Decimal
from sqlmodel import Session
from app.database import engine, create_db_and_tables
from app.models.rr_watchlist import RRWatchlist, RRHistory


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables and clean up before and after each test."""
    create_db_and_tables()
    
    # Cleanup before test
    with Session(engine) as session:
        from sqlmodel import select
        
        # Delete history first (foreign key constraint)
        statement = select(RRHistory)
        all_history = session.exec(statement).all()
        for hist in all_history:
            session.delete(hist)
        
        # Delete watchlist entries
        statement = select(RRWatchlist)
        all_entries = session.exec(statement).all()
        for entry in all_entries:
            session.delete(entry)
        
        session.commit()
    
    yield
    
    # Cleanup after test
    with Session(engine) as session:
        from sqlmodel import select
        
        statement = select(RRHistory)
        all_history = session.exec(statement).all()
        for hist in all_history:
            session.delete(hist)
        
        statement = select(RRWatchlist)
        all_entries = session.exec(statement).all()
        for entry in all_entries:
            session.delete(entry)
        
        session.commit()


def create_test_rr_entry(ticker: str = "AAPL", ratio: str = "1:1", account_id: str = None) -> RRWatchlist:
    """Helper to create a test RR watchlist entry."""
    from uuid import UUID
    with Session(engine) as session:
        entry = RRWatchlist(
            ticker=ticker,
            expiration=date.today() + timedelta(days=90),
            put_strike=Decimal("150.00"),
            call_strike=Decimal("170.00"),
            put_quantity=1,
            call_quantity=1,
            stock_price=Decimal("160.00"),
            entry_price=Decimal("2.50"),
            call_option_quote=Decimal("3.50"),  # Required field
            put_option_quote=Decimal("1.00"),   # Required field
            ratio=ratio,
            expired_yn="N",
            date_added=datetime.now(),
            account_id=UUID(account_id) if account_id else None
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry


@pytest.fixture
def live_server_url():
    """Return the URL of the live server."""
    import os
    return os.getenv("TEST_SERVER_URL", "http://localhost:8000")


@pytest.mark.browser
class TestRRListBrowser:
    """Browser tests for RR Watchlist list page."""
    
    def test_rr_list_page_loads(self, page: Page, live_server_url, authenticated_session):
        """Test that the RR list page loads correctly."""
        page.goto(f"{live_server_url}/rr-list")
        
        # Check page title
        expect(page).to_have_title("RR Watchlist - Arthos")
        
        # Check header
        expect(page.locator("h1")).to_contain_text("RR Watchlist")
        
        # Check table exists
        expect(page.locator("#rrTable")).to_be_visible()
    
    def test_rr_list_shows_entries(self, page: Page, live_server_url, authenticated_session):
        """Test that RR entries are displayed in the table."""
        # Create test entry with authenticated account
        entry = create_test_rr_entry("AAPL", account_id=str(authenticated_session))
        
        page.goto(f"{live_server_url}/rr-list")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Check that AAPL is displayed
        expect(page.locator("#rrTable tbody")).to_contain_text("AAPL")
        
        # Check that delete button is visible
        delete_btn = page.locator(f".delete-rr-btn[data-rr-id='{entry.id}']")
        expect(delete_btn).to_be_visible()
    
    def test_delete_button_exists_and_clickable(self, page: Page, live_server_url, authenticated_session):
        """Test that delete button is visible and shows confirmation dialog when clicked.
        
        Note: Full delete verification is tested in test_rr_watchlist_collar.py at service layer.
        This browser test verifies UI behavior with authenticated user.
        """
        # Create test entry with authenticated account
        entry = create_test_rr_entry("MSFT", account_id=str(authenticated_session))
        entry_id = entry.id
        
        page.goto(f"{live_server_url}/rr-list")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify entry is visible
        expect(page.locator("#rrTable tbody")).to_contain_text("MSFT")
        
        # Find delete button for this entry
        delete_btn = page.locator(f".delete-rr-btn[data-rr-id='{entry_id}']")
        expect(delete_btn).to_be_visible()
        
        # Verify button has correct text
        expect(delete_btn).to_contain_text("Delete")
        
        # Verify button has correct styling (btn-danger class)
        import re
        expect(delete_btn).to_have_class(re.compile(r"btn-danger"))
        
        # Set up dialog handler to capture the confirmation dialog
        dialog_shown = []
        def handle_dialog(dialog):
            dialog_shown.append(dialog.message)
            dialog.dismiss()  # Cancel the delete
        
        page.once("dialog", handle_dialog)
        
        # Click delete button
        delete_btn.click()
        
        # Wait for dialog to be processed
        page.wait_for_timeout(1000)
        
        # Verify confirmation dialog was shown
        assert len(dialog_shown) == 1, "Confirmation dialog should have been shown"
        assert "delete" in dialog_shown[0].lower() or "risk reversal" in dialog_shown[0].lower(), \
            f"Dialog should mention delete/risk reversal, got: {dialog_shown[0]}"
        
        # Entry should still exist since we dismissed the dialog
        expect(page.locator("#rrTable tbody")).to_contain_text("MSFT")
    
    def test_delete_button_cancel_keeps_entry(self, page: Page, live_server_url, authenticated_session):
        """Test that canceling delete confirmation keeps the entry."""
        # Create test entry with authenticated account
        entry = create_test_rr_entry("GOOGL", account_id=str(authenticated_session))
        entry_id = entry.id
        
        page.goto(f"{live_server_url}/rr-list")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify entry is visible
        expect(page.locator("#rrTable tbody")).to_contain_text("GOOGL")
        
        # Find delete button
        delete_btn = page.locator(f".delete-rr-btn[data-rr-id='{entry_id}']")
        expect(delete_btn).to_be_visible()
        
        # Set up dialog handler to dismiss (cancel) confirmation
        page.once("dialog", lambda dialog: dialog.dismiss())
        
        # Click delete button
        delete_btn.click()
        
        # Wait a moment
        page.wait_for_timeout(1000)
        
        # Verify entry is still visible
        expect(page.locator("#rrTable tbody")).to_contain_text("GOOGL")
        
        # Verify entry is still in database
        with Session(engine) as session:
            from sqlmodel import select
            statement = select(RRWatchlist).where(RRWatchlist.id == entry_id)
            result = session.exec(statement).first()
            assert result is not None, "Entry should still exist in database"

    def test_delete_entry_success(self, page: Page, live_server_url, authenticated_session):
        """Test that confirming delete actually removes the entry from UI and database."""
        # Create test entry with authenticated account
        entry = create_test_rr_entry("NVDA", account_id=str(authenticated_session))
        entry_id = entry.id
        
        page.goto(f"{live_server_url}/rr-list")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        
        # Verify entry is visible
        expect(page.locator("#rrTable tbody")).to_contain_text("NVDA")
        
        # Find delete button
        delete_btn = page.locator(f".delete-rr-btn[data-rr-id='{entry_id}']")
        expect(delete_btn).to_be_visible()
        
        # Set up dialog handler to ACCEPT (confirm) the deletion
        page.once("dialog", lambda dialog: dialog.accept())
        
        # Click delete button
        delete_btn.click()
        
        # Wait for AJAX request to complete and row to be removed
        page.wait_for_timeout(2000)
        
        # Verify entry is no longer visible in the table
        expect(page.locator("#rrTable tbody")).not_to_contain_text("NVDA")
        
        # Verify entry is removed from database
        with Session(engine) as session:
            from sqlmodel import select
            statement = select(RRWatchlist).where(RRWatchlist.id == entry_id)
            result = session.exec(statement).first()
            assert result is None, "Entry should be deleted from database"

