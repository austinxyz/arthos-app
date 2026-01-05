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
    get_stock_metrics
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


class TestGetStockMetrics:
    """Tests for get_stock_metrics function."""
    
    def test_get_metrics_valid_ticker(self):
        """Test getting metrics for a valid ticker."""
        metrics = get_stock_metrics("AAPL")
        
        assert isinstance(metrics, dict)
        assert "ticker" in metrics
        assert "sma_50" in metrics
        assert "sma_200" in metrics
        assert "devstep" in metrics
        assert "signal" in metrics
        assert "current_price" in metrics
        assert "data_points" in metrics
        
        # Verify signal is one of the expected values
        assert metrics["signal"] in [
            "Neutral", "Overbought", "Extreme Overbought",
            "Oversold", "Extreme Oversold"
        ]
        
        # Verify numeric values are reasonable
        assert metrics["sma_50"] > 0
        assert metrics["sma_200"] > 0
        assert metrics["current_price"] > 0
        assert metrics["data_points"] > 0
    
    def test_current_price_uses_latest_data(self):
        """Test that current price uses the latest available data (intraday if available)."""
        # Get metrics which should use latest data point
        metrics = get_stock_metrics("AAPL")
        
        # Fetch the raw data to verify
        data = fetch_stock_data("AAPL")
        latest_price = float(data['Close'].iloc[-1])
        latest_price_rounded = round(latest_price, 2)
        
        # Current price should match the latest data point (accounting for rounding)
        assert abs(metrics["current_price"] - latest_price_rounded) < 0.01, \
            f"Current price {metrics['current_price']} should match rounded latest data point {latest_price_rounded} (raw: {latest_price})"
        
        # If we have intraday data, the latest price should be from today
        last_timestamp = pd.Timestamp(data.index[-1])
        if last_timestamp.hour != 0 or last_timestamp.minute != 0:
            # We have intraday data
            today = datetime.now().date()
            assert last_timestamp.date() == today, \
                "If intraday data exists, it should be for today"
    
    def test_get_metrics_invalid_ticker(self):
        """Test getting metrics for an invalid ticker."""
        with pytest.raises(ValueError):
            get_stock_metrics("INVALIDTICKER12345")
    
    def test_ticker_case_insensitive(self):
        """Test that ticker is converted to uppercase."""
        metrics = get_stock_metrics("aapl")
        assert metrics["ticker"] == "AAPL"


class TestTSLADebug:
    """Debug test for TSLA to validate SMA calculations."""
    
    def test_tsla_debug_sma_calculations(self, capsys):
        """Fetch TSLA data and print intermediate outputs to validate SMA calculations."""
        ticker = "TSLA"
        
        print(f"\n{'='*80}")
        print(f"DEBUG TEST: Fetching and validating SMA calculations for {ticker}")
        print(f"{'='*80}\n")
        
        # Fetch stock data
        print("Step 1: Fetching stock data from yfinance...")
        data = fetch_stock_data(ticker)
        print(f"✓ Data fetched successfully")
        print(f"  - Total data points: {len(data)}")
        print(f"  - Date range: {data.index.min()} to {data.index.max()}")
        print(f"  - Columns: {list(data.columns)}")
        
        # Display first and last few rows
        print(f"\n  First 5 rows:")
        print(data.head().to_string())
        print(f"\n  Last 5 rows:")
        print(data.tail().to_string())
        
        # Calculate SMAs
        print(f"\nStep 2: Calculating 50-day SMA...")
        sma_50 = calculate_sma(data, 50)
        print(f"✓ 50-day SMA calculated: ${sma_50:.2f}")
        
        # Manual calculation for validation
        last_50_prices = data['Close'].tail(50)
        manual_sma_50 = last_50_prices.mean()
        print(f"  - Last 50 closing prices count: {len(last_50_prices)}")
        print(f"  - Manual calculation: ${manual_sma_50:.2f}")
        print(f"  - Validation: {'✓ PASS' if abs(sma_50 - manual_sma_50) < 0.01 else '✗ FAIL'}")
        print(f"  - Last 50 prices range: ${last_50_prices.min():.2f} to ${last_50_prices.max():.2f}")
        print(f"  - Last 50 prices mean: ${manual_sma_50:.2f}")
        print(f"  - Last 50 prices std dev: ${last_50_prices.std():.2f}")
        
        print(f"\nStep 3: Calculating 200-day SMA...")
        sma_200 = calculate_sma(data, 200)
        print(f"✓ 200-day SMA calculated: ${sma_200:.2f}")
        
        # Manual calculation for validation
        if len(data) >= 200:
            last_200_prices = data['Close'].tail(200)
            manual_sma_200 = last_200_prices.mean()
            print(f"  - Last 200 closing prices count: {len(last_200_prices)}")
            print(f"  - Manual calculation: ${manual_sma_200:.2f}")
            print(f"  - Validation: {'✓ PASS' if abs(sma_200 - manual_sma_200) < 0.01 else '✗ FAIL'}")
            print(f"  - Last 200 prices range: ${last_200_prices.min():.2f} to ${last_200_prices.max():.2f}")
            print(f"  - Last 200 prices mean: ${manual_sma_200:.2f}")
            print(f"  - Last 200 prices std dev: ${last_200_prices.std():.2f}")
        else:
            print(f"  - Warning: Only {len(data)} data points available, using all data")
            manual_sma_200 = data['Close'].mean()
            print(f"  - Using all {len(data)} data points")
            print(f"  - Manual calculation: ${manual_sma_200:.2f}")
            print(f"  - Validation: {'✓ PASS' if abs(sma_200 - manual_sma_200) < 0.01 else '✗ FAIL'}")
        
        # Calculate devstep
        print(f"\nStep 4: Calculating devstep...")
        devstep = calculate_devstep(data, sma_50)
        print(f"✓ Devstep calculated: {devstep:.4f}")
        
        # Manual calculation for validation
        current_price = data['Close'].iloc[-1]
        recent_prices = data['Close'].tail(50) if len(data) >= 50 else data['Close']
        std_dev = recent_prices.std()
        manual_devstep = (current_price - sma_50) / std_dev if std_dev > 0 else 0.0
        print(f"  - Current price: ${current_price:.2f}")
        print(f"  - 50-day SMA: ${sma_50:.2f}")
        print(f"  - Standard deviation (last 50): ${std_dev:.2f}")
        print(f"  - Manual devstep: {manual_devstep:.4f}")
        print(f"  - Validation: {'✓ PASS' if abs(devstep - manual_devstep) < 0.0001 else '✗ FAIL'}")
        
        # Calculate signal
        print(f"\nStep 5: Calculating signal...")
        signal = calculate_signal(devstep)
        print(f"✓ Signal: {signal}")
        print(f"  - Based on devstep: {devstep:.4f}")
        
        # Get full metrics
        print(f"\nStep 6: Getting full metrics...")
        metrics = get_stock_metrics(ticker)
        print(f"✓ Full metrics retrieved")
        print(f"\n{'='*80}")
        print("FINAL METRICS SUMMARY:")
        print(f"{'='*80}")
        print(f"Ticker: {metrics['ticker']}")
        print(f"Current Price: ${metrics['current_price']:.2f}")
        print(f"50-day SMA: ${metrics['sma_50']:.2f}")
        print(f"200-day SMA: ${metrics['sma_200']:.2f}")
        print(f"Devstep: {metrics['devstep']:.4f}")
        print(f"Signal: {metrics['signal']}")
        print(f"Data Points: {metrics['data_points']}")
        print(f"Cached: {metrics['cached']}")
        if metrics.get('cache_timestamp'):
            print(f"Cache Timestamp: {metrics['cache_timestamp']}")
        print(f"{'='*80}\n")
        
        # Assertions
        assert metrics['ticker'] == ticker.upper()
        assert metrics['sma_50'] > 0
        assert metrics['sma_200'] > 0
        assert metrics['current_price'] > 0
        assert metrics['data_points'] > 0
        assert abs(metrics['sma_50'] - sma_50) < 0.01
        assert abs(metrics['sma_200'] - sma_200) < 0.01
        
        # Print captured output
        captured = capsys.readouterr()
        print(captured.out)

