"""Tests for watchlist models."""
import pytest
from datetime import datetime
from uuid import uuid4
from app.models.watchlist import WatchList, WatchListStock
from app.database import engine, create_db_and_tables
from sqlmodel import Session


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables before each test."""
    create_db_and_tables()
    yield
    # Cleanup: delete all entries after each test
    with Session(engine) as session:
        from sqlmodel import select
        statement = select(WatchListStock)
        all_stocks = session.exec(statement).all()
        for stock in all_stocks:
            session.delete(stock)
        
        statement = select(WatchList)
        all_portfolios = session.exec(statement).all()
        for watchlist in all_portfolios:
            session.delete(watchlist)
        
        session.commit()


class TestWatchList:
    """Tests for WatchList model."""
    
    def test_create_watchlist(self):
        """Test creating a watchlist."""
        with Session(engine) as session:
            watchlist = WatchList(
                watchlist_name="Test WatchList",
                date_added=datetime.now(),
                date_modified=datetime.now()
            )
            session.add(watchlist)
            session.commit()
            session.refresh(watchlist)
            
            assert watchlist.watchlist_id is not None
            assert watchlist.watchlist_name == "Test WatchList"
            assert isinstance(watchlist.date_added, datetime)
            assert isinstance(watchlist.date_modified, datetime)
    
    def test_watchlist_name_max_length(self):
        """Test watchlist name respects max length."""
        with Session(engine) as session:
            # 128 characters should work
            long_name = "A" * 128
            watchlist = WatchList(
                watchlist_name=long_name,
                date_added=datetime.now(),
                date_modified=datetime.now()
            )
            session.add(watchlist)
            session.commit()
            session.refresh(watchlist)
            
            assert len(watchlist.watchlist_name) == 128


class TestWatchListStock:
    """Tests for WatchListStock model."""
    
    def test_create_portfolio_stock(self):
        """Test creating a watchlist stock."""
        with Session(engine) as session:
            # Create watchlist first
            watchlist = WatchList(
                watchlist_name="Test WatchList",
                date_added=datetime.now(),
                date_modified=datetime.now()
            )
            session.add(watchlist)
            session.commit()
            session.refresh(watchlist)
            
            # Create watchlist stock
            stock = WatchListStock(
                watchlist_id=watchlist.watchlist_id,
                ticker="AAPL",
                date_added=datetime.now()
            )
            session.add(stock)
            session.commit()
            session.refresh(stock)
            
            assert stock.watchlist_id == watchlist.watchlist_id
            assert stock.ticker == "AAPL"
            assert isinstance(stock.date_added, datetime)
    
    def test_portfolio_stock_composite_key(self):
        """Test that watchlist_id and ticker form composite primary key."""
        with Session(engine) as session:
            # Create watchlist
            watchlist = WatchList(
                watchlist_name="Test WatchList",
                date_added=datetime.now(),
                date_modified=datetime.now()
            )
            session.add(watchlist)
            session.commit()
            session.refresh(watchlist)
            
            # Create first stock
            stock1 = WatchListStock(
                watchlist_id=watchlist.watchlist_id,
                ticker="AAPL",
                date_added=datetime.now()
            )
            session.add(stock1)
            session.commit()
            
            # Try to create duplicate (same watchlist_id and ticker)
            # This should fail due to primary key constraint
            stock2 = WatchListStock(
                watchlist_id=watchlist.watchlist_id,
                ticker="AAPL",
                date_added=datetime.now()
            )
            session.add(stock2)
            
            with pytest.raises(Exception):  # Should raise integrity error
                session.commit()
