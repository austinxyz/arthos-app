"""Tests for API endpoints."""
import pytest
from fastapi import status
from app.database import create_db_and_tables


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables before each test."""
    create_db_and_tables()
    yield
    # Cleanup is handled by cache service tests if needed


class TestStockAPI:
    """Tests for /v1/stock endpoint."""
    
    def test_get_stock_data_valid_ticker(self, client):
        """Test API endpoint with a valid ticker."""
        response = client.get("/v1/stock?q=AAPL")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        # Verify response structure
        assert "ticker" in data
        assert "sma_50" in data
        assert "sma_200" in data
        assert "devstep" in data
        assert "signal" in data
        assert "current_price" in data
        assert "data_points" in data
        
        # Verify data types
        assert isinstance(data["ticker"], str)
        assert isinstance(data["sma_50"], (int, float))
        assert isinstance(data["sma_200"], (int, float))
        assert isinstance(data["devstep"], (int, float))
        assert isinstance(data["signal"], str)
        assert isinstance(data["current_price"], (int, float))
        assert isinstance(data["data_points"], int)
        
        # Verify signal is valid
        assert data["signal"] in [
            "Neutral", "Overbought", "Extreme Overbought",
            "Oversold", "Extreme Oversold"
        ]
    
    def test_get_stock_data_missing_query_param(self, client):
        """Test API endpoint without query parameter."""
        response = client.get("/v1/stock")
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    
    def test_get_stock_data_empty_query_param(self, client):
        """Test API endpoint with empty query parameter."""
        response = client.get("/v1/stock?q=")
        
        # Should return 400 or 422
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ]
    
    def test_get_stock_data_invalid_ticker(self, client):
        """Test API endpoint with invalid ticker."""
        response = client.get("/v1/stock?q=INVALIDTICKER12345")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        assert "detail" in data
    
    def test_get_stock_data_case_insensitive(self, client):
        """Test that ticker parameter is case-insensitive."""
        response_lower = client.get("/v1/stock?q=aapl")
        response_upper = client.get("/v1/stock?q=AAPL")
        
        assert response_lower.status_code == status.HTTP_200_OK
        assert response_upper.status_code == status.HTTP_200_OK
        
        # Both should return the same ticker (uppercase)
        assert response_lower.json()["ticker"] == "AAPL"
        assert response_upper.json()["ticker"] == "AAPL"
    
    def test_get_stock_data_with_whitespace(self, client):
        """Test that whitespace in ticker is handled correctly."""
        response = client.get("/v1/stock?q=  AAPL  ")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["ticker"] == "AAPL"


class TestHomeAPI:
    """Tests for homepage endpoint."""
    
    def test_home_endpoint(self, client):
        """Test homepage endpoint returns HTML."""
        response = client.get("/")
        
        assert response.status_code == status.HTTP_200_OK
        assert "text/html" in response.headers["content-type"]
        assert "Arthos" in response.text

