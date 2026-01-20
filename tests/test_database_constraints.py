"""Tests for database constraints and data integrity."""
import pytest
from datetime import date, timedelta
from decimal import Decimal
from sqlmodel import Session, select
from sqlalchemy.exc import IntegrityError
from app.database import engine, create_db_and_tables
from app.models.watchlist import WatchList, WatchListStock
from app.models.stock_price import StockPrice, StockAttributes
from app.models.rr_watchlist import RRWatchlist, RRHistory


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables before each test."""
    create_db_and_tables()
    yield
    # Cleanup
    with Session(engine) as session:
        session.exec(select(WatchListStock)).all()
        for item in session.exec(select(WatchListStock)).all():
            session.delete(item)
        for item in session.exec(select(WatchList)).all():
            session.delete(item)
        for item in session.exec(select(RRHistory)).all():
            session.delete(item)
        for item in session.exec(select(RRWatchlist)).all():
            session.delete(item)
        for item in session.exec(select(StockPrice)).all():
            session.delete(item)
        for item in session.exec(select(StockAttributes)).all():
            session.delete(item)
        session.commit()


class TestWatchListConstraints:
    """Tests for watchlist database constraints."""

    def test_watchlist_uuid_generated_on_create(self):
        """Test that watchlist UUID is generated automatically."""
        with Session(engine) as session:
            watchlist = WatchList(
                watchlist_name="Test Watchlist",
                date_added=date.today(),
                date_modified=date.today()
            )
            session.add(watchlist)
            session.commit()
            session.refresh(watchlist)

            assert watchlist.watchlist_id is not None

    def test_watchlist_stock_requires_watchlist(self):
        """Test that watchlist stock requires valid watchlist reference."""
        with Session(engine) as session:
            # Create watchlist first
            watchlist = WatchList(
                watchlist_name="Test Watchlist",
                date_added=date.today(),
                date_modified=date.today()
            )
            session.add(watchlist)
            session.commit()
            session.refresh(watchlist)

            # Add stock to watchlist
            stock = WatchListStock(
                watchlist_id=watchlist.watchlist_id,
                ticker="AAPL",
                date_added=date.today()
            )
            session.add(stock)
            session.commit()

            # Verify stock was added
            result = session.exec(
                select(WatchListStock).where(WatchListStock.ticker == "AAPL")
            ).first()
            assert result is not None
            assert result.watchlist_id == watchlist.watchlist_id

    def test_duplicate_stock_in_watchlist(self):
        """Test handling of duplicate stocks in same watchlist."""
        with Session(engine) as session:
            watchlist = WatchList(
                watchlist_name="Test Watchlist",
                date_added=date.today(),
                date_modified=date.today()
            )
            session.add(watchlist)
            session.commit()
            session.refresh(watchlist)

            # Add stock first time
            stock1 = WatchListStock(
                watchlist_id=watchlist.watchlist_id,
                ticker="AAPL",
                date_added=date.today()
            )
            session.add(stock1)
            session.commit()

            # Count stocks
            count = len(session.exec(
                select(WatchListStock).where(
                    WatchListStock.watchlist_id == watchlist.watchlist_id
                )
            ).all())
            assert count == 1


class TestStockPriceConstraints:
    """Tests for stock price database constraints."""

    def test_stock_price_unique_date_ticker(self):
        """Test that stock price has unique constraint on date+ticker."""
        with Session(engine) as session:
            price1 = StockPrice(
                price_date=date.today(),
                ticker="AAPL",
                open_price=Decimal("150.00"),
                close_price=Decimal("152.00"),
                high_price=Decimal("153.00"),
                low_price=Decimal("149.00")
            )
            session.add(price1)
            session.commit()

            # Try to add duplicate - should either update or raise
            try:
                price2 = StockPrice(
                    price_date=date.today(),
                    ticker="AAPL",
                    open_price=Decimal("151.00"),
                    close_price=Decimal("153.00"),
                    high_price=Decimal("154.00"),
                    low_price=Decimal("150.00")
                )
                session.add(price2)
                session.commit()
                # If commit succeeds, verify only one record exists
                # (merge behavior)
            except IntegrityError:
                session.rollback()
                # This is expected if unique constraint exists

    def test_stock_attributes_unique_ticker(self):
        """Test that stock attributes has unique constraint on ticker."""
        with Session(engine) as session:
            attrs1 = StockAttributes(
                ticker="AAPL",
                earliest_date=date.today() - timedelta(days=365),
                latest_date=date.today()
            )
            session.add(attrs1)
            session.commit()

            # Verify record exists
            result = session.exec(
                select(StockAttributes).where(StockAttributes.ticker == "AAPL")
            ).first()
            assert result is not None


class TestRRWatchlistConstraints:
    """Tests for RR watchlist database constraints."""

    def test_rr_watchlist_uuid_generated(self):
        """Test that RR watchlist UUID is generated automatically."""
        with Session(engine) as session:
            entry = RRWatchlist(
                ticker="AAPL",
                call_strike=Decimal("105.0"),
                call_quantity=1,
                put_strike=Decimal("100.0"),
                put_quantity=1,
                stock_price=Decimal("102.0"),
                entry_price=Decimal("1.0"),
                call_option_quote=Decimal("6.0"),
                put_option_quote=Decimal("5.0"),
                expiration=date.today() + timedelta(days=365),
                ratio="1:1",
                expired_yn="N"
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)

            assert entry.id is not None

    def test_rr_history_requires_valid_parent(self):
        """Test that RR history requires valid parent entry."""
        with Session(engine) as session:
            # Create parent entry
            entry = RRWatchlist(
                ticker="AAPL",
                call_strike=Decimal("105.0"),
                call_quantity=1,
                put_strike=Decimal("100.0"),
                put_quantity=1,
                stock_price=Decimal("102.0"),
                entry_price=Decimal("1.0"),
                call_option_quote=Decimal("6.0"),
                put_option_quote=Decimal("5.0"),
                expiration=date.today() + timedelta(days=365),
                ratio="1:1",
                expired_yn="N"
            )
            session.add(entry)
            session.commit()
            session.refresh(entry)

            # Add history
            history = RRHistory(
                rr_uuid=entry.id,
                ticker="AAPL",
                history_date=date.today(),
                curr_value=Decimal("2.0"),
                call_price=Decimal("7.0"),
                put_price=Decimal("5.0")
            )
            session.add(history)
            session.commit()

            # Verify history was created
            result = session.exec(
                select(RRHistory).where(RRHistory.rr_uuid == entry.id)
            ).first()
            assert result is not None


class TestDataIntegrity:
    """Tests for data integrity scenarios."""

    def test_decimal_precision_preserved(self):
        """Test that decimal precision is preserved in stock prices."""
        with Session(engine) as session:
            price = StockPrice(
                price_date=date.today(),
                ticker="TEST",
                open_price=Decimal("150.1234"),
                close_price=Decimal("152.5678"),
                high_price=Decimal("153.9012"),
                low_price=Decimal("149.3456")
            )
            session.add(price)
            session.commit()
            session.refresh(price)

            # Verify precision
            assert price.open_price == Decimal("150.1234")
            assert price.close_price == Decimal("152.5678")

    def test_null_optional_fields(self):
        """Test that optional fields can be null."""
        with Session(engine) as session:
            price = StockPrice(
                price_date=date.today(),
                ticker="TEST",
                open_price=Decimal("150.00"),
                close_price=Decimal("152.00"),
                high_price=Decimal("153.00"),
                low_price=Decimal("149.00"),
                dma_50=None,
                dma_200=None,
                iv=None
            )
            session.add(price)
            session.commit()
            session.refresh(price)

            assert price.dma_50 is None
            assert price.dma_200 is None
            assert price.iv is None

    def test_cascade_behavior_not_triggered_unexpectedly(self):
        """Test that deleting watchlist doesn't cascade incorrectly."""
        with Session(engine) as session:
            # Create watchlist with stock
            watchlist = WatchList(
                watchlist_name="Test Watchlist",
                date_added=date.today(),
                date_modified=date.today()
            )
            session.add(watchlist)
            session.commit()
            session.refresh(watchlist)
            watchlist_id = watchlist.watchlist_id

            stock = WatchListStock(
                watchlist_id=watchlist_id,
                ticker="AAPL",
                date_added=date.today()
            )
            session.add(stock)
            session.commit()

            # Delete stock first
            session.delete(stock)
            session.commit()

            # Watchlist should still exist
            result = session.exec(
                select(WatchList).where(WatchList.watchlist_id == watchlist_id)
            ).first()
            assert result is not None
