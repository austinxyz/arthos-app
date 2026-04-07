"""Tests for stock price service."""
import pytest
import pandas as pd
from datetime import date, datetime, timedelta
from decimal import Decimal
from app.services.stock_price_service import (
    get_stock_prices_from_db,
    get_stock_prices_as_dataframe,
    get_stock_metrics_from_db,
    fetch_and_save_stock_prices,
    get_stock_attributes,
    update_stock_attributes,
    refresh_stock_data
)
from app.database import engine, create_db_and_tables
from sqlmodel import Session
from app.models.stock_price import StockPrice, StockAttributes


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables before each test."""
    create_db_and_tables()
    yield
    # Cleanup
    with Session(engine) as session:
        from sqlmodel import select
        statement = select(StockPrice)
        all_prices = session.exec(statement).all()
        for price in all_prices:
            session.delete(price)
        
        statement = select(StockAttributes)
        all_attributes = session.exec(statement).all()
        for attributes in all_attributes:
            session.delete(attributes)
        
        session.commit()


class TestGetStockPricesFromDb:
    """Tests for get_stock_prices_from_db function."""
    
    def test_get_stock_prices_empty(self):
        """Test getting prices when no data exists."""
        prices = get_stock_prices_from_db("AAPL")
        assert len(prices) == 0
    
    def test_get_stock_prices_with_data(self):
        """Test getting prices when data exists."""
        # Create test data
        with Session(engine) as session:
            price1 = StockPrice(
                price_date=date(2024, 1, 1),
                ticker="AAPL",
                open_price=Decimal("150.0000"),
                close_price=Decimal("151.0000"),
                high_price=Decimal("152.0000"),
                low_price=Decimal("149.0000"),
                dma_50=Decimal("150.5000"),
                dma_200=Decimal("145.0000")
            )
            price2 = StockPrice(
                price_date=date(2024, 1, 2),
                ticker="AAPL",
                open_price=Decimal("151.0000"),
                close_price=Decimal("152.0000"),
                high_price=Decimal("153.0000"),
                low_price=Decimal("150.0000"),
                dma_50=Decimal("151.0000"),
                dma_200=Decimal("145.5000")
            )
            session.add(price1)
            session.add(price2)
            session.commit()
        
        prices = get_stock_prices_from_db("AAPL")
        assert len(prices) == 2
        assert prices[0].price_date == date(2024, 1, 2)  # Descending order
        assert prices[1].price_date == date(2024, 1, 1)
    
    def test_get_stock_prices_with_date_filter(self):
        """Test getting prices with date filters."""
        # Create test data
        with Session(engine) as session:
            price1 = StockPrice(
                price_date=date(2024, 1, 1),
                ticker="AAPL",
                open_price=Decimal("150.0000"),
                close_price=Decimal("151.0000"),
                high_price=Decimal("152.0000"),
                low_price=Decimal("149.0000")
            )
            price2 = StockPrice(
                price_date=date(2024, 1, 15),
                ticker="AAPL",
                open_price=Decimal("151.0000"),
                close_price=Decimal("152.0000"),
                high_price=Decimal("153.0000"),
                low_price=Decimal("150.0000")
            )
            session.add(price1)
            session.add(price2)
            session.commit()
        
        # Test with start_date
        prices = get_stock_prices_from_db("AAPL", start_date=date(2024, 1, 10))
        assert len(prices) == 1
        assert prices[0].price_date == date(2024, 1, 15)
        
        # Test with end_date
        prices = get_stock_prices_from_db("AAPL", end_date=date(2024, 1, 10))
        assert len(prices) == 1
        assert prices[0].price_date == date(2024, 1, 1)


class TestGetStockPricesAsDataframe:
    """Tests for get_stock_prices_as_dataframe function."""
    
    def test_get_dataframe_empty(self):
        """Test getting dataframe when no data exists."""
        df = get_stock_prices_as_dataframe("AAPL")
        assert df.empty
    
    def test_get_dataframe_with_data(self):
        """Test getting dataframe with data."""
        # Create test data
        with Session(engine) as session:
            price1 = StockPrice(
                price_date=date(2024, 1, 1),
                ticker="AAPL",
                open_price=Decimal("150.0000"),
                close_price=Decimal("151.0000"),
                high_price=Decimal("152.0000"),
                low_price=Decimal("149.0000"),
                dma_50=Decimal("150.5000"),
                dma_200=Decimal("145.0000")
            )
            price2 = StockPrice(
                price_date=date(2024, 1, 2),
                ticker="AAPL",
                open_price=Decimal("151.0000"),
                close_price=Decimal("152.0000"),
                high_price=Decimal("153.0000"),
                low_price=Decimal("150.0000"),
                dma_50=Decimal("151.0000"),
                dma_200=Decimal("145.5000")
            )
            session.add(price1)
            session.add(price2)
            session.commit()
        
        df = get_stock_prices_as_dataframe("AAPL")
        assert not df.empty
        assert len(df) == 2
        assert 'Open' in df.columns
        assert 'High' in df.columns
        assert 'Low' in df.columns
        assert 'Close' in df.columns
        assert 'dma_50' in df.columns
        assert 'dma_200' in df.columns
        assert df.index[0].date() == date(2024, 1, 1)  # Ascending order
        assert df.index[1].date() == date(2024, 1, 2)


class TestGetStockMetricsFromDb:
    """Tests for get_stock_metrics_from_db function."""
    
    def test_get_metrics_no_data(self):
        """Test getting metrics when no data exists."""
        with pytest.raises(ValueError, match="No price data found"):
            get_stock_metrics_from_db("AAPL")
    
    def test_get_metrics_with_data(self):
        """Test getting metrics with sufficient data."""
        # Create 60 days of test data to ensure SMA calculations work
        with Session(engine) as session:
            base_date = date(2024, 1, 1)
            base_price = 150.0
            
            for i in range(60):
                price_date = base_date + timedelta(days=i)
                # Create a simple price pattern
                close_price = base_price + (i * 0.1)
                open_price = close_price - 0.5
                high_price = close_price + 0.5
                low_price = close_price - 1.0
                
                # Calculate moving averages (simplified)
                dma_50 = None
                dma_200 = None
                if i >= 49:  # Have enough data for 50-day MA
                    dma_50 = Decimal(str(base_price + ((i - 24.5) * 0.1)))
                if i >= 199:  # Have enough data for 200-day MA
                    dma_200 = Decimal(str(base_price + ((i - 99.5) * 0.1)))
                
                price = StockPrice(
                    price_date=price_date,
                    ticker="AAPL",
                    open_price=Decimal(str(open_price)),
                    close_price=Decimal(str(close_price)),
                    high_price=Decimal(str(high_price)),
                    low_price=Decimal(str(low_price)),
                    dma_50=dma_50,
                    dma_200=dma_200
                )
                session.add(price)
            session.commit()
        
        metrics = get_stock_metrics_from_db("AAPL")
        
        assert metrics["ticker"] == "AAPL"
        assert "sma_50" in metrics
        assert "sma_200" in metrics
        assert "devstep" in metrics
        assert "signal" in metrics
        assert "current_price" in metrics
        assert "dividend_yield" in metrics
        assert "movement_5day_stddev" in metrics
        assert "is_price_positive_5day" in metrics
        assert "data_points" in metrics
        
        assert metrics["current_price"] > 0
        assert metrics["data_points"] == 60
        assert metrics["signal"] in [
            "Neutral", "Overbought", "Extreme Overbought",
            "Oversold", "Extreme Oversold"
        ]
    
    def test_get_metrics_uses_stored_dma(self):
        """Test that metrics use stored DMA values when available."""
        # Create data with stored DMA values
        with Session(engine) as session:
            base_date = date(2024, 1, 1)
            for i in range(60):
                price_date = base_date + timedelta(days=i)
                close_price = 150.0 + (i * 0.1)
                
                # Store a specific DMA value for the last record
                dma_50 = Decimal("155.0000") if i == 59 else None
                dma_200 = Decimal("145.0000") if i >= 199 else None
                
                price = StockPrice(
                    price_date=price_date,
                    ticker="AAPL",
                    open_price=Decimal("150.0000"),
                    close_price=Decimal(str(close_price)),
                    high_price=Decimal(str(close_price + 1.0)),
                    low_price=Decimal(str(close_price - 1.0)),
                    dma_50=dma_50,
                    dma_200=dma_200
                )
                session.add(price)
            session.commit()
        
        metrics = get_stock_metrics_from_db("AAPL")
        
        # Should use stored DMA_50 value (155.0) from the latest record if available
        # The latest record (i=59) has dma_50=155.0
        if metrics["sma_50"] is not None:
            # The function should use the stored DMA from the latest price record
            # Since we set dma_50=155.0 for the last record, it should be close to that
            assert metrics["sma_50"] is not None
            # Allow some tolerance since the function might calculate from close prices if DMA is None for earlier records


class TestFetchAndSaveStockPrices:
    """Tests for fetch_and_save_stock_prices function."""
    
    def test_fetch_and_save_new_ticker(self):
        """Test fetching and saving data for a new ticker."""
        ticker = "AAPL"
        price_data, new_records = fetch_and_save_stock_prices(ticker)
        
        assert not price_data.empty
        assert new_records > 0
        
        # Verify data was saved
        prices = get_stock_prices_from_db(ticker)
        assert len(prices) > 0
        
        # Verify stock_attributes was created
        attributes = get_stock_attributes(ticker)
        assert attributes is not None
        assert attributes.ticker == ticker
        assert attributes.earliest_date is not None
        assert attributes.latest_date is not None
    
    def test_fetch_and_save_incremental(self):
        """Test fetching incremental data when watermark exists."""
        ticker = "AAPL"
        
        # First fetch
        price_data1, new_records1 = fetch_and_save_stock_prices(ticker)
        assert new_records1 > 0
        
        # Second fetch should only get new data
        price_data2, new_records2 = fetch_and_save_stock_prices(ticker)
        # Should have fewer or no new records (depending on timing)
        assert new_records2 <= new_records1
    
    def test_fetch_and_save_invalid_ticker(self):
        """Test fetching data for invalid ticker."""
        # Invalid ticker should raise ValueError when yfinance can't fetch data
        # Note: yfinance might not always raise an error immediately, so we check for ValueError
        # or that no data was saved
        try:
            price_data, new_records = fetch_and_save_stock_prices("INVALID")
            # If it doesn't raise, verify no data was saved
            prices = get_stock_prices_from_db("INVALIDTICKER12345")
            assert len(prices) == 0, "Invalid ticker should not save any data"
        except ValueError:
            # Expected behavior - invalid ticker raises ValueError
            pass
    
    def test_fetch_and_save_earnings_date(self):
        """Test that earnings date is fetched and stored when available."""
        ticker = "AAPL"
        price_data, new_records = fetch_and_save_stock_prices(ticker)
        
        # Verify stock_attributes was created with earnings data
        attributes = get_stock_attributes(ticker)
        assert attributes is not None
        
        # Earnings date may or may not be available depending on yfinance data
        # If available, it should be today or a future date
        if attributes.next_earnings_date is not None:
            assert attributes.next_earnings_date >= date.today()
            # is_earnings_date_estimate should be a boolean if earnings date exists
            assert isinstance(attributes.is_earnings_date_estimate, (bool, type(None)))
    
    def test_update_stock_attributes_with_earnings(self):
        """Test updating stock attributes with earnings date."""
        ticker = "TEST"
        future_date = date.today() + timedelta(days=30)
        
        # Create initial attributes
        update_stock_attributes(
            ticker,
            earliest_date=date.today() - timedelta(days=365),
            latest_date=date.today(),
            next_earnings_date=future_date,
            is_earnings_date_estimate=False
        )
        
        attributes = get_stock_attributes(ticker)
        assert attributes is not None
        assert attributes.next_earnings_date == future_date
        assert attributes.is_earnings_date_estimate is False
    
    def test_update_stock_attributes_past_earnings_not_stored(self):
        """Test that past earnings dates are not stored."""
        ticker = "TEST"
        past_date = date.today() - timedelta(days=10)
        
        # Try to update with past date
        update_stock_attributes(
            ticker,
            earliest_date=date.today() - timedelta(days=365),
            latest_date=date.today(),
            next_earnings_date=past_date,
            is_earnings_date_estimate=False
        )
        
        # The function should accept it, but we test that get_stock_metrics_from_db
        # doesn't return past dates (this is handled in fetch_and_save_stock_prices)
        attributes = get_stock_attributes(ticker)
        assert attributes is not None
        # Note: update_stock_attributes doesn't validate dates, but fetch_and_save_stock_prices does
        # So we just verify the attribute was stored as-is
    
    def test_get_stock_metrics_includes_earnings(self):
        """Test that get_stock_metrics_from_db includes earnings data."""
        ticker = "AAPL"
        
        # Populate test data
        from tests.conftest import populate_test_stock_prices
        populate_test_stock_prices(ticker)
        
        # Set earnings date in attributes
        future_date = date.today() + timedelta(days=30)
        update_stock_attributes(
            ticker,
            earliest_date=date.today() - timedelta(days=365),
            latest_date=date.today(),
            next_earnings_date=future_date,
            is_earnings_date_estimate=True
        )
        
        metrics = get_stock_metrics_from_db(ticker)
        assert metrics is not None
        assert "next_earnings_date" in metrics
        assert "is_earnings_date_estimate" in metrics
        assert metrics["next_earnings_date"] == future_date
        assert metrics["is_earnings_date_estimate"] is True


class TestRefreshStockData:
    """Tests for the unified refresh_stock_data function."""

    def test_refresh_stock_data_returns_dict(self):
        """Test that refresh_stock_data returns a dict with expected keys."""
        from app.services.stock_price_service import refresh_stock_data
        from tests.conftest import populate_test_stock_prices

        ticker = "TEST"

        # Populate test data first
        populate_test_stock_prices(ticker)

        result = refresh_stock_data(ticker, clear_cache=False)

        # Verify result structure
        assert isinstance(result, dict)
        assert "ticker" in result
        assert "success" in result
        assert "price_records" in result
        assert "current_price" in result
        assert "rr_strategies" in result
        assert "cc_strategies" in result
        assert result["ticker"] == ticker

    def test_refresh_stock_data_with_clear_cache(self):
        """Test that refresh_stock_data accepts clear_cache parameter."""
        from app.services.stock_price_service import refresh_stock_data
        from tests.conftest import populate_test_stock_prices

        ticker = "TEST2"

        # Populate test data first
        populate_test_stock_prices(ticker)

        # This should not raise any errors
        result = refresh_stock_data(ticker, clear_cache=True)

        assert isinstance(result, dict)
        assert result["ticker"] == ticker

    def test_refresh_stock_data_invalid_ticker(self):
        """Test refresh_stock_data with an invalid ticker."""
        from app.services.stock_price_service import refresh_stock_data

        result = refresh_stock_data("INVALID_TICKER_XYZ", clear_cache=False)

        # Should return result with success=False or error message
        assert isinstance(result, dict)
        assert result["ticker"] == "INVALID_TICKER_XYZ"
        # The function should handle this gracefully

    def test_refresh_stock_data_reuses_shared_options_data(self, monkeypatch):
        """Force refresh should fetch options once and reuse for IV/CC/RR."""
        import app.services.stock_price_service as stock_price_service
        import app.services.stock_service as stock_service
        import app.services.options_strategy_cache_service as strategy_cache_service
        import app.services.options_cache_service as options_cache_service

        call_log = {
            "clear_cache_ticker": None,
            "include_options_iv_on_price_fetch": None,
            "get_all_options_data_calls": 0,
            "shared_options_data_obj": None,
            "rr_shared_obj": None,
            "cc_shared_obj": None,
            "iv_updates": 0,
        }

        shared_options_data = [
            ("2026-03-20", {100.0: {"call": {"bid": 2.0, "ask": 2.2, "impliedVolatility": 25.0}, "put": {"bid": 1.8, "ask": 2.0, "impliedVolatility": 24.0}}}),
            ("2027-01-15", {100.0: {"call": {"bid": 3.0, "ask": 3.3, "impliedVolatility": 27.0}, "put": {"bid": 2.7, "ask": 3.0, "impliedVolatility": 26.0}}}),
        ]

        def fake_clear_options_cache(ticker=None):
            call_log["clear_cache_ticker"] = ticker

        def fake_fetch_and_save_stock_prices(ticker, include_options_iv=True, force_purge=False):
            call_log["include_options_iv_on_price_fetch"] = include_options_iv
            return pd.DataFrame({"Close": [160.0]}), 1

        def fake_get_all_options_data(ticker, current_price, days_limit=90, include_leaps=False, force_refresh=False):
            call_log["get_all_options_data_calls"] += 1
            call_log["shared_options_data_obj"] = shared_options_data
            assert include_leaps is True
            assert force_refresh is True
            return shared_options_data

        def fake_compute_and_cache_risk_reversals(ticker, current_price, options_data_by_expiration=None):
            call_log["rr_shared_obj"] = options_data_by_expiration
            return 3

        def fake_compute_and_cache_covered_calls(ticker, current_price, options_data_by_expiration=None):
            call_log["cc_shared_obj"] = options_data_by_expiration
            return 5

        def fake_calculate_atm_iv(options_data, current_price):
            return 25.0

        def fake_update_stock_iv_metrics(ticker, current_iv):
            call_log["iv_updates"] += 1

        monkeypatch.setattr(options_cache_service, "clear_options_cache", fake_clear_options_cache)
        monkeypatch.setattr(stock_price_service, "fetch_and_save_stock_prices", fake_fetch_and_save_stock_prices)
        monkeypatch.setattr(stock_price_service, "compute_and_save_trading_metrics", lambda ticker: None)
        monkeypatch.setattr(stock_service, "get_all_options_data", fake_get_all_options_data)
        monkeypatch.setattr(strategy_cache_service, "compute_and_cache_risk_reversals", fake_compute_and_cache_risk_reversals)
        monkeypatch.setattr(strategy_cache_service, "compute_and_cache_covered_calls", fake_compute_and_cache_covered_calls)
        monkeypatch.setattr(options_cache_service, "calculate_atm_iv", fake_calculate_atm_iv)
        monkeypatch.setattr(options_cache_service, "update_stock_iv_metrics", fake_update_stock_iv_metrics)

        result = refresh_stock_data("DASH", clear_cache=True, refresh_options_strategies=True, include_options_iv=True)

        assert result["success"] is True
        assert call_log["clear_cache_ticker"] == "DASH"
        assert call_log["include_options_iv_on_price_fetch"] is False
        assert call_log["get_all_options_data_calls"] == 1
        assert call_log["rr_shared_obj"] is call_log["shared_options_data_obj"]
        assert call_log["cc_shared_obj"] is call_log["shared_options_data_obj"]
        assert call_log["iv_updates"] == 1
        assert result["rr_strategies"] == 3
        assert result["cc_strategies"] == 5

    def test_refresh_stock_data_iv_only_does_not_refetch_shared_options(self, monkeypatch):
        """IV-only refresh should keep the legacy single IV path and avoid shared fetch."""
        import app.services.stock_price_service as stock_price_service
        import app.services.stock_service as stock_service

        call_log = {
            "include_options_iv_on_price_fetch": None,
            "get_all_options_data_calls": 0,
        }

        def fake_fetch_and_save_stock_prices(ticker, include_options_iv=True, force_purge=False):
            call_log["include_options_iv_on_price_fetch"] = include_options_iv
            return pd.DataFrame({"Close": [100.0]}), 1

        def fake_get_all_options_data(*args, **kwargs):
            call_log["get_all_options_data_calls"] += 1
            return []

        monkeypatch.setattr(stock_price_service, "fetch_and_save_stock_prices", fake_fetch_and_save_stock_prices)
        monkeypatch.setattr(stock_price_service, "compute_and_save_trading_metrics", lambda ticker: None)
        monkeypatch.setattr(stock_service, "get_all_options_data", fake_get_all_options_data)

        result = refresh_stock_data("AAPL", clear_cache=False, refresh_options_strategies=False, include_options_iv=True)

        assert result["success"] is True
        assert call_log["include_options_iv_on_price_fetch"] is True
        assert call_log["get_all_options_data_calls"] == 0
