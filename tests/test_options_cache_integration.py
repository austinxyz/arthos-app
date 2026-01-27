import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app
from app.models.stock_price import StockPrice, StockAttributes
from sqlmodel import Session, delete
from app.database import engine
from datetime import date

client = TestClient(app)

# Use a simple class that behaves like an object (attribute access) AND a dict (.get)
# This covers both template usage (dot notation) and python usage (.get) if mixed.
class MockStrategy(dict):
    """Mock object that supports both dict access/get AND attribute access."""
    def __getattr__(self, name):
        if name in self:
            return self[name]
        raise AttributeError(f"'MockStrategy' object has no attribute '{name}'")
    
    def __setattr__(self, name, value):
        self[name] = value

@pytest.fixture
def mock_stock_data():
    """Setup minimal stock data for the test."""
    ticker = "CACHE_TEST"
    with Session(engine) as session:
        # cleanup
        session.exec(delete(StockPrice).where(StockPrice.ticker == ticker))
        session.exec(delete(StockAttributes).where(StockAttributes.ticker == ticker))
        session.commit()
        
        # Add stock price
        sp = StockPrice(
            ticker=ticker,
            price_date=date(2025, 1, 1),
            close_price=100.0,
            volume=1000
        )
        session.add(sp)
        session.commit()
        
    yield ticker
    
    # cleanup
    with Session(engine) as session:
        session.exec(delete(StockPrice).where(StockPrice.ticker == ticker))
        session.exec(delete(StockAttributes).where(StockAttributes.ticker == ticker))
        session.commit()

def test_stock_detail_populates_cache_on_miss_covered_calls(mock_stock_data):
    """
    Regression test: Verify that cache miss triggers compute_and_cache_covered_calls.
    """
    ticker = mock_stock_data
    
    with patch("app.services.options_strategy_cache_service.get_cached_covered_calls") as mock_get_cache, \
         patch("app.services.options_strategy_cache_service.compute_and_cache_covered_calls") as mock_compute, \
         patch("app.services.stock_chart_service.get_stock_chart_data") as mock_chart, \
         patch("app.services.stock_price_service.get_stock_metrics_from_db") as mock_metrics:
        
        # Complete mock chart data
        mock_chart.return_value = {
            "candlestick_data": [],
            "volume_data": [],
            "sma_50": [],
            "sma_200": [],
            "std_bands": {
                "std_3_upper": [], "std_3_lower": [],
                "std_2_upper": [], "std_2_lower": [],
                "std_1_upper": [], "std_1_lower": []
            },
            "period": "1y",
            "current_data_timestamp": "2025-01-01"
        }
        
        mock_metrics.return_value = {
            "current_price": 100.0,
            "sma_50": 95.0,
            "sma_200": 90.0,
            "devstep": 1.0, 
            "movement_5day_stddev": 1.0,
            "stddev_50d": 1.0,
            "signal": "Neutral",
            "dividend_yield": 0.0,
            "next_earnings_date": None,
            "next_dividend_date": None,
            "current_iv": 0.25
        }
        
        # Mock strategy objects
        # Covered calls in template use dot notation largely, but to be safe use our hybrid class
        hit_data = [
            MockStrategy(
                strike=105.0, 
                expirationDate="2025-02-01", 
                callPremium=2.5,             
                returnExercised=750,
                returnPctExercised=7.5,
                annualizedReturnExercised=90.0,
                returnNotExercised=250,
                returnPctNotExercised=2.5,
                annualizedReturnNotExercised=30.0,
                stockAppreciationPct=5.0,
                callPremiumPct=2.5
            )
        ]
        
        mock_get_cache.side_effect = [
            [],      # Miss
            hit_data # Hit
        ]
        
        response = client.get(f"/stock/{ticker}")
        
        if response.status_code != 200:
            print(f"Error: {response.text}")
            
        assert response.status_code == 200
        mock_compute.assert_called_once()
        assert mock_get_cache.call_count == 2

def test_stock_detail_populates_cache_on_miss_risk_reversals(mock_stock_data):
    """
    Regression test: Verify that cache miss triggers compute_and_cache_risk_reversals.
    """
    ticker = mock_stock_data
    
    with patch("app.services.options_strategy_cache_service.get_cached_risk_reversals") as mock_get_cache, \
         patch("app.services.options_strategy_cache_service.compute_and_cache_risk_reversals") as mock_compute, \
         patch("app.services.stock_chart_service.get_stock_chart_data") as mock_chart, \
         patch("app.services.stock_price_service.get_stock_metrics_from_db") as mock_metrics:
        
        mock_chart.return_value = {
            "candlestick_data": [],
            "volume_data": [],
            "sma_50": [],
            "sma_200": [],
            "std_bands": {
                "std_3_upper": [], "std_3_lower": [],
                "std_2_upper": [], "std_2_lower": [],
                "std_1_upper": [], "std_1_lower": []
            },
            "period": "1y",
            "current_data_timestamp": "2025-01-01"
        }
        
        mock_metrics.return_value = {
            "current_price": 100.0,
            "sma_50": 95.0,
            "sma_200": 90.0,
            "devstep": 1.0, 
            "movement_5day_stddev": 1.0,
            "stddev_50d": 1.0,
            "signal": "Neutral",
            "dividend_yield": 0.0,
            "next_earnings_date": None,
            "next_dividend_date": None,
            "current_iv": 0.25
        }
        
        hit_data = {
            "2025-02-01": [
                MockStrategy(
                    put_strike=95.0,
                    call_strike=105.0,
                    put_bid=1.0,
                    put_breakeven=94.0,
                    call_ask=1.0,
                    call_breakeven=106.0,
                    strike_spread=10.0,
                    cost=0.0,
                    cost_pct=0.0,
                    ratio="1:1",
                    put_risk=9500.0,
                    put_risk_formatted="9,500.00",
                    expiration_date=date(2025, 2, 1),
                    days_to_expiration=30,
                    highlight=False
                )
            ]
        }
        
        mock_get_cache.side_effect = [
            {},      # Miss
            hit_data # Hit
        ]
        
        response = client.get(f"/stock/{ticker}")
        
        if response.status_code != 200:
            print(f"Error: {response.text}")
            
        assert response.status_code == 200
        mock_compute.assert_called_once()
        assert mock_get_cache.call_count == 2
