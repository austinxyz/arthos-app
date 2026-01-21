"""
Tests for pandas edge cases that can cause subtle bugs.

These tests specifically target the "truth value of a Series is ambiguous" error
and other pandas-related pitfalls that don't occur with typical data.

See: docs/learnings/pandas_and_yfinance_pitfalls.md
"""
import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock

from app.services.stock_price_service import (
    save_stock_prices,
    get_stock_attributes,
    update_stock_attributes,
)
from app.database import create_db_and_tables


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables before each test."""
    create_db_and_tables()
    yield


class TestPandasBooleanChecks:
    """Tests for proper handling of pandas boolean checks."""
    
    def test_empty_dataframe_boolean_check(self):
        """Test that empty DataFrame checks use .empty, not boolean."""
        df = pd.DataFrame()
        
        # This is the correct way
        assert df.empty is True
        
        # This would raise "truth value is ambiguous" if df had multiple rows
        # We verify the pattern works for empty case
        if df.empty:
            pass  # Should work
    
    def test_series_ambiguity_prevention(self):
        """Test that Series boolean checks are handled correctly."""
        series = pd.Series([True, False, True])
        
        # This would raise error: if series:
        # Correct patterns:
        assert series.any() is True
        assert series.all() is False
        assert len(series) > 0
        assert not series.empty
    
    def test_none_vs_empty_list_check(self):
        """Test proper checking of None vs empty list."""
        none_data = None
        empty_list = []
        data_list = [1, 2, 3]
        
        # Correct pattern for all cases
        assert none_data is None or len(none_data) == 0 if none_data else True
        assert empty_list is None or len(empty_list) == 0
        assert not (data_list is None or len(data_list) == 0)


class TestDuplicateDateHandling:
    """Tests for handling duplicate dates in DataFrame index."""
    
    def test_loc_with_duplicate_dates_returns_series(self):
        """Test that df.loc with duplicate index returns Series."""
        # Create DataFrame with duplicate date
        dates = [date(2024, 1, 1), date(2024, 1, 1), date(2024, 1, 2)]
        data = {'close': [100.0, 101.0, 102.0], 'dma_50': [99.0, 99.5, 100.0]}
        df = pd.DataFrame(data, index=dates)
        
        # With duplicate index, loc returns Series
        result = df.loc[date(2024, 1, 1), 'dma_50']
        
        # Verify it's a Series (not scalar)
        assert isinstance(result, pd.Series)
        assert len(result) == 2
        
        # Correct way to get scalar
        if isinstance(result, pd.Series):
            scalar = result.iloc[-1]
        else:
            scalar = result
        
        assert isinstance(scalar, (int, float, np.floating))
        assert scalar == 99.5
    
    def test_loc_with_unique_dates_returns_scalar(self):
        """Test that df.loc with unique index returns scalar."""
        dates = [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)]
        data = {'close': [100.0, 101.0, 102.0], 'dma_50': [99.0, 99.5, 100.0]}
        df = pd.DataFrame(data, index=dates)
        
        # With unique index, loc returns scalar
        result = df.loc[date(2024, 1, 2), 'dma_50']
        
        # Verify it's a scalar (not Series)
        assert not isinstance(result, pd.Series)
        assert isinstance(result, (int, float, np.floating))
        assert result == 99.5
    
    def test_notna_on_series_returns_series(self):
        """Test that pd.notna on Series returns Series of booleans."""
        series = pd.Series([1.0, None, 3.0])
        
        result = pd.notna(series)
        
        # pd.notna on Series returns Series of booleans
        assert isinstance(result, pd.Series)
        assert result.dtype == bool
        
        # Cannot use in if statement directly:
        # if pd.notna(series):  # This would raise error
        
        # Correct patterns:
        assert result.all() is False  # Not all values are notna
        assert result.any() is True   # Some values are notna


class TestSaveStockPricesEdgeCases:
    """Tests for save_stock_prices with edge case data."""
    
    def test_save_with_duplicate_dates_in_input(self):
        """Test saving stock prices when input has duplicate dates."""
        ticker = "TEST_DUP"
        
        # Create price_data with duplicate dates (simulating aggregated data)
        dates = pd.DatetimeIndex([
            pd.Timestamp('2024-01-15'),
            pd.Timestamp('2024-01-15'),  # Duplicate!
            pd.Timestamp('2024-01-16'),
        ])
        
        price_data = pd.DataFrame({
            'Open': [100.0, 100.5, 101.0],
            'High': [101.0, 101.5, 102.0],
            'Low': [99.0, 99.5, 100.0],
            'Close': [100.5, 101.0, 101.5],
            'Volume': [1000, 1100, 1200],
        }, index=dates)
        
        # This should NOT raise "truth value is ambiguous"
        # The function should handle duplicates gracefully
        try:
            save_stock_prices(ticker, price_data)
        except ValueError as e:
            if "ambiguous" in str(e).lower():
                pytest.fail(f"Series ambiguity error not handled: {e}")
            raise  # Re-raise other ValueErrors
    
    def test_save_with_timezone_aware_timestamps(self):
        """Test saving stock prices with timezone-aware timestamps."""
        from zoneinfo import ZoneInfo
        
        ticker = "TEST_TZ"
        et_tz = ZoneInfo("America/New_York")
        
        dates = pd.DatetimeIndex([
            pd.Timestamp('2024-01-15', tz=et_tz),
            pd.Timestamp('2024-01-16', tz=et_tz),
        ])
        
        price_data = pd.DataFrame({
            'Open': [100.0, 101.0],
            'High': [101.0, 102.0],
            'Low': [99.0, 100.0],
            'Close': [100.5, 101.5],
            'Volume': [1000, 1100],
        }, index=dates)
        
        # Should handle timezone-aware timestamps
        save_stock_prices(ticker, price_data)


class TestDataProviderReturnTypes:
    """Tests for correct handling of data provider return types."""
    
    def test_provider_returns_none(self):
        """Test handling when provider returns None."""
        data = None
        
        # Correct check pattern
        if data is None or len(data) == 0:
            result = "no data"
        else:
            result = "has data"
        
        assert result == "no data"
    
    def test_provider_returns_empty_list(self):
        """Test handling when provider returns empty list."""
        data = []
        
        # Correct check pattern
        if data is None or len(data) == 0:
            result = "no data"
        else:
            result = "has data"
        
        assert result == "no data"
    
    def test_provider_returns_data(self):
        """Test handling when provider returns data."""
        data = [{"date": date.today(), "close": 100.0}]
        
        # Correct check pattern
        if data is None or len(data) == 0:
            result = "no data"
        else:
            result = "has data"
        
        assert result == "has data"
