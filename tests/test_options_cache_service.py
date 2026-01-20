"""Tests for options cache service."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from decimal import Decimal
from app.services.options_cache_service import (
    get_cached_options_data,
    cache_options_data,
    clear_options_cache,
    calculate_atm_iv,
    update_stock_iv_metrics,
    _options_cache,
    _is_market_hours,
    _get_cache_ttl,
    CACHE_TTL_MINUTES,
    CACHE_TTL_AFTER_HOURS_MINUTES
)


@pytest.fixture(autouse=True)
def clear_cache_before_test():
    """Clear cache before each test."""
    clear_options_cache()
    yield
    clear_options_cache()


class TestOptionsCache:
    """Tests for cache operations."""

    def test_cache_and_retrieve_options_data(self):
        """Test caching and retrieving options data."""
        ticker = "AAPL"
        expiration = "2027-01-15"
        options_data = {
            100.0: {"call": {"bid": 5.0, "ask": 5.5}, "put": {"bid": 3.0, "ask": 3.5}},
            105.0: {"call": {"bid": 3.0, "ask": 3.5}, "put": {"bid": 5.0, "ask": 5.5}},
        }

        # Cache the data
        cache_options_data(ticker, expiration, options_data)

        # Retrieve from cache
        result = get_cached_options_data(ticker, expiration)

        assert result is not None
        assert result[0] == expiration
        assert result[1] == options_data

    def test_cache_miss_for_uncached_data(self):
        """Test cache miss returns None."""
        result = get_cached_options_data("MSFT", "2027-01-15")
        assert result is None

    def test_cache_is_case_insensitive(self):
        """Test that cache keys are case-insensitive for tickers."""
        expiration = "2027-01-15"
        options_data = {100.0: {"call": {"bid": 5.0}}}

        cache_options_data("aapl", expiration, options_data)
        result = get_cached_options_data("AAPL", expiration)

        assert result is not None
        assert result[1] == options_data

    def test_clear_cache_for_specific_ticker(self):
        """Test clearing cache for a specific ticker."""
        options_data = {100.0: {"call": {"bid": 5.0}}}

        cache_options_data("AAPL", "2027-01-15", options_data)
        cache_options_data("MSFT", "2027-01-15", options_data)

        clear_options_cache("AAPL")

        assert get_cached_options_data("AAPL", "2027-01-15") is None
        assert get_cached_options_data("MSFT", "2027-01-15") is not None

    def test_clear_all_cache(self):
        """Test clearing entire cache."""
        options_data = {100.0: {"call": {"bid": 5.0}}}

        cache_options_data("AAPL", "2027-01-15", options_data)
        cache_options_data("MSFT", "2027-01-15", options_data)

        clear_options_cache()

        assert get_cached_options_data("AAPL", "2027-01-15") is None
        assert get_cached_options_data("MSFT", "2027-01-15") is None

    @patch('app.services.options_cache_service._is_market_hours')
    def test_cache_expiration_during_market_hours(self, mock_market_hours):
        """Test cache expires after TTL during market hours."""
        mock_market_hours.return_value = True

        options_data = {100.0: {"call": {"bid": 5.0}}}
        cache_options_data("AAPL", "2027-01-15", options_data)

        # Manually expire the cache
        cache_key = "AAPL:2027-01-15"
        with patch.dict(_options_cache, {
            cache_key: {
                'expiration': "2027-01-15",
                'options_data': options_data,
                'cached_at': datetime.now() - timedelta(minutes=CACHE_TTL_MINUTES + 1)
            }
        }):
            result = get_cached_options_data("AAPL", "2027-01-15")
            assert result is None


class TestMarketHours:
    """Tests for market hours detection."""

    def test_is_market_hours_returns_boolean(self):
        """Test that market hours detection returns a boolean."""
        # This test verifies the function runs without error and returns bool
        result = _is_market_hours()
        assert isinstance(result, bool)

    @patch('app.services.options_cache_service._is_market_hours')
    def test_get_cache_ttl_during_market_hours(self, mock_market_hours):
        """Test TTL is shorter during market hours."""
        mock_market_hours.return_value = True
        ttl = _get_cache_ttl()
        assert ttl == timedelta(minutes=CACHE_TTL_MINUTES)

    @patch('app.services.options_cache_service._is_market_hours')
    def test_get_cache_ttl_after_hours(self, mock_market_hours):
        """Test TTL is longer after market hours."""
        mock_market_hours.return_value = False
        ttl = _get_cache_ttl()
        assert ttl == timedelta(minutes=CACHE_TTL_AFTER_HOURS_MINUTES)


class TestCalculateATMIV:
    """Tests for ATM IV calculation."""

    def test_calculate_atm_iv_at_exact_strike(self):
        """Test ATM IV calculation when price equals a strike."""
        options_data = {
            100.0: {
                "call": {"impliedVolatility": 0.30},
                "put": {"impliedVolatility": 0.32}
            }
        }
        current_price = 100.0

        iv = calculate_atm_iv(options_data, current_price)

        assert iv is not None
        assert iv == pytest.approx(0.31, rel=0.01)  # Average of 0.30 and 0.32

    def test_calculate_atm_iv_finds_closest_strike(self):
        """Test ATM IV uses closest strike to current price."""
        options_data = {
            100.0: {"call": {"impliedVolatility": 0.25}, "put": {"impliedVolatility": 0.25}},
            105.0: {"call": {"impliedVolatility": 0.30}, "put": {"impliedVolatility": 0.30}},
            110.0: {"call": {"impliedVolatility": 0.35}, "put": {"impliedVolatility": 0.35}},
        }
        current_price = 103.0  # Closest to 105

        iv = calculate_atm_iv(options_data, current_price)

        assert iv is not None
        assert iv == pytest.approx(0.30, rel=0.01)

    def test_calculate_atm_iv_with_only_call_iv(self):
        """Test ATM IV when only call IV is available."""
        options_data = {
            100.0: {
                "call": {"impliedVolatility": 0.30},
                "put": {}  # No IV for put
            }
        }

        iv = calculate_atm_iv(options_data, 100.0)

        assert iv is not None
        assert iv == pytest.approx(0.30, rel=0.01)

    def test_calculate_atm_iv_with_only_put_iv(self):
        """Test ATM IV when only put IV is available."""
        options_data = {
            100.0: {
                "call": {},
                "put": {"impliedVolatility": 0.32}
            }
        }

        iv = calculate_atm_iv(options_data, 100.0)

        assert iv is not None
        assert iv == pytest.approx(0.32, rel=0.01)

    def test_calculate_atm_iv_returns_none_for_empty_data(self):
        """Test ATM IV returns None for empty options data."""
        assert calculate_atm_iv({}, 100.0) is None
        assert calculate_atm_iv(None, 100.0) is None

    def test_calculate_atm_iv_returns_none_for_invalid_price(self):
        """Test ATM IV returns None for invalid current price."""
        options_data = {100.0: {"call": {"impliedVolatility": 0.30}}}

        assert calculate_atm_iv(options_data, 0) is None
        assert calculate_atm_iv(options_data, -10) is None

    def test_calculate_atm_iv_returns_none_when_no_iv_available(self):
        """Test ATM IV returns None when no IV data in options."""
        options_data = {
            100.0: {
                "call": {"bid": 5.0},  # No impliedVolatility
                "put": {"bid": 3.0}
            }
        }

        iv = calculate_atm_iv(options_data, 100.0)
        assert iv is None


class TestUpdateStockIVMetrics:
    """Tests for updating stock IV metrics."""

    @pytest.fixture
    def setup_stock_attributes(self):
        """Create test stock attributes."""
        from sqlmodel import Session
        from app.database import engine, create_db_and_tables
        from app.models.stock_price import StockAttributes, StockPrice
        from datetime import date, timedelta

        create_db_and_tables()

        with Session(engine) as session:
            # Clean existing data
            from sqlmodel import delete
            session.exec(delete(StockPrice).where(StockPrice.ticker == "TEST"))
            session.exec(delete(StockAttributes).where(StockAttributes.ticker == "TEST"))
            session.commit()

            # Create stock attributes
            attrs = StockAttributes(
                ticker="TEST",
                earliest_date=date.today() - timedelta(days=365),
                latest_date=date.today()
            )
            session.add(attrs)
            session.commit()

        yield

        # Cleanup
        with Session(engine) as session:
            session.exec(delete(StockPrice).where(StockPrice.ticker == "TEST"))
            session.exec(delete(StockAttributes).where(StockAttributes.ticker == "TEST"))
            session.commit()

    def test_update_stock_iv_metrics_updates_current_iv(self, setup_stock_attributes):
        """Test that current IV is updated."""
        from sqlmodel import Session, select
        from app.database import engine
        from app.models.stock_price import StockAttributes

        update_stock_iv_metrics("TEST", 35.5)

        with Session(engine) as session:
            attrs = session.exec(
                select(StockAttributes).where(StockAttributes.ticker == "TEST")
            ).first()

            assert attrs is not None
            assert attrs.current_iv == Decimal("35.5")

    def test_update_stock_iv_metrics_handles_missing_ticker(self):
        """Test graceful handling when ticker doesn't exist."""
        # Should not raise an exception
        update_stock_iv_metrics("NONEXISTENT", 35.5)
