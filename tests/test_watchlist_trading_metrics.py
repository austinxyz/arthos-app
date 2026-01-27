
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime, date, timedelta
from app.services.watchlist_service import create_watchlist, add_stocks_to_watchlist, get_watchlist_stocks_with_metrics
from app.database import engine, create_db_and_tables
from sqlmodel import Session, select
from app.models.watchlist import WatchList, WatchListStock
from app.models.stock_price import StockPrice, StockAttributes
import pandas as pd
from decimal import Decimal

@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables before each test and clean up."""
    create_db_and_tables()
    yield
    # Cleanup
    with Session(engine) as session:
        statement = select(WatchListStock)
        for stock in session.exec(statement).all():
            session.delete(stock)
        
        statement = select(WatchList)
        for watchlist in session.exec(statement).all():
            session.delete(watchlist)
        
        statement = select(StockPrice)
        for price in session.exec(statement).all():
            session.delete(price)
        
        statement = select(StockAttributes)
        for attr in session.exec(statement).all():
            session.delete(attr)
        
        session.commit()

def test_add_stock_calculates_trading_metrics_immediately():
    """
    Regression test for the 'Neutral' trading range bug.
    Verifies that adding a stock to a watchlist immediately triggers
    calculation of trading metrics (Signal, DevStep) without needing a scheduled job.
    """
    ticker = "TEST"
    
    # Mock data setup
    today = date.today()
    base_price = 150.0
    
    # Generate 1 year of daily data to support SMA200 calculation
    dates = [today - timedelta(days=i) for i in range(365)]
    dates.reverse() # Oldest to newest
    
    data = []
    for d in dates:
        # Create a trend that puts price above SMA50 for a specific signal
        price = base_price + (dates.index(d) * 0.1)
        data.append({
            'Open': price, 
            'High': price + 1, 
            'Low': price - 1, 
            'Close': price, 
            'Volume': 1000000
        })
        
    df = pd.DataFrame(data, index=pd.to_datetime(dates))
    
    # Mock the provider to return our DataFrame
    # Note: The provider methods return List[StockPriceData], not DataFrame directly. 
    # But internally fetch_and_save_stock_prices converts them to DF or handles list.
    # Let's check stock_price_service.py... actually fetch_and_save_mock converts provider result to DF.
    # We should mock at the YFinanceProvider level which returns objects.
    
    from app.providers.base import StockPriceData
    
    mock_historical_data = []
    for row_date, row in df.iterrows():
        mock_historical_data.append(StockPriceData(
            date=row_date.date(),
            open=row['Open'],
            high=row['High'],
            low=row['Low'],
            close=row['Close'],
            volume=row['Volume']
        ))

    # Mock the provider methods
    with patch('app.providers.yfinance_provider.YFinanceProvider.fetch_historical_prices') as mock_history, \
         patch('app.providers.yfinance_provider.YFinanceProvider.fetch_intraday_prices') as mock_intraday, \
         patch('app.providers.yfinance_provider.YFinanceProvider.fetch_stock_info') as mock_info:
        
        mock_info.return_value = MagicMock(dividend_amount=0.5, dividend_yield=3.0) # StockInfo object-like
        mock_history.return_value = mock_historical_data
        mock_intraday.return_value = None # No intraday for simplicity
        
        # 1. Create a watchlist
        watchlist = create_watchlist("Metrics Test List")
        
        # 2. Add stock (this initiates the fetch and SHOULD initiate calculation)
        added, invalid = add_stocks_to_watchlist(watchlist.watchlist_id, [ticker])
        assert len(added) == 1
        
        # 3. Verify metrics are calculated immediately
        metrics = get_watchlist_stocks_with_metrics(watchlist.watchlist_id)
        
        assert len(metrics) == 1
        stock_metric = metrics[0]
        
        print(f"DEBUG: Signal found: {stock_metric.get('signal')}")
        print(f"DEBUG: DevStep found: {stock_metric.get('devstep')}")
        
        # KEY ASSERTION: Signal should NOT be "Neutral" (unless data actually dictates it, 
        # but our consistent uptrend should likely produce Overbought or similar, 
        # or at least we check it's populated).
        # Actually "Neutral" IS a valid signal if it's within range.
        # But the bug was that it was default/empty.
        # Check if 'devstep' is not None. The bug caused these to be null/None until scheduled job ran.
        
        assert stock_metric.get('signal') is not None, "Signal should be calculated"
        assert stock_metric.get('devstep') is not None, "Devstep should be calculated"
        
        # Double check directly in DB
        with Session(engine) as session:
            attrs = session.get(StockAttributes, ticker)
            assert attrs is not None
            assert attrs.signal is not None
            assert attrs.devstep is not None
            assert attrs.movement_5day_stddev is not None
