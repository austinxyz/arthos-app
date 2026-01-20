"""Tests for API endpoints."""
import pytest
from fastapi import status
from app.database import engine, create_db_and_tables
from sqlmodel import Session
from app.models.stock_price import StockPrice, StockAttributes


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables before each test."""
    create_db_and_tables()
    yield
    # Cleanup stock_price and stock_attributes tables
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


class TestStockAPI:
    """Tests for /v1/stock endpoint."""
    
    def test_get_stock_data_valid_ticker(self, client):
        """Test API endpoint with a valid ticker."""
        # Populate test data first (required since endpoint now reads from DB)
        from tests.conftest import populate_test_stock_prices
        populate_test_stock_prices("AAPL")
        
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
        assert isinstance(data["sma_50"], (int, float)) or data["sma_50"] is None
        assert isinstance(data["sma_200"], (int, float)) or data["sma_200"] is None
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
        # Populate test data first
        from tests.conftest import populate_test_stock_prices
        populate_test_stock_prices("AAPL")
        
        response_lower = client.get("/v1/stock?q=aapl")
        response_upper = client.get("/v1/stock?q=AAPL")
        
        assert response_lower.status_code == status.HTTP_200_OK
        assert response_upper.status_code == status.HTTP_200_OK
        
        # Both should return the same ticker (uppercase)
        assert response_lower.json()["ticker"] == "AAPL"
        assert response_upper.json()["ticker"] == "AAPL"
    
    def test_get_stock_data_with_whitespace(self, client):
        """Test that whitespace in ticker is handled correctly."""
        # Populate test data first
        from tests.conftest import populate_test_stock_prices
        populate_test_stock_prices("AAPL")
        
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


class TestAPIErrorHandling:
    """Tests for API error handling scenarios."""

    def test_stock_endpoint_special_characters(self, client):
        """Test API rejects tickers with special characters."""
        response = client.get("/v1/stock?q=AAP@L")

        # Should be rejected as invalid
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_404_NOT_FOUND
        ]

    def test_stock_endpoint_numeric_ticker(self, client):
        """Test API handles numeric-only tickers."""
        response = client.get("/v1/stock?q=12345")

        # Should be rejected
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ]

    def test_stock_endpoint_very_long_ticker(self, client):
        """Test API handles excessively long ticker symbols."""
        long_ticker = "A" * 100
        response = client.get(f"/v1/stock?q={long_ticker}")

        # Should be rejected
        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ]

    def test_results_page_no_tickers(self, client):
        """Test results page with no tickers parameter."""
        response = client.get("/results")

        # API returns 422 when tickers parameter is missing
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_results_page_empty_tickers(self, client):
        """Test results page with empty tickers."""
        response = client.get("/results?tickers=")

        # API returns 400 when tickers is empty
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_nonexistent_endpoint(self, client):
        """Test 404 for non-existent endpoints."""
        response = client.get("/v1/nonexistent")

        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_method_not_allowed_stock_post(self, client):
        """Test POST method not allowed on GET-only endpoint."""
        response = client.post("/v1/stock", json={"ticker": "AAPL"})

        assert response.status_code == status.HTTP_405_METHOD_NOT_ALLOWED

    def test_stock_endpoint_sql_injection_attempt(self, client):
        """Test that SQL injection attempts are handled safely."""
        # This should not cause any errors, just be rejected as invalid ticker
        response = client.get("/v1/stock?q='; DROP TABLE stocks;--")

        assert response.status_code in [
            status.HTTP_400_BAD_REQUEST,
            status.HTTP_404_NOT_FOUND,
            status.HTTP_422_UNPROCESSABLE_ENTITY
        ]

