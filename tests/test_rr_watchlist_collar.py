"""Tests for RR Watchlist Collar functionality."""
import pytest
from uuid import UUID
from datetime import datetime, date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock
from sqlmodel import Session, select
from app.database import engine, create_db_and_tables
from app.models.rr_watchlist import RRWatchlist, RRHistory
from app.services.rr_watchlist_service import (
    save_rr_to_watchlist,
    get_all_rr_watchlist_entries,
    get_rr_history,
    delete_rr_watchlist_entry
)


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables and clean up before/after each test."""
    from app.models.account import Account
    create_db_and_tables()

    # Cleanup before test
    with Session(engine) as session:
        # Delete history first (foreign key constraint)
        statement = select(RRHistory)
        all_history = session.exec(statement).all()
        for hist in all_history:
            session.delete(hist)
        session.commit()

        # Delete watchlist entries
        statement = select(RRWatchlist)
        all_entries = session.exec(statement).all()
        for entry in all_entries:
            session.delete(entry)
        session.commit()

        # Delete accounts
        statement = select(Account)
        all_accounts = session.exec(statement).all()
        for acc in all_accounts:
            session.delete(acc)
        session.commit()

    yield

    # Cleanup after test
    with Session(engine) as session:
        statement = select(RRHistory)
        all_history = session.exec(statement).all()
        for hist in all_history:
            session.delete(hist)
        session.commit()

        statement = select(RRWatchlist)
        all_entries = session.exec(statement).all()
        for entry in all_entries:
            session.delete(entry)
        session.commit()

        statement = select(Account)
        all_accounts = session.exec(statement).all()
        for acc in all_accounts:
            session.delete(acc)
        session.commit()


def create_mock_option(strike, bid, ask, last_price=None):
    """Create a mock option object."""
    mock = MagicMock()
    mock.strike = strike
    mock.bid = bid
    mock.ask = ask
    mock.last_price = last_price or (bid + ask) / 2
    return mock


def create_mock_options_chain(puts, calls):
    """Create a mock options chain."""
    mock = MagicMock()
    mock.puts = puts
    mock.calls = calls
    return mock


class TestRRWatchlistCollar:
    """Tests for Collar functionality in RR Watchlist."""
    
    def test_save_collar_to_watchlist(self, test_user):
        """Test saving a Collar strategy to the watchlist."""
        with patch('app.services.rr_watchlist_service.ProviderFactory') as mock_provider_factory:
            # Setup mock provider
            mock_provider = MagicMock()
            mock_provider_factory.get_default_provider.return_value = mock_provider
            
            # Create mock options chain with put, call, and short call
            mock_put = create_mock_option(strike=100.0, bid=5.0, ask=5.50)
            mock_call = create_mock_option(strike=105.0, bid=3.0, ask=3.50)
            mock_short_call = create_mock_option(strike=120.0, bid=1.0, ask=1.50)
            
            mock_chain = create_mock_options_chain(
                puts=[mock_put],
                calls=[mock_call, mock_short_call]
            )
            mock_provider.fetch_options_chain.return_value = mock_chain
            
            # Save Collar
            result = save_rr_to_watchlist(
                ticker="AAPL",
                expiration="2027-01-15",
                put_strike=100.0,
                call_strike=105.0,
                ratio="Collar",
                current_price=102.0,
                sold_call_strike=120.0,
                collar_type="1:1",
                account_id=test_user.id
            )
            
            assert result["success"] is True
            assert "id" in result
            
            # Verify saved entry
            entries = get_all_rr_watchlist_entries(test_user.id)
            assert len(entries) == 1
            
            entry = entries[0]
            assert entry.account_id == test_user.id
            assert entry.ticker == "AAPL"
            assert entry.ratio == "Collar"
            assert entry.collar_type == "1:1"
            assert entry.put_strike == Decimal("100.0")
            assert entry.call_strike == Decimal("105.0")
            assert entry.short_call_strike == Decimal("120.0")
            assert entry.short_call_quantity == 1
            assert entry.call_quantity == 1
            assert entry.put_quantity == 1
            
            # Verify entry price calculation
            # Put mid: (5.0 + 5.50) / 2 = 5.25
            # Call mid: (3.0 + 3.50) / 2 = 3.25
            # Short call mid: (1.0 + 1.50) / 2 = 1.25
            # Entry price = call - put - short_call = 3.25 - 5.25 - 1.25 = -3.25
            expected_entry_price = 3.25 - 5.25 - 1.25  # -3.25
            assert float(entry.entry_price) == pytest.approx(expected_entry_price, rel=0.01)
            
            # Cleanup
            delete_rr_watchlist_entry(entry.id)
    
    @patch('app.services.rr_watchlist_service.ProviderFactory')
    def test_save_collar_1_2_to_watchlist(self, mock_provider_factory):
        """Test saving a 1:2 Collar strategy to the watchlist."""
        mock_provider = MagicMock()
        mock_provider_factory.get_default_provider.return_value = mock_provider
        
        mock_put = create_mock_option(strike=100.0, bid=8.0, ask=8.50)
        mock_call = create_mock_option(strike=105.0, bid=2.0, ask=2.50)
        mock_short_call = create_mock_option(strike=130.0, bid=0.5, ask=0.75)
        
        mock_chain = create_mock_options_chain(
            puts=[mock_put],
            calls=[mock_call, mock_short_call]
        )
        mock_provider.fetch_options_chain.return_value = mock_chain
        
        result = save_rr_to_watchlist(
            ticker="TSLA",
            expiration="2027-01-15",
            put_strike=100.0,
            call_strike=105.0,
            ratio="Collar",
            current_price=102.0,
            sold_call_strike=130.0,
            collar_type="1:2"
        )
        
        assert result["success"] is True
        
        entries = get_all_rr_watchlist_entries()
        assert len(entries) == 1
        
        entry = entries[0]
        assert entry.collar_type == "1:2"
        assert entry.call_quantity == 2
        assert entry.short_call_quantity == 2
        assert entry.put_quantity == 1
        
        # Entry price = (2 * call) - put - (2 * short_call)
        # = (2 * 2.25) - 8.25 - (2 * 0.625)
        # = 4.50 - 8.25 - 1.25 = -5.0
        put_mid = 8.25
        call_mid = 2.25
        short_call_mid = 0.625
        expected_entry_price = (2 * call_mid) - put_mid - (2 * short_call_mid)
        assert float(entry.entry_price) == pytest.approx(expected_entry_price, rel=0.01)
        
        delete_rr_watchlist_entry(entry.id)
    
    @patch('app.services.rr_watchlist_service.ProviderFactory')
    def test_save_regular_rr_still_works(self, mock_provider_factory):
        """Test that regular 1:1 and 1:2 RR still work after Collar changes."""
        mock_provider = MagicMock()
        mock_provider_factory.get_default_provider.return_value = mock_provider
        
        mock_put = create_mock_option(strike=100.0, bid=5.0, ask=5.50)
        mock_call = create_mock_option(strike=100.0, bid=6.0, ask=6.50)
        
        mock_chain = create_mock_options_chain(
            puts=[mock_put],
            calls=[mock_call]
        )
        mock_provider.fetch_options_chain.return_value = mock_chain
        
        # Test 1:1
        result = save_rr_to_watchlist(
            ticker="MSFT",
            expiration="2027-01-15",
            put_strike=100.0,
            call_strike=100.0,
            ratio="1:1",
            current_price=100.0
        )
        
        assert result["success"] is True
        
        entries = get_all_rr_watchlist_entries()
        entry = entries[0]
        assert entry.ratio == "1:1"
        assert entry.short_call_strike is None
        assert entry.short_call_quantity is None
        assert entry.collar_type is None
        
        # Entry price = call - put = 6.25 - 5.25 = 1.0
        assert float(entry.entry_price) == pytest.approx(1.0, rel=0.01)
        
        delete_rr_watchlist_entry(entry.id)


class TestSchedulerCollarUpdate:
    """Tests for scheduler updating Collar current values."""
    
    @patch('app.providers.factory.ProviderFactory.get_default_provider')
    def test_scheduler_updates_collar_current_value(self, mock_get_provider):
        """Test that scheduler correctly calculates current value for Collar."""
        from app.services.scheduler_service import update_rr_history_manual
        
        # First create a Collar entry manually in the database
        with Session(engine) as session:
            future_date = date.today() + timedelta(days=365)
            entry = RRWatchlist(
                ticker="AAPL",
                call_strike=Decimal("105.0"),
                call_quantity=1,
                put_strike=Decimal("100.0"),
                put_quantity=1,
                stock_price=Decimal("102.0"),
                entry_price=Decimal("-3.25"),
                call_option_quote=Decimal("3.25"),
                put_option_quote=Decimal("5.25"),
                expiration=future_date,
                ratio="Collar",
                expired_yn="N",
                short_call_strike=Decimal("120.0"),
                short_call_quantity=1,
                short_call_option_quote=Decimal("1.25"),
                collar_type="1:1"
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            entry_id = entry.id
        
        # Setup mock provider with updated quotes
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        
        # New prices (stock went up, calls are worth more)
        mock_put = create_mock_option(strike=100.0, bid=4.0, ask=4.50)  # mid = 4.25
        mock_call = create_mock_option(strike=105.0, bid=5.0, ask=5.50)  # mid = 5.25
        mock_short_call = create_mock_option(strike=120.0, bid=2.0, ask=2.50)  # mid = 2.25
        
        mock_chain = create_mock_options_chain(
            puts=[mock_put],
            calls=[mock_call, mock_short_call]
        )
        mock_provider.fetch_options_chain.return_value = mock_chain
        
        # Run scheduler update
        update_rr_history_manual(bypass_market_hours=True)
        
        # Verify history was created with correct current value
        history = get_rr_history(entry_id)
        assert len(history) >= 1
        
        latest_history = history[-1]
        # Current value = call - put - short_call = 5.25 - 4.25 - 2.25 = -1.25
        expected_curr_value = 5.25 - 4.25 - 2.25
        assert float(latest_history.curr_value) == pytest.approx(expected_curr_value, rel=0.01)
        assert float(latest_history.call_price) == pytest.approx(5.25, rel=0.01)
        assert float(latest_history.put_price) == pytest.approx(4.25, rel=0.01)
        assert float(latest_history.short_call_price) == pytest.approx(2.25, rel=0.01)
        
        # Cleanup
        delete_rr_watchlist_entry(entry_id)
    
    @patch('app.providers.factory.ProviderFactory.get_default_provider')
    def test_scheduler_updates_regular_rr_without_short_call(self, mock_get_provider):
        """Test that scheduler still works for regular RR (no short call)."""
        from app.services.scheduler_service import update_rr_history_manual
        
        # Create a regular 1:1 RR entry
        with Session(engine) as session:
            future_date = date.today() + timedelta(days=365)
            entry = RRWatchlist(
                ticker="MSFT",
                call_strike=Decimal("100.0"),
                call_quantity=1,
                put_strike=Decimal("100.0"),
                put_quantity=1,
                stock_price=Decimal("100.0"),
                entry_price=Decimal("1.0"),
                call_option_quote=Decimal("6.25"),
                put_option_quote=Decimal("5.25"),
                expiration=future_date,
                ratio="1:1",
                expired_yn="N"
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            entry_id = entry.id
        
        # Setup mock provider
        mock_provider = MagicMock()
        mock_get_provider.return_value = mock_provider
        
        mock_put = create_mock_option(strike=100.0, bid=4.0, ask=4.50)
        mock_call = create_mock_option(strike=100.0, bid=7.0, ask=7.50)
        
        mock_chain = create_mock_options_chain(
            puts=[mock_put],
            calls=[mock_call]
        )
        mock_provider.fetch_options_chain.return_value = mock_chain
        
        update_rr_history_manual(bypass_market_hours=True)
        
        history = get_rr_history(entry_id)
        assert len(history) >= 1
        
        latest_history = history[-1]
        # Current value = call - put = 7.25 - 4.25 = 3.0
        expected_curr_value = 7.25 - 4.25
        assert float(latest_history.curr_value) == pytest.approx(expected_curr_value, rel=0.01)
        assert latest_history.short_call_price is None  # No short call for regular RR
        
        delete_rr_watchlist_entry(entry_id)


class TestCollarModelFields:
    """Tests for Collar-specific model fields."""
    
    def test_rr_watchlist_collar_fields_optional(self):
        """Test that Collar fields are optional for regular RR."""
        with Session(engine) as session:
            future_date = date.today() + timedelta(days=365)
            entry = RRWatchlist(
                ticker="TEST",
                call_strike=Decimal("100.0"),
                call_quantity=1,
                put_strike=Decimal("100.0"),
                put_quantity=1,
                stock_price=Decimal("100.0"),
                entry_price=Decimal("1.0"),
                call_option_quote=Decimal("6.0"),
                put_option_quote=Decimal("5.0"),
                expiration=future_date,
                ratio="1:1",
                expired_yn="N"
                # Collar fields not provided - should default to None
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            
            assert entry.short_call_strike is None
            assert entry.short_call_quantity is None
            assert entry.short_call_option_quote is None
            assert entry.collar_type is None
            
            delete_rr_watchlist_entry(entry.id)
    
    def test_rr_history_short_call_price_optional(self):
        """Test that short_call_price is optional in RRHistory."""
        with Session(engine) as session:
            future_date = date.today() + timedelta(days=365)
            # Create parent entry first
            entry = RRWatchlist(
                ticker="TEST",
                call_strike=Decimal("100.0"),
                call_quantity=1,
                put_strike=Decimal("100.0"),
                put_quantity=1,
                stock_price=Decimal("100.0"),
                entry_price=Decimal("1.0"),
                call_option_quote=Decimal("6.0"),
                put_option_quote=Decimal("5.0"),
                expiration=future_date,
                ratio="1:1",
                expired_yn="N"
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)
            
            # Create history without short_call_price
            history = RRHistory(
                rr_uuid=entry.id,
                ticker="TEST",
                history_date=date.today(),
                curr_value=Decimal("2.0"),
                call_price=Decimal("7.0"),
                put_price=Decimal("5.0")
                # short_call_price not provided
            )
            session.add(history)
            session.commit()
            session.refresh(history)
            
            assert history.short_call_price is None
            
            delete_rr_watchlist_entry(entry.id)
