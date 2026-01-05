"""Tests for stock detail API endpoint."""
import pytest
from fastapi import status


class TestStockDetailAPI:
    """Tests for /stock/{ticker} endpoint."""
    
    def test_stock_detail_page_success(self, client):
        """Test successfully loading stock detail page."""
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
        response = client.get("/stock/MSFT")
        
        assert response.status_code == status.HTTP_200_OK
        assert "stockChart" in response.text
        assert "plotly" in response.text.lower() or "Plotly" in response.text
    
    def test_stock_detail_page_contains_metrics(self, client):
        """Test that stock detail page contains metrics."""
        response = client.get("/stock/GOOGL")
        
        assert response.status_code == status.HTTP_200_OK
        assert "Current Metrics" in response.text
        assert "Current Price" in response.text
        assert "SMA 50" in response.text
        assert "SMA 200" in response.text
    
    def test_stock_detail_page_with_options_and_covered_calls(self, client):
        """Test that stock detail page loads with options data and covered calls section."""
        response = client.get("/stock/AAPL")
        
        assert response.status_code == status.HTTP_200_OK
        assert "AAPL" in response.text
        assert "Stock Details" in response.text
        
        # Check for Option Data section
        assert "Option Data" in response.text or "No options data available" in response.text
        
        # Check for Covered Calls section
        assert "Covered Calls" in response.text or "No covered call data available" in response.text
        
        # Check that page rendered without errors
        assert "Internal Server Error" not in response.text
        assert "Error" not in response.text or "Error fetching" not in response.text
    
    def test_stock_detail_page_ticker_case_insensitive(self, client):
        """Test that ticker is case-insensitive."""
        response1 = client.get("/stock/aapl")
        response2 = client.get("/stock/AAPL")
        
        assert response1.status_code == status.HTTP_200_OK
        assert response2.status_code == status.HTTP_200_OK

