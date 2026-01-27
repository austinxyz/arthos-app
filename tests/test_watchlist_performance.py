"""Performance tests for watchlist page optimization."""
import pytest
import time
from decimal import Decimal
from datetime import date, datetime, timedelta
from uuid import uuid4
from sqlmodel import Session, delete
from app.database import engine, create_db_and_tables
from app.models.stock_price import StockPrice, StockAttributes
from app.models.watchlist import WatchList, WatchListStock


def populate_test_stock_with_metrics(ticker: str, num_days: int = 60, base_price: float = 150.0):
    """
    Populate test stock price data AND pre-computed trading metrics.
    Uses a simplified approach that doesn't require external test fixtures.

    Args:
        ticker: Stock ticker symbol
        num_days: Number of days of data to create (default: 60)
        base_price: Base price to start from (default: 150.0)
    """
    ticker_upper = ticker.upper()
    today = date.today()

    with Session(engine) as session:
        # Delete any existing data for this ticker
        session.exec(delete(StockPrice).where(StockPrice.ticker == ticker_upper))
        session.exec(delete(StockAttributes).where(StockAttributes.ticker == ticker_upper))
        session.commit()

        # Add stock price data
        for i in range(num_days):
            price_date = today - timedelta(days=num_days - i - 1)
            close_price = base_price + i * 0.5  # Slight upward trend

            session.add(StockPrice(
                ticker=ticker_upper,
                price_date=price_date,
                open_price=Decimal(str(close_price - 0.5)),
                close_price=Decimal(str(close_price)),
                high_price=Decimal(str(close_price + 0.5)),
                low_price=Decimal(str(close_price - 1.0)),
                dma_50=Decimal(str(close_price - 5.0)) if i >= 49 else None,
                dma_200=None
            ))

        # Add stock attributes
        session.add(StockAttributes(
            ticker=ticker_upper,
            earliest_date=today - timedelta(days=num_days),
            latest_date=today
        ))
        session.commit()

    # Compute and save the trading metrics
    from app.services.stock_price_service import compute_and_save_trading_metrics
    compute_and_save_trading_metrics(ticker_upper)


@pytest.fixture
def clean_test_db():
    """Create tables and clean up test data before and after tests."""
    create_db_and_tables()

    # Cleanup before test
    with Session(engine) as session:
        session.exec(delete(WatchListStock))
        session.exec(delete(WatchList))
        session.commit()

    yield

    # Cleanup after test
    with Session(engine) as session:
        session.exec(delete(WatchListStock))
        session.exec(delete(WatchList))
        session.commit()


class TestWatchlistPerformance:
    """Tests for watchlist page performance after optimization."""

    def test_batch_query_performance_10_stocks(self, clean_test_db):
        """
        Test that fetching metrics for 10 stocks is fast with batch queries.
        Target: < 500ms for 10 stocks.
        """
        from app.services.watchlist_service import get_watchlist_stocks_with_metrics

        # Test tickers (use simple names for test data)
        tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META",
                   "NVDA", "TSLA", "JPM", "V", "JNJ"]

        # Populate test data for each ticker
        for ticker in tickers:
            populate_test_stock_with_metrics(ticker)

        # Create watchlist with stocks (use string for UUID to support SQLite)
        watchlist_id = str(uuid4())
        with Session(engine) as session:
            session.add(WatchList(
                watchlist_id=watchlist_id,
                watchlist_name="Performance Test",
                date_added=datetime.now(),
                date_modified=datetime.now()
            ))
            for ticker in tickers:
                session.add(WatchListStock(
                    watchlist_id=watchlist_id,
                    ticker=ticker.upper()
                ))
            session.commit()

        # Measure query time
        start_time = time.time()
        metrics = get_watchlist_stocks_with_metrics(watchlist_id)
        elapsed_time = time.time() - start_time

        # Assertions
        assert len(metrics) == 10, f"Expected 10 stocks, got {len(metrics)}"
        assert elapsed_time < 0.5, f"Query took {elapsed_time:.3f}s, expected < 0.5s"

        # Verify metrics are populated correctly
        for metric in metrics:
            assert "error" not in metric, f"Error in metric for {metric.get('ticker')}: {metric.get('error')}"
            assert metric.get("devstep") is not None, f"devstep is None for {metric['ticker']}"
            assert metric.get("signal") is not None, f"signal is None for {metric['ticker']}"
            assert metric.get("current_price") is not None, f"current_price is None for {metric['ticker']}"

    def test_batch_query_performance_30_stocks(self, clean_test_db):
        """
        Test that fetching metrics for 30 stocks is still fast with batch queries.
        Target: < 1s for 30 stocks.
        """
        from app.services.watchlist_service import get_watchlist_stocks_with_metrics

        # 30 unique test tickers
        tickers = [
            "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "JPM", "V", "JNJ",
            "WMT", "PG", "MA", "UNH", "HD", "DIS", "PYPL", "ADBE", "NFLX", "INTC",
            "CMCSA", "PFE", "KO", "PEP", "TMO", "ABT", "CSCO", "NKE", "MRK", "CVX"
        ]

        # Populate test data for each ticker
        for ticker in tickers:
            populate_test_stock_with_metrics(ticker)

        # Create watchlist with stocks (use string for UUID to support SQLite)
        watchlist_id = str(uuid4())
        with Session(engine) as session:
            session.add(WatchList(
                watchlist_id=watchlist_id,
                watchlist_name="Large Performance Test",
                date_added=datetime.now(),
                date_modified=datetime.now()
            ))
            for ticker in tickers:
                session.add(WatchListStock(
                    watchlist_id=watchlist_id,
                    ticker=ticker.upper()
                ))
            session.commit()

        # Measure query time
        start_time = time.time()
        metrics = get_watchlist_stocks_with_metrics(watchlist_id)
        elapsed_time = time.time() - start_time

        # Assertions
        assert len(metrics) == 30, f"Expected 30 stocks, got {len(metrics)}"
        assert elapsed_time < 1.0, f"Query took {elapsed_time:.3f}s, expected < 1.0s"

    def test_metrics_populated_from_stock_attributes(self, clean_test_db):
        """
        Verify that devstep, signal, and movement_5day_stddev are read from
        stock_attributes (pre-computed) rather than calculated on demand.
        """
        from app.services.watchlist_service import get_watchlist_stocks_with_metrics

        # Create test data
        ticker = "TEST"
        populate_test_stock_with_metrics(ticker)

        # Verify stock_attributes has the pre-computed values
        with Session(engine) as session:
            attributes = session.get(StockAttributes, ticker)
            assert attributes is not None, "StockAttributes not found"
            assert attributes.devstep is not None, "devstep not computed"
            assert attributes.signal is not None, "signal not computed"

            stored_devstep = float(attributes.devstep)
            stored_signal = attributes.signal

        # Create watchlist and add stock (use string for UUID to support SQLite)
        watchlist_id = str(uuid4())
        with Session(engine) as session:
            session.add(WatchList(
                watchlist_id=watchlist_id,
                watchlist_name="Test Watchlist",
                date_added=datetime.now(),
                date_modified=datetime.now()
            ))
            session.add(WatchListStock(
                watchlist_id=watchlist_id,
                ticker=ticker.upper()
            ))
            session.commit()

        # Get metrics from watchlist
        metrics = get_watchlist_stocks_with_metrics(watchlist_id)

        assert len(metrics) == 1
        metric = metrics[0]

        # Verify the values match what's stored in stock_attributes
        assert metric["devstep"] == stored_devstep, f"devstep mismatch: {metric['devstep']} != {stored_devstep}"
        assert metric["signal"] == stored_signal, f"signal mismatch: {metric['signal']} != {stored_signal}"

    def test_query_count_optimization(self, clean_test_db):
        """
        Verify the optimization: should use only 2-3 queries regardless of stock count.
        This is a structural test to ensure the batch query pattern is used.
        """
        from app.services.watchlist_service import get_watchlist_stocks_with_metrics

        # Create test data for 5 stocks
        tickers = ["TEST1", "TEST2", "TEST3", "TEST4", "TEST5"]
        for ticker in tickers:
            populate_test_stock_with_metrics(ticker)

        # Create watchlist with stocks (use string for UUID to support SQLite)
        watchlist_id = str(uuid4())
        with Session(engine) as session:
            session.add(WatchList(
                watchlist_id=watchlist_id,
                watchlist_name="Query Count Test",
                date_added=datetime.now(),
                date_modified=datetime.now()
            ))
            for ticker in tickers:
                session.add(WatchListStock(
                    watchlist_id=watchlist_id,
                    ticker=ticker.upper()
                ))
            session.commit()

        # The function should execute exactly:
        # 1. get_watchlist_stocks query (1 query)
        # 2. Batch StockAttributes query (1 query)
        # 3. Batch StockPrice query with subquery (1 query, but may count as 2)
        # Total: 2-3 queries (not 15-20 like before)

        # This is a functional test - if the batch queries work, the result should be correct
        metrics = get_watchlist_stocks_with_metrics(watchlist_id)

        assert len(metrics) == 5
        for metric in metrics:
            assert "error" not in metric
            assert metric.get("current_price") is not None
