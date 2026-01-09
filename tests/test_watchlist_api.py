"""Tests for watchlist API endpoints."""
import pytest
from fastapi import status
from uuid import UUID
from app.services.watchlist_service import create_watchlist, add_stocks_to_watchlist
from app.database import engine, create_db_and_tables
from sqlmodel import Session
from app.models.watchlist import WatchList, WatchListStock
from app.models.stock_price import StockPrice, StockAttributes


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables and clean up before and after each test."""
    create_db_and_tables()
    
    # Cleanup before test: delete all entries
    with Session(engine) as session:
        from sqlmodel import select
        statement = select(WatchListStock)
        all_stocks = session.exec(statement).all()
        for stock in all_stocks:
            session.delete(stock)
        
        statement = select(WatchList)
        all_watchlists = session.exec(statement).all()
        for watchlist in all_watchlists:
            session.delete(watchlist)
        
        # Clean stock_price tables
        statement = select(StockPrice)
        all_prices = session.exec(statement).all()
        for price in all_prices:
            session.delete(price)
        
        statement = select(StockAttributes)
        all_attributes = session.exec(statement).all()
        for attributes in all_attributes:
            session.delete(attributes)
        
        session.commit()
    
    yield
    
    # Cleanup after test: delete all entries
    with Session(engine) as session:
        from sqlmodel import select
        statement = select(WatchListStock)
        all_stocks = session.exec(statement).all()
        for stock in all_stocks:
            session.delete(stock)
        
        statement = select(WatchList)
        all_watchlists = session.exec(statement).all()
        for watchlist in all_watchlists:
            session.delete(watchlist)
        
        # Clean stock_price tables
        statement = select(StockPrice)
        all_prices = session.exec(statement).all()
        for price in all_prices:
            session.delete(price)
        
        statement = select(StockAttributes)
        all_attributes = session.exec(statement).all()
        for attributes in all_attributes:
            session.delete(attributes)
        
        session.commit()


class TestWatchListAPI:
    """Tests for /v1/watchlist endpoints."""
    
    def test_create_portfolio_success(self, client):
        """Test creating a watchlist via API."""
        response = client.post(
            "/v1/watchlist",
            json={"watchlist_name": "Test WatchList"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "watchlist_id" in data
        assert data["watchlist_name"] == "Test WatchList"
        assert "date_added" in data
        assert "date_modified" in data
    
    def test_create_portfolio_invalid_name(self, client):
        """Test creating watchlist with invalid name."""
        response = client.post(
            "/v1/watchlist",
            json={"watchlist_name": "Invalid-Name!"}
        )
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        data = response.json()
        assert "detail" in data
    
    def test_list_watchlists_empty(self, client):
        """Test listing watchlists when none exist."""
        response = client.get("/v1/watchlist")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "watchlists" in data
        assert data["watchlists"] == []
    
    def test_list_watchlists_multiple(self, client):
        """Test listing multiple watchlists."""
        # Create watchlists
        create_watchlist("WatchList 1")
        create_watchlist("WatchList 2")
        
        response = client.get("/v1/watchlist")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["watchlists"]) == 2
    
    def test_get_portfolio_success(self, client):
        """Test getting a watchlist by ID."""
        watchlist = create_watchlist("Test WatchList")
        
        response = client.get(f"/v1/watchlist/{watchlist.watchlist_id}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["watchlist_id"] == str(watchlist.watchlist_id)
        assert data["watchlist_name"] == "Test WatchList"
        assert "stocks" in data
    
    def test_get_portfolio_not_found(self, client):
        """Test getting a non-existent watchlist."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = client.get(f"/v1/watchlist/{fake_id}")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_update_watchlist_name(self, client):
        """Test updating watchlist name."""
        watchlist = create_watchlist("Old Name")
        
        response = client.put(
            f"/v1/watchlist/{watchlist.watchlist_id}",
            json={"watchlist_name": "New Name"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["watchlist_name"] == "New Name"
    
    def test_delete_portfolio(self, client):
        """Test deleting a watchlist."""
        watchlist = create_watchlist("Test WatchList")
        
        response = client.delete(f"/v1/watchlist/{watchlist.watchlist_id}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
        
        # Verify watchlist is deleted
        get_response = client.get(f"/v1/watchlist/{watchlist.watchlist_id}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_add_stocks_to_portfolio(self, client):
        """Test adding stocks to a watchlist."""
        watchlist = create_watchlist("Test WatchList")
        
        response = client.post(
            f"/v1/watchlist/{watchlist.watchlist_id}/stocks",
            json={"tickers": "AAPL,MSFT"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
        assert "added_stocks" in data
        assert len(data["added_stocks"]) == 2
    
    def test_add_stocks_duplicate_ignored(self, client):
        """Test that duplicate stocks are ignored."""
        watchlist = create_watchlist("Test WatchList")
        
        # Add AAPL first time
        response1 = client.post(
            f"/v1/watchlist/{watchlist.watchlist_id}/stocks",
            json={"tickers": "AAPL"}
        )
        assert response1.status_code == status.HTTP_200_OK
        assert len(response1.json()["added_stocks"]) == 1
        
        # Try to add AAPL again
        response2 = client.post(
            f"/v1/watchlist/{watchlist.watchlist_id}/stocks",
            json={"tickers": "AAPL"}
        )
        assert response2.status_code == status.HTTP_200_OK
        assert len(response2.json()["added_stocks"]) == 0  # Should be ignored
    
    def test_add_stocks_invalid_ticker_filtered(self, client):
        """Test that invalid tickers are filtered out and message is returned."""
        watchlist = create_watchlist("Test WatchList")
        
        response = client.post(
            f"/v1/watchlist/{watchlist.watchlist_id}/stocks",
            json={"tickers": "INVALID12345"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "invalid_tickers" in data
        assert len(data["invalid_tickers"]) == 1
        assert "INVALID12345" in data["invalid_tickers"]
        assert "Ticker INVALID12345 is invalid" in data["message"]
    
    def test_add_stocks_mixed_valid_invalid(self, client):
        """Test adding mix of valid and invalid tickers."""
        watchlist = create_watchlist("Test WatchList")
        
        response = client.post(
            f"/v1/watchlist/{watchlist.watchlist_id}/stocks",
            json={"tickers": "AAPL,INVALID12345,MSFT"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["added_stocks"]) == 2
        assert len(data["invalid_tickers"]) == 1
        assert "INVALID12345" in data["invalid_tickers"]
        assert "Added 2 stock(s) to watchlist" in data["message"]
        assert "Ticker INVALID12345 is invalid" in data["message"]
    
    def test_remove_stock_from_portfolio(self, client):
        """Test removing a stock from watchlist."""
        watchlist = create_watchlist("Test WatchList")
        add_stocks_to_watchlist(watchlist.watchlist_id, ["AAPL", "MSFT"])
        
        response = client.delete(
            f"/v1/watchlist/{watchlist.watchlist_id}/stocks/AAPL"
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "message" in data
    
    def test_remove_stock_not_found(self, client):
        """Test removing a stock that doesn't exist."""
        watchlist = create_watchlist("Test WatchList")
        
        response = client.delete(
            f"/v1/watchlist/{watchlist.watchlist_id}/stocks/AAPL"
        )
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
