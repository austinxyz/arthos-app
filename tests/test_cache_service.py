"""Tests for cache service module."""
import pytest
import pandas as pd
from datetime import datetime, timedelta
from app.services.cache_service import (
    get_cached_data,
    set_cached_data,
    purge_expired_cache,
    CACHE_EXPIRY_HOURS
)
from app.models.stock_cache import StockCache
from app.database import engine, create_db_and_tables
from sqlmodel import Session


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables and clean up before and after each test."""
    create_db_and_tables()
    
    # Cleanup BEFORE test: delete all cache entries
    with Session(engine) as session:
        from sqlmodel import select
        statement = select(StockCache)
        all_entries = session.exec(statement).all()
        for entry in all_entries:
            session.delete(entry)
        session.commit()
    
    yield
    
    # Cleanup AFTER test: delete all cache entries
    with Session(engine) as session:
        from sqlmodel import select
        statement = select(StockCache)
        all_entries = session.exec(statement).all()
        for entry in all_entries:
            session.delete(entry)
        session.commit()


class TestGetCachedData:
    """Tests for get_cached_data function."""
    
    def test_get_cached_data_not_exists(self):
        """Test getting cached data when it doesn't exist."""
        result = get_cached_data("AAPL")
        assert result is None
    
    def test_get_cached_data_exists_and_valid(self):
        """Test getting cached data when it exists and is valid."""
        # Create test data
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        test_data = pd.DataFrame({
            'Close': [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0]
        }, index=dates)
        
        # Set cache
        set_cached_data("AAPL", test_data)
        
        # Get from cache
        result = get_cached_data("AAPL")
        assert result is not None
        data, cache_timestamp = result
        assert isinstance(data, pd.DataFrame)
        assert isinstance(cache_timestamp, datetime)
        assert len(data) == 10
    
    def test_get_cached_data_expired(self):
        """Test that expired cache entries are deleted."""
        # Create test data
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        test_data = pd.DataFrame({
            'Close': [100.0] * 10
        }, index=dates)
        
        # Manually create an expired cache entry
        with Session(engine) as session:
            import json
            data_dict = test_data.to_dict(orient='index')
            data_dict = {str(k): v for k, v in data_dict.items()}
            data_json = json.dumps(data_dict)
            
            expired_entry = StockCache(
                ticker="AAPL",
                data=data_json,
                cache_timestamp=datetime.now() - timedelta(hours=CACHE_EXPIRY_HOURS + 1)
            )
            session.add(expired_entry)
            session.commit()
        
        # Try to get expired cache
        result = get_cached_data("AAPL")
        assert result is None
        
        # Verify entry was deleted
        with Session(engine) as session:
            from sqlmodel import select
            statement = select(StockCache).where(StockCache.ticker == "AAPL")
            entry = session.exec(statement).first()
            assert entry is None
    
    def test_get_cached_data_case_insensitive(self):
        """Test that cache lookup is case-insensitive."""
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        test_data = pd.DataFrame({'Close': [100.0] * 10}, index=dates)
        
        set_cached_data("AAPL", test_data)
        
        # Should find cache with different case
        result = get_cached_data("aapl")
        assert result is not None


class TestSetCachedData:
    """Tests for set_cached_data function."""
    
    def test_set_cached_data_new_entry(self):
        """Test setting cache for a new ticker."""
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        test_data = pd.DataFrame({'Close': [100.0] * 10}, index=dates)
        
        set_cached_data("AAPL", test_data)
        
        # Verify entry was created
        with Session(engine) as session:
            from sqlmodel import select
            statement = select(StockCache).where(StockCache.ticker == "AAPL")
            entry = session.exec(statement).first()
            assert entry is not None
            assert entry.ticker == "AAPL"
    
    def test_set_cached_data_update_existing(self):
        """Test updating existing cache entry."""
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        test_data1 = pd.DataFrame({'Close': [100.0] * 10}, index=dates)
        test_data2 = pd.DataFrame({'Close': [200.0] * 10}, index=dates)
        
        # Set initial cache
        set_cached_data("AAPL", test_data1)
        
        # Update cache
        set_cached_data("AAPL", test_data2)
        
        # Verify only one entry exists and it's updated
        with Session(engine) as session:
            from sqlmodel import select
            statement = select(StockCache).where(StockCache.ticker == "AAPL")
            entries = session.exec(statement).all()
            assert len(entries) == 1
            # Verify timestamp was updated
            assert entries[0].cache_timestamp > datetime.now() - timedelta(seconds=5)
    
    def test_set_cached_data_case_insensitive(self):
        """Test that cache stores ticker in uppercase."""
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        test_data = pd.DataFrame({'Close': [100.0] * 10}, index=dates)
        
        set_cached_data("aapl", test_data)
        
        # Verify ticker is stored in uppercase
        with Session(engine) as session:
            from sqlmodel import select
            statement = select(StockCache).where(StockCache.ticker == "AAPL")
            entry = session.exec(statement).first()
            assert entry is not None
            assert entry.ticker == "AAPL"


class TestPurgeExpiredCache:
    """Tests for purge_expired_cache function."""
    
    def test_purge_expired_cache_no_expired(self):
        """Test purging when no expired entries exist."""
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        test_data = pd.DataFrame({'Close': [100.0] * 10}, index=dates)
        
        # Create a fresh cache entry
        set_cached_data("AAPL", test_data)
        
        # Purge expired
        count = purge_expired_cache()
        assert count == 0
        
        # Verify entry still exists
        result = get_cached_data("AAPL")
        assert result is not None
    
    def test_purge_expired_cache_with_expired(self):
        """Test purging expired cache entries."""
        dates = pd.date_range(start='2024-01-01', periods=10, freq='D')
        test_data = pd.DataFrame({'Close': [100.0] * 10}, index=dates)
        
        # Create fresh entry
        set_cached_data("AAPL", test_data)
        
        # Manually create expired entries
        with Session(engine) as session:
            import json
            data_dict = test_data.to_dict(orient='index')
            data_dict = {str(k): v for k, v in data_dict.items()}
            data_json = json.dumps(data_dict)
            
            expired1 = StockCache(
                ticker="MSFT",
                data=data_json,
                cache_timestamp=datetime.now() - timedelta(hours=CACHE_EXPIRY_HOURS + 1)
            )
            expired2 = StockCache(
                ticker="GOOGL",
                data=data_json,
                cache_timestamp=datetime.now() - timedelta(hours=CACHE_EXPIRY_HOURS + 2)
            )
            session.add(expired1)
            session.add(expired2)
            session.commit()
        
        # Purge expired
        count = purge_expired_cache()
        assert count == 2
        
        # Verify expired entries are gone
        with Session(engine) as session:
            from sqlmodel import select
            statement = select(StockCache).where(StockCache.ticker.in_(["MSFT", "GOOGL"]))
            entries = session.exec(statement).all()
            assert len(entries) == 0
        
        # Verify fresh entry still exists
        result = get_cached_data("AAPL")
        assert result is not None

