"""Tests for results page functionality."""
import pytest
from fastapi import status
from app.services.stock_service import get_multiple_stock_metrics
from app.database import engine, create_db_and_tables
from sqlmodel import Session
from tests.conftest import populate_test_stock_prices


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables and populate test data before each test."""
    create_db_and_tables()
    
    # Populate test data for tickers used in tests
    populate_test_stock_prices("AAPL")
    populate_test_stock_prices("MSFT")
    
    yield
    
    # Cleanup after test
    with Session(engine) as session:
        from sqlmodel import select
        from app.models.stock_price import StockPrice, StockAttributes
        
        for price in session.exec(select(StockPrice)).all():
            session.delete(price)
        for attr in session.exec(select(StockAttributes)).all():
            session.delete(attr)
        session.commit()


class TestMultipleStockMetrics:
    """Tests for get_multiple_stock_metrics function."""
    
    def test_get_multiple_stock_metrics_single_ticker(self):
        """Test getting metrics for a single ticker."""
        results = get_multiple_stock_metrics(["AAPL"])
        
        assert len(results) == 1
        assert "ticker" in results[0]
        assert results[0]["ticker"] == "AAPL"
        assert "error" not in results[0]
    
    def test_get_multiple_stock_metrics_multiple_tickers(self):
        """Test getting metrics for multiple tickers."""
        results = get_multiple_stock_metrics(["AAPL", "MSFT"])
        
        assert len(results) == 2
        assert all("ticker" in r for r in results)
        assert any(r["ticker"] == "AAPL" for r in results)
        assert any(r["ticker"] == "MSFT" for r in results)
    
    def test_get_multiple_stock_metrics_invalid_ticker(self):
        """Test handling of invalid ticker."""
        results = get_multiple_stock_metrics(["INVALIDTICKER12345"])
        
        assert len(results) == 1
        assert "error" in results[0]
        assert results[0]["ticker"] == "INVALIDTICKER12345"
    
    def test_get_multiple_stock_metrics_mixed_valid_invalid(self):
        """Test handling of mixed valid and invalid tickers."""
        results = get_multiple_stock_metrics(["AAPL", "INVALIDTICKER12345", "MSFT"])
        
        assert len(results) == 3
        # At least one should be valid
        valid_count = sum(1 for r in results if "error" not in r)
        assert valid_count >= 2  # AAPL and MSFT should be valid
    
    def test_get_multiple_stock_metrics_empty_list(self):
        """Test handling of empty ticker list."""
        results = get_multiple_stock_metrics([])
        assert len(results) == 0
    
    def test_get_multiple_stock_metrics_whitespace_handling(self):
        """Test that whitespace in tickers is handled correctly."""
        results = get_multiple_stock_metrics(["  AAPL  ", "  MSFT  "])
        
        assert len(results) == 2
        assert all(r["ticker"] in ["AAPL", "MSFT"] for r in results if "error" not in r)


class TestResultsPageAPI:
    """Tests for /results endpoint."""
    
    def test_results_page_single_ticker(self, client):
        """Test results page with single ticker."""
        response = client.get("/results?tickers=AAPL")
        
        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers["content-type"]
        assert "Stock Metrics Results" in response.text
        assert "AAPL" in response.text
    
    def test_results_page_multiple_tickers(self, client):
        """Test results page with multiple tickers."""
        response = client.get("/results?tickers=AAPL,MSFT")
        
        assert response.status_code == status.HTTP_200_OK
        assert "AAPL" in response.text
        assert "MSFT" in response.text
    
    def test_results_page_missing_tickers(self, client):
        """Test results page without tickers parameter."""
        response = client.get("/results")
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_results_page_empty_tickers(self, client):
        """Test results page with empty tickers."""
        response = client.get("/results?tickers=")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_results_page_whitespace_tickers(self, client):
        """Test results page with whitespace in tickers."""
        response = client.get("/results?tickers=  AAPL  ,  MSFT  ")
        
        assert response.status_code == status.HTTP_200_OK
        assert "AAPL" in response.text
        assert "MSFT" in response.text
    
    def test_results_page_invalid_ticker_format(self, client):
        """Test results page rejects invalid ticker formats."""
        response = client.get("/results?tickers=INVALID12345")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "Invalid ticker format" in data["detail"]
        assert "INVALID12345" in data["detail"]
    
    def test_results_page_multiple_invalid_tickers(self, client):
        """Test results page rejects multiple invalid ticker formats."""
        response = client.get("/results?tickers=TOOLONG,INVALID@")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "Invalid ticker format" in data["detail"]
    
    def test_results_page_mixed_valid_invalid_formats(self, client):
        """Test results page rejects when mix of valid and invalid formats."""
        response = client.get("/results?tickers=AAPL,INVALID12345,MSFT")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "Invalid ticker format" in data["detail"]
        assert "INVALID12345" in data["detail"]


class TestHomePage:
    """Tests for updated homepage."""
    
    def test_homepage_renders(self, client):
        """Test that homepage renders correctly."""
        response = client.get("/")
        
        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers["content-type"]
        assert "Arthos" in response.text
        assert "Enter comma-separated stock tickers" in response.text
        assert "Explore" in response.text

