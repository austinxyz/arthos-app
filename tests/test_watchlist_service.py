"""Tests for watchlist service."""
import pytest
from uuid import UUID
from datetime import datetime
from app.services.watchlist_service import (
    validate_watchlist_name,
    create_watchlist,
    get_all_watchlists,
    get_watchlist,
    update_watchlist_name,
    delete_watchlist,
    add_stocks_to_watchlist,
    remove_stock_from_watchlist,
    get_watchlist_stocks,
    get_watchlist_stocks_with_metrics
)
from app.database import engine, create_db_and_tables
from sqlmodel import Session
from app.models.watchlist import WatchList, WatchListStock


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables before each test."""
    create_db_and_tables()
    yield
    # Cleanup
    with Session(engine) as session:
        from sqlmodel import select
        from app.models.stock_price import StockPrice, StockAttributes
        
        statement = select(WatchListStock)
        all_stocks = session.exec(statement).all()
        for stock in all_stocks:
            session.delete(stock)
        
        statement = select(WatchList)
        all_watchlists = session.exec(statement).all()
        for watchlist in all_watchlists:
            session.delete(watchlist)
        
        # Cleanup stock price data
        statement = select(StockPrice)
        all_prices = session.exec(statement).all()
        for price in all_prices:
            session.delete(price)
        
        statement = select(StockAttributes)
        all_attributes = session.exec(statement).all()
        for attributes in all_attributes:
            session.delete(attributes)
        
        session.commit()


class TestValidateWatchListName:
    """Tests for validate_watchlist_name function."""
    
    def test_valid_name_alphanumeric(self):
        """Test valid alphanumeric name."""
        assert validate_watchlist_name("MyPortfolio123") is True
    
    def test_valid_name_with_spaces(self):
        """Test valid name with spaces."""
        assert validate_watchlist_name("My WatchList 123") is True
    
    def test_invalid_empty_string(self):
        """Test empty string."""
        assert validate_watchlist_name("") is False
        assert validate_watchlist_name("   ") is False
    
    def test_invalid_too_long(self):
        """Test name that's too long."""
        long_name = "A" * 129  # 129 characters
        assert validate_watchlist_name(long_name) is False
    
    def test_invalid_special_characters(self):
        """Test name with special characters."""
        assert validate_watchlist_name("My-WatchList") is False
        assert validate_watchlist_name("My_Portfolio") is False
        assert validate_watchlist_name("My@WatchList") is False
        assert validate_watchlist_name("My.WatchList") is False


class TestCreateWatchList:
    """Tests for create_watchlist function."""
    
    def test_create_portfolio_success(self):
        """Test successful watchlist creation."""
        watchlist = create_watchlist("Test WatchList")
        
        assert watchlist.watchlist_id is not None
        assert watchlist.watchlist_name == "Test WatchList"
        assert isinstance(watchlist.date_added, datetime)
        assert isinstance(watchlist.date_modified, datetime)
    
    def test_create_portfolio_invalid_name(self):
        """Test watchlist creation with invalid name."""
        with pytest.raises(ValueError, match="WatchList name must be"):
            create_watchlist("My-WatchList!")
    
    def test_create_portfolio_whitespace_trimmed(self):
        """Test that watchlist name whitespace is trimmed."""
        watchlist = create_watchlist("  Test WatchList  ")
        assert watchlist.watchlist_name == "Test WatchList"


class TestGetAllWatchLists:
    """Tests for get_all_watchlists function."""
    
    def test_get_all_portfolios_empty(self):
        """Test getting all portfolios when none exist."""
        portfolios = get_all_watchlists()
        assert portfolios == []
    
    def test_get_all_portfolios_multiple(self):
        """Test getting all portfolios."""
        portfolio1 = create_watchlist("WatchList 1")
        portfolio2 = create_watchlist("WatchList 2")
        
        portfolios = get_all_watchlists()
        assert len(portfolios) == 2
        assert any(p.watchlist_id == portfolio1.watchlist_id for p in portfolios)
        assert any(p.watchlist_id == portfolio2.watchlist_id for p in portfolios)


class TestGetWatchList:
    """Tests for get_watchlist function."""
    
    def test_get_portfolio_success(self):
        """Test getting a watchlist by ID."""
        created = create_watchlist("Test WatchList")
        retrieved = get_watchlist(created.watchlist_id)
        
        assert retrieved.watchlist_id == created.watchlist_id
        assert retrieved.watchlist_name == "Test WatchList"
    
    def test_get_portfolio_not_found(self):
        """Test getting a non-existent watchlist."""
        fake_id = '00000000-0000-0000-0000-000000000000'  # Use string for SQLite compatibility
        with pytest.raises(ValueError, match="not found"):
            get_watchlist(fake_id)


class TestUpdateWatchListName:
    """Tests for update_watchlist_name function."""
    
    def test_update_watchlist_name_success(self):
        """Test successful watchlist name update."""
        watchlist = create_watchlist("Old Name")
        updated = update_watchlist_name(watchlist.watchlist_id, "New Name")
        
        assert updated.watchlist_name == "New Name"
        assert updated.watchlist_id == watchlist.watchlist_id
        assert updated.date_modified > watchlist.date_modified
    
    def test_update_watchlist_name_invalid(self):
        """Test updating with invalid name."""
        watchlist = create_watchlist("Test WatchList")
        with pytest.raises(ValueError, match="WatchList name must be"):
            update_watchlist_name(watchlist.watchlist_id, "Invalid-Name!")


class TestDeleteWatchList:
    """Tests for delete_watchlist function."""
    
    def test_delete_portfolio_success(self):
        """Test successful watchlist deletion."""
        watchlist = create_watchlist("Test WatchList")
        result = delete_watchlist(watchlist.watchlist_id)
        
        assert result is True
        
        # Verify watchlist is deleted
        with pytest.raises(ValueError, match="not found"):
            get_watchlist(watchlist.watchlist_id)


class TestAddStocksToWatchList:
    """Tests for add_stocks_to_watchlist function."""
    
    def test_add_stocks_success(self):
        """Test successfully adding stocks to watchlist."""
        watchlist = create_watchlist("Test WatchList")
        added, invalid = add_stocks_to_watchlist(watchlist.watchlist_id, ["AAPL", "MSFT"])
        
        assert len(added) == 2
        assert len(invalid) == 0
        assert any(s.ticker == "AAPL" for s in added)
        assert any(s.ticker == "MSFT" for s in added)
    
    def test_add_stocks_duplicate_ignored(self):
        """Test that duplicate stocks are ignored."""
        watchlist = create_watchlist("Test WatchList")
        
        # Add AAPL first time
        added1, invalid1 = add_stocks_to_watchlist(watchlist.watchlist_id, ["AAPL"])
        assert len(added1) == 1
        assert len(invalid1) == 0
        
        # Try to add AAPL again
        added2, invalid2 = add_stocks_to_watchlist(watchlist.watchlist_id, ["AAPL"])
        assert len(added2) == 0  # Should be ignored
        assert len(invalid2) == 0
    
    def test_add_stocks_invalid_ticker_filtered(self):
        """Test that invalid tickers are filtered out instead of raising error."""
        watchlist = create_watchlist("Test WatchList")
        added, invalid = add_stocks_to_watchlist(watchlist.watchlist_id, ["INVALID12345"])
        
        assert len(added) == 0
        assert len(invalid) == 1
        assert "INVALID12345" in invalid
    
    def test_add_stocks_mixed_valid_invalid(self):
        """Test adding mix of valid and invalid tickers."""
        watchlist = create_watchlist("Test WatchList")
        added, invalid = add_stocks_to_watchlist(watchlist.watchlist_id, ["AAPL", "INVALID12345", "MSFT", "BADTICKER"])
        
        assert len(added) == 2
        assert len(invalid) == 2
        assert any(s.ticker == "AAPL" for s in added)
        assert any(s.ticker == "MSFT" for s in added)
        assert "INVALID12345" in invalid
        assert "BADTICKER" in invalid
    
    def test_add_stocks_ticker_not_exists_in_yfinance(self):
        """Test that tickers that pass format validation but don't exist in yfinance are filtered out."""
        watchlist = create_watchlist("Test WatchList")
        # SDSK passes format validation but doesn't exist in yfinance
        added, invalid = add_stocks_to_watchlist(watchlist.watchlist_id, ["SDSK", "AAPL"])
        
        assert len(added) == 1
        assert len(invalid) == 1
        assert any(s.ticker == "AAPL" for s in added)
        assert "SDSK" in invalid


class TestRemoveStockFromWatchList:
    """Tests for remove_stock_from_watchlist function."""
    
    def test_remove_stock_success(self):
        """Test successfully removing a stock."""
        watchlist = create_watchlist("Test WatchList")
        added, _ = add_stocks_to_watchlist(watchlist.watchlist_id, ["AAPL", "MSFT"])
        
        result = remove_stock_from_watchlist(watchlist.watchlist_id, "AAPL")
        assert result is True
        
        # Verify stock is removed
        stocks = get_watchlist_stocks(watchlist.watchlist_id)
        assert len(stocks) == 1
        assert stocks[0].ticker == "MSFT"
    
    def test_remove_stock_not_found(self):
        """Test removing a stock that doesn't exist."""
        watchlist = create_watchlist("Test WatchList")
        with pytest.raises(ValueError, match="not found in watchlist"):
            remove_stock_from_watchlist(watchlist.watchlist_id, "AAPL")


class TestGetWatchlistStocksWithMetrics:
    """Tests for get_watchlist_stocks_with_metrics function."""
    
    def test_get_metrics_empty_watchlist(self):
        """Test getting metrics for empty watchlist."""
        watchlist = create_watchlist("Test WatchList")
        metrics = get_watchlist_stocks_with_metrics(watchlist.watchlist_id)
        
        assert metrics == []
    
    def test_get_metrics_with_stocks(self):
        """Test getting metrics for watchlist with stocks."""
        watchlist = create_watchlist("Test WatchList")
        
        # Add stocks (this will also fetch and save stock prices)
        added, invalid = add_stocks_to_watchlist(watchlist.watchlist_id, ["AAPL", "MSFT"])
        assert len(added) == 2
        
        # Get metrics (should read from stock_price table)
        metrics = get_watchlist_stocks_with_metrics(watchlist.watchlist_id)
        
        assert len(metrics) == 2
        assert any(m["ticker"] == "AAPL" for m in metrics)
        assert any(m["ticker"] == "MSFT" for m in metrics)
        
        # Verify each metric has required fields
        for metric in metrics:
            assert "ticker" in metric
            assert "current_price" in metric
            assert "sma_50" in metric
            assert "sma_200" in metric
            assert "devstep" in metric
            assert "signal" in metric
            assert "current_price_formatted" in metric
            assert "sma_50_formatted" in metric
            assert "sma_200_formatted" in metric
            assert "dividend_yield_formatted" in metric
    
    def test_get_metrics_with_stock_no_price_data(self):
        """Test getting metrics when stock exists but has no price data."""
        watchlist = create_watchlist("Test WatchList")
        
        # Manually add stock without fetching prices
        with Session(engine) as session:
            from app.models.watchlist import WatchListStock
            stock = WatchListStock(
                watchlist_id=watchlist.watchlist_id,
                ticker="TEST",
                date_added=datetime.now()
            )
            session.add(stock)
            session.commit()
        
        # Get metrics (should show error for missing price data)
        metrics = get_watchlist_stocks_with_metrics(watchlist.watchlist_id)
        
        assert len(metrics) == 1
        assert metrics[0]["ticker"] == "TEST"
        assert "error" in metrics[0]
    
    def test_get_metrics_includes_earnings_data(self):
        """Test that get_watchlist_stocks_with_metrics includes earnings data."""
        from datetime import date, timedelta
        from app.services.stock_price_service import update_stock_attributes
        from tests.conftest import populate_test_stock_prices
        
        watchlist = create_watchlist("Test WatchList")
        ticker = "AAPL"
        
        # Populate test data
        populate_test_stock_prices(ticker)
        
        # Add stock to watchlist
        with Session(engine) as session:
            from app.models.watchlist import WatchListStock
            stock = WatchListStock(
                watchlist_id=watchlist.watchlist_id,
                ticker=ticker,
                date_added=datetime.now()
            )
            session.add(stock)
            session.commit()
        
        # Set earnings date in attributes
        future_date = date.today() + timedelta(days=30)
        update_stock_attributes(
            ticker,
            earliest_date=date.today() - timedelta(days=365),
            latest_date=date.today(),
            next_earnings_date=future_date,
            is_earnings_date_estimate=True
        )
        
        # Get metrics
        metrics = get_watchlist_stocks_with_metrics(watchlist.watchlist_id)
        
        assert len(metrics) == 1
        assert metrics[0]["ticker"] == ticker
        assert "next_earnings_date" in metrics[0]
        assert "is_earnings_date_estimate" in metrics[0]
        assert metrics[0]["next_earnings_date"] == future_date
        assert metrics[0]["is_earnings_date_estimate"] is True


class TestUUIDStringCompatibility:
    """
    Regression tests for UUID vs string compatibility.

    These tests verify that ownership checks work correctly when:
    - Database stores account_id as UUID type (PostgreSQL)
    - Session/code passes account_id as string

    This bug was introduced when we changed model types from UUID to str,
    but existing production data still had UUID types that SQLAlchemy
    returns as UUID objects (bypassing model validators).
    """

    def _create_test_account(self, account_id_str: str):
        """Helper to create a test account for foreign key constraints."""
        from app.models.account import Account
        with Session(engine) as session:
            account = Account(
                id=account_id_str,
                email=f"test-{account_id_str[:8]}@example.com",
                google_sub=f"google-{account_id_str[:8]}"
            )
            session.add(account)
            session.commit()

    def test_get_watchlist_with_uuid_account_id_in_db(self):
        """
        Regression test: Verify ownership check works when database has UUID
        but code passes string account_id.

        Simulates production scenario where:
        1. Existing watchlist has account_id stored as UUID in PostgreSQL
        2. User session provides account_id as string
        3. Ownership check should still pass (same value, different types)
        """
        from uuid import uuid4

        account_id_str = str(uuid4())
        watchlist_id = str(uuid4())

        # Create account first (for foreign key constraint)
        self._create_test_account(account_id_str)

        # Create watchlist with account_id
        with Session(engine) as session:
            watchlist = WatchList(
                watchlist_id=watchlist_id,
                watchlist_name="Test Watchlist",
                account_id=account_id_str
            )
            session.add(watchlist)
            session.commit()

        # Access watchlist using STRING account_id (like session would provide)
        # This should NOT raise "Access denied" error
        result = get_watchlist(watchlist_id, account_id=account_id_str)

        assert result is not None
        assert result.watchlist_id == watchlist_id
        assert result.watchlist_name == "Test Watchlist"

    def test_get_watchlist_wrong_account_still_denied(self):
        """Verify that access is still denied for wrong account after the fix."""
        from uuid import uuid4

        owner_account_id = str(uuid4())
        other_account_id = str(uuid4())

        # Create both accounts (for foreign key constraint)
        self._create_test_account(owner_account_id)
        self._create_test_account(other_account_id)

        # Create watchlist owned by one account
        watchlist = create_watchlist("Test Watchlist", account_id=owner_account_id)

        # Try to access with different account - should be denied
        with pytest.raises(ValueError, match="Access denied"):
            get_watchlist(watchlist.watchlist_id, account_id=other_account_id)

    def test_update_watchlist_with_uuid_account_id_in_db(self):
        """Regression test: Verify update works with UUID in db, string in code."""
        from uuid import uuid4

        account_id_str = str(uuid4())

        # Create account first (for foreign key constraint)
        self._create_test_account(account_id_str)

        # Create watchlist
        watchlist = create_watchlist("Original Name", account_id=account_id_str)

        # Update using string account_id - should work
        updated = update_watchlist_name(
            watchlist.watchlist_id,
            "Updated Name",
            account_id=account_id_str
        )

        assert updated.watchlist_name == "Updated Name"

    def test_delete_stock_with_uuid_account_id_in_db(self):
        """Regression test: Verify delete stock works with UUID in db, string in code."""
        from uuid import uuid4
        from tests.conftest import populate_test_stock_prices

        account_id_str = str(uuid4())

        # Create account first (for foreign key constraint)
        self._create_test_account(account_id_str)

        # Create watchlist and add stock
        watchlist = create_watchlist("Test Watchlist", account_id=account_id_str)
        populate_test_stock_prices("AAPL")
        add_stocks_to_watchlist(watchlist.watchlist_id, ["AAPL"], account_id=account_id_str)

        # Remove stock using string account_id - should work
        result = remove_stock_from_watchlist(
            watchlist.watchlist_id,
            "AAPL",
            account_id=account_id_str
        )

        assert result is True

        # Verify stock is removed
        stocks = get_watchlist_stocks(watchlist.watchlist_id)
        assert len(stocks) == 0
