"""Tests for stock service module."""
import pytest
import pandas as pd
from datetime import datetime, timedelta
from app.services.stock_service import (
    fetch_stock_data,
    fetch_intraday_data,
    calculate_sma,
    calculate_devstep,
    calculate_signal,
    calculate_5day_price_movement
)


class TestCalculateSMA:
    """Tests for calculate_sma function."""
    
    def test_sma_with_sufficient_data(self):
        """Test SMA calculation with sufficient data points."""
        # Create sample data with 100 days
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        prices = pd.Series(range(100, 200), index=dates)
        data = pd.DataFrame({'Close': prices})
        
        sma_50 = calculate_sma(data, 50)
        # SMA of last 50 values: (150+151+...+199)/50 = 174.5
        expected = sum(range(150, 200)) / 50
        assert sma_50 == pytest.approx(expected, rel=1e-2)
    
    def test_sma_with_insufficient_data(self):
        """Test SMA calculation when data points are less than window."""
        dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
        prices = pd.Series(range(100, 130), index=dates)
        data = pd.DataFrame({'Close': prices})
        
        sma_50 = calculate_sma(data, 50)
        # Should use all available data (30 points)
        expected = sum(range(100, 130)) / 30
        assert sma_50 == pytest.approx(expected, rel=1e-2)


class TestCalculateDevstep:
    """Tests for calculate_devstep function."""
    
    def test_devstep_calculation(self):
        """Test devstep calculation."""
        # Create sample data
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        prices = pd.Series([100.0] * 100, index=dates)  # Constant price
        data = pd.DataFrame({'Close': prices})
        
        sma_50 = 100.0
        devstep = calculate_devstep(data, sma_50)
        
        # With constant prices, std dev is 0, so devstep should be 0
        assert devstep == pytest.approx(0.0, abs=1e-6)
    
    def test_devstep_with_variation(self):
        """Test devstep with price variation."""
        import numpy as np
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        # Create prices with variation - gradually increasing with some noise
        np.random.seed(42)  # For reproducibility
        base_prices = [100.0 + i * 0.1 + np.random.normal(0, 1) for i in range(100)]
        prices = pd.Series(base_prices, index=dates)
        data = pd.DataFrame({'Close': prices})
        
        sma_50 = data['Close'].tail(50).mean()
        devstep = calculate_devstep(data, sma_50)
        
        # With variation, devstep should be a valid number (not NaN or inf)
        assert not (pd.isna(devstep) or np.isinf(devstep))
        assert isinstance(devstep, (int, float))


class TestCalculateSignal:
    """Tests for calculate_signal function."""
    
    def test_signal_neutral(self):
        """Test signal calculation for neutral range."""
        assert calculate_signal(0.0) == "Neutral"
        assert calculate_signal(0.5) == "Neutral"
        assert calculate_signal(-0.5) == "Neutral"
        assert calculate_signal(1.0) == "Neutral"
        assert calculate_signal(-1.0) == "Neutral"
    
    def test_signal_overbought(self):
        """Test signal calculation for overbought range."""
        assert calculate_signal(1.5) == "Overbought"
        assert calculate_signal(2.0) == "Overbought"
    
    def test_signal_extreme_overbought(self):
        """Test signal calculation for extreme overbought."""
        assert calculate_signal(2.1) == "Extreme Overbought"
        assert calculate_signal(3.0) == "Extreme Overbought"
    
    def test_signal_oversold(self):
        """Test signal calculation for oversold range."""
        assert calculate_signal(-1.5) == "Oversold"
        assert calculate_signal(-2.0) == "Oversold"
    
    def test_signal_extreme_oversold(self):
        """Test signal calculation for extreme oversold."""
        assert calculate_signal(-2.1) == "Extreme Oversold"
        assert calculate_signal(-3.0) == "Extreme Oversold"


class TestFetchStockData:
    """Tests for fetch_stock_data function."""
    
    def test_fetch_valid_ticker(self):
        """Test fetching data for a valid ticker."""
        # Use a well-known ticker like AAPL
        data = fetch_stock_data("AAPL")
        
        assert isinstance(data, pd.DataFrame)
        assert not data.empty
        assert 'Close' in data.columns
    
    def test_fetch_invalid_ticker(self):
        """Test fetching data for an invalid ticker."""
        with pytest.raises(ValueError, match="No data found|Error fetching"):
            fetch_stock_data("INVALIDTICKER12345")
    
    def test_fetch_stock_data_includes_intraday_if_available(self):
        """Test that fetch_stock_data includes intraday data for today if available."""
        # Fetch data for a well-known ticker
        data = fetch_stock_data("AAPL")
        
        assert isinstance(data, pd.DataFrame)
        assert not data.empty
        assert 'Close' in data.columns
        
        # Check if we have intraday data (timestamps with time components)
        # Intraday data will have hour/minute components, daily data won't
        last_timestamp = pd.Timestamp(data.index[-1])
        has_intraday = last_timestamp.hour != 0 or last_timestamp.minute != 0
        
        # If market is open, we should have intraday data
        # If market is closed, we might not have it
        # So we just verify the data structure is correct
        if has_intraday:
            # We have intraday data - verify it's for today
            today = datetime.now().date()
            assert last_timestamp.date() == today, "Intraday data should be for today"
        
        # Verify the data has the expected columns
        assert all(col in data.columns for col in ['Open', 'High', 'Low', 'Close', 'Volume'])
    
    def test_fetch_intraday_data(self):
        """Test fetching intraday data for current day."""
        # Try to fetch intraday data
        intraday = fetch_intraday_data("AAPL")
        
        # Intraday data may or may not be available depending on market hours
        if intraday is not None:
            assert isinstance(intraday, pd.DataFrame)
            assert not intraday.empty
            assert 'Close' in intraday.columns
            
            # Verify it's for today
            today = datetime.now().date()
            intraday_dates = set([pd.Timestamp(ts).date() for ts in intraday.index])
            assert today in intraday_dates, "Intraday data should be for today"
            
            # Verify timestamps have time components
            has_time = any(
                pd.Timestamp(ts).hour != 0 or pd.Timestamp(ts).minute != 0 
                for ts in intraday.index
            )
            assert has_time, "Intraday data should have time components"


class TestCalculate5DayPriceMovement:
    """Tests for calculate_5day_price_movement function."""
    
    def test_5day_movement_calculation(self):
        """Test 5-day price movement calculation."""
        # Create sample data with enough days
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        prices = pd.Series([100.0 + i * 0.1 for i in range(100)], index=dates)
        data = pd.DataFrame({'Close': prices})
        
        sma_50 = 105.0
        movement, is_positive = calculate_5day_price_movement(data, sma_50)
        
        # Should return valid values
        assert isinstance(movement, (int, float))
        assert isinstance(is_positive, bool)
        import numpy as np
        assert not (pd.isna(movement) or np.isinf(movement))

