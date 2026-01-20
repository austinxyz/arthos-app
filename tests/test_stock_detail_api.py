"""Tests for stock detail API endpoint."""
import pytest
from fastapi import status
from app.database import engine, create_db_and_tables
from sqlmodel import Session
from app.models.stock_price import StockPrice, StockAttributes
from tests.conftest import populate_test_stock_prices


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


class TestStockDetailAPI:
    """Tests for /stock/{ticker} endpoint."""
    
    def test_stock_detail_page_success(self, client):
        """Test successfully loading stock detail page."""
        # Populate database with test stock price data
        populate_test_stock_prices("AAPL")
        
        response = client.get("/stock/AAPL")
        
        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers["content-type"]
        assert "AAPL" in response.text
        assert "Stock Details" in response.text
    
    def test_stock_detail_page_invalid_ticker(self, client):
        """Test stock detail page with invalid ticker."""
        response = client.get("/stock/INVALIDTICKER12345")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_stock_detail_page_contains_chart(self, client):
        """Test that stock detail page contains chart container."""
        # Populate database with test stock price data
        populate_test_stock_prices("MSFT")
        
        response = client.get("/stock/MSFT")
        
        assert response.status_code == status.HTTP_200_OK
        assert "stockChart" in response.text
        assert "plotly" in response.text.lower() or "Plotly" in response.text
    
    def test_stock_detail_page_contains_metrics(self, client):
        """Test that stock detail page contains metrics."""
        # Populate database with test stock price data
        populate_test_stock_prices("GOOGL")

        response = client.get("/stock/GOOGL")

        assert response.status_code == status.HTTP_200_OK
        assert "Price & Averages" in response.text
        assert "Current Price" in response.text
        assert "SMA 50" in response.text
        assert "SMA 200" in response.text
    
    def test_stock_detail_page_with_options_and_covered_calls(self, client):
        """Test that stock detail page loads with options data and covered calls section."""
        # Populate database with test stock price data
        populate_test_stock_prices("AAPL")
        
        response = client.get("/stock/AAPL")
        
        assert response.status_code == status.HTTP_200_OK
        assert "AAPL" in response.text
        assert "Stock Details" in response.text
        
        # Check for Bootstrap tabs structure
        assert 'nav-tabs' in response.text
        assert 'option-data-tab' in response.text
        assert 'covered-calls-tab' in response.text
        assert 'tab-pane' in response.text
        assert 'data-bs-toggle="tab"' in response.text
        
        # Check for Option Data tab content
        assert "Option Data" in response.text or "No options data available" in response.text
        
        # Check for Covered Calls tab content
        assert "Covered Calls" in response.text or "No covered call data available" in response.text
        
        # Check that page rendered without errors
        assert "Internal Server Error" not in response.text
        assert "Error" not in response.text or "Error fetching" not in response.text
    
    def test_stock_detail_page_ticker_case_insensitive(self, client):
        """Test that ticker is case-insensitive."""
        # Populate database with test stock price data
        populate_test_stock_prices("AAPL")
        
        response1 = client.get("/stock/aapl")
        response2 = client.get("/stock/AAPL")
        
        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK
    
    def test_sma_values_match_between_chart_and_metrics(self, client):
        """Test that SMA 50 and SMA 200 values in metrics table match chart values."""
        from app.services.stock_price_service import get_stock_metrics_from_db
        from app.services.stock_chart_service import get_stock_chart_data
        
        ticker = "AAPL"
        
        # Populate database with test stock price data
        populate_test_stock_prices(ticker)
        
        # Get metrics (from database)
        metrics = get_stock_metrics_from_db(ticker)
        
        # Get chart data (from database)
        chart_data = get_stock_chart_data(ticker)
        
        # Extract SMA values from metrics
        metrics_sma_50 = metrics.get('sma_50')
        metrics_sma_200 = metrics.get('sma_200')
        
        # Extract SMA values from chart data
        chart_sma_50 = chart_data.get('sma_50_current')
        chart_sma_200 = chart_data.get('sma_200_current')
        
        # Verify both have values
        assert metrics_sma_50 is not None, "Metrics SMA 50 should not be None"
        assert metrics_sma_200 is not None, "Metrics SMA 200 should not be None"
        assert chart_sma_50 is not None, "Chart SMA 50 should not be None"
        assert chart_sma_200 is not None, "Chart SMA 200 should not be None"
        
        # Verify they match (within 0.01 tolerance for floating point precision)
        assert abs(metrics_sma_50 - chart_sma_50) < 0.01, \
            f"SMA 50 mismatch: metrics={metrics_sma_50}, chart={chart_sma_50}"
        assert abs(metrics_sma_200 - chart_sma_200) < 0.01, \
            f"SMA 200 mismatch: metrics={metrics_sma_200}, chart={chart_sma_200}"

