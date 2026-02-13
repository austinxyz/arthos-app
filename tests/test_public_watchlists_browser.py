"""Browser tests for public watchlist pages."""
import os
import pytest
from datetime import datetime
from playwright.sync_api import Page, expect
from sqlmodel import Session

from app.database import engine
from app.models.watchlist import WatchList, WatchListStock
from tests.conftest import populate_test_stock_prices


@pytest.fixture(autouse=True)
def setup_test_data(setup_database):
    """Use shared cleanup fixture and seed stock data needed by public watchlist views."""
    populate_test_stock_prices("AAPL")
    yield


@pytest.fixture
def live_server_url():
    """Get the live server URL from environment or use default."""
    return os.getenv("TEST_SERVER_URL", "http://localhost:8000")


def _create_watchlist(name: str, account_id: str, is_public: bool) -> WatchList:
    """Create a watchlist record directly for deterministic browser tests."""
    with Session(engine) as session:
        watchlist = WatchList(
            watchlist_name=name,
            account_id=account_id,
            is_public=is_public,
            date_added=datetime.now(),
            date_modified=datetime.now()
        )
        session.add(watchlist)
        session.commit()
        session.refresh(watchlist)
        return watchlist


@pytest.mark.browser
class TestPublicWatchlistsBrowser:
    """Browser tests for public watchlist listing and read-only details."""

    def test_public_watchlists_page_shows_only_public_entries(
        self,
        page: Page,
        live_server_url,
        test_account,
        unauthenticated_session
    ):
        """Public listing should include only public watchlists."""
        public_watchlist = _create_watchlist("Public Alpha", str(test_account.id), True)
        _create_watchlist("Private Secret", str(test_account.id), False)

        page.goto(f"{live_server_url}/public-watchlists")
        expect(page).to_have_title("Public WatchLists - Arthos")

        table = page.locator("#publicWatchlistsTable")
        expect(table).to_be_visible()

        public_row = page.locator("#publicWatchlistsTable tbody tr").filter(has_text="Public Alpha")
        expect(public_row).to_be_visible()
        expect(
            public_row.locator(f"a[href='/public-watchlist/{public_watchlist.watchlist_id}']").first
        ).to_be_visible()

        # Private watchlists must not appear in public listing
        expect(page.locator("text=Private Secret")).to_have_count(0)

    def test_public_watchlist_details_is_read_only_for_anonymous_user(
        self,
        page: Page,
        live_server_url,
        test_account,
        unauthenticated_session
    ):
        """Public watchlist details page should be accessible and read-only."""
        public_watchlist = _create_watchlist("Public Read Only", str(test_account.id), True)

        with Session(engine) as session:
            session.add(WatchListStock(
                watchlist_id=public_watchlist.watchlist_id,
                ticker="AAPL",
                date_added=datetime.now()
            ))
            session.commit()

        page.goto(f"{live_server_url}/public-watchlist/{public_watchlist.watchlist_id}")
        expect(page).to_have_title("WatchList: Public Read Only - Arthos")
        expect(page.locator("h1")).to_contain_text("Public Read Only")
        expect(page.locator("a[href='/public-watchlists']")).to_be_visible()

        # Read-only: owner controls/forms should not be present
        expect(page.locator("#tickersInput")).to_have_count(0)
        expect(page.locator("#visibilityToggle")).to_have_count(0)
        expect(page.locator("#watchlistNameInput")).to_have_count(0)

        # Data table still visible
        expect(page.locator("#stocksTable")).to_be_visible()
        expect(page.locator("#stocksTable tbody tr").filter(has_text="AAPL")).to_be_visible()
        expect(page.locator("#stocksTable thead th:has-text('Actions')")).to_have_count(0)
