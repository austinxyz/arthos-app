
"""Tests for watchlist API endpoints."""
import pytest
from fastapi import status
from uuid import UUID
from app.services.watchlist_service import create_watchlist, add_stocks_to_watchlist
from app.database import engine, create_db_and_tables
from sqlmodel import Session, select
from app.models.watchlist import WatchList, WatchListStock
from app.models.stock_price import StockPrice, StockAttributes

# Removed duplicate setup_database fixture - using the one from conftest.py instead

class TestWatchListAPI:
    """Tests for /v1/watchlist endpoints."""

    def test_create_portfolio_success(self, auth_client, test_user):
        """Test creating a watchlist via API."""
        response = auth_client.post(
            "/v1/watchlist",
            json={"watchlist_name": "Test WatchList"}
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "watchlist_id" in data
        assert data["watchlist_name"] == "Test WatchList"
        # Verify it's owned by test_user
        with Session(engine) as session:
            wl = session.get(WatchList, UUID(data["watchlist_id"]))
            assert wl.account_id == test_user.id
    
    def test_create_portfolio_invalid_name(self, auth_client):
        """Test creating watchlist with invalid name."""
        response = auth_client.post(
            "/v1/watchlist",
            json={"watchlist_name": "Invalid-Name!"}
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_list_watchlists_empty(self, auth_client):
        """Test listing watchlists when none exist."""
        response = auth_client.get("/v1/watchlist")
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["watchlists"] == []
    
    def test_list_watchlists_multiple(self, auth_client, test_user):
        """Test listing multiple watchlists."""
        # Create watchlists for this user
        create_watchlist("WatchList 1", account_id=test_user.id)
        create_watchlist("WatchList 2", account_id=test_user.id)
        
        response = auth_client.get("/v1/watchlist")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["watchlists"]) == 2
    
    def test_get_watchlist_success(self, auth_client, test_user):
        """Test getting a watchlist by ID."""
        watchlist = create_watchlist("Test WatchList", account_id=test_user.id)
        
        response = auth_client.get(f"/v1/watchlist/{watchlist.watchlist_id}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["watchlist_id"] == str(watchlist.watchlist_id)
        assert data["watchlist_name"] == "Test WatchList"

    def test_get_watchlist_not_found(self, auth_client):
        """Test getting a non-existent watchlist."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = auth_client.get(f"/v1/watchlist/{fake_id}")
        assert response.status_code == status.HTTP_404_NOT_FOUND
    
    def test_update_watchlist_name(self, auth_client, test_user):
        """Test updating watchlist name."""
        watchlist = create_watchlist("Old Name", account_id=test_user.id)
        
        response = auth_client.put(
            f"/v1/watchlist/{watchlist.watchlist_id}",
            json={"watchlist_name": "New Name"}
        )
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["watchlist_name"] == "New Name"

    def test_delete_portfolio(self, auth_client, test_user):
        """Test deleting a watchlist."""
        watchlist = create_watchlist("Test WatchList", account_id=test_user.id)
        
        response = auth_client.delete(f"/v1/watchlist/{watchlist.watchlist_id}")
        assert response.status_code == status.HTTP_200_OK
        
        # Verify deleted
        get_response = auth_client.get(f"/v1/watchlist/{watchlist.watchlist_id}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND

    def test_add_stocks_to_portfolio(self, auth_client, test_user):
        """Test adding stocks to a watchlist."""
        watchlist = create_watchlist("Test WatchList", account_id=test_user.id)
        
        response = auth_client.post(
            f"/v1/watchlist/{watchlist.watchlist_id}/stocks",
            json={"tickers": "AAPL,MSFT"}
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert len(data["added_stocks"]) == 2

    def test_remove_stock_from_portfolio(self, auth_client, test_user):
        """Test removing a stock from watchlist."""
        watchlist = create_watchlist("Test WatchList", account_id=test_user.id)
        add_stocks_to_watchlist(watchlist.watchlist_id, ["AAPL", "MSFT"], account_id=test_user.id)

        response = auth_client.delete(
            f"/v1/watchlist/{watchlist.watchlist_id}/stocks/AAPL"
        )
        assert response.status_code == status.HTTP_200_OK

class TestWatchListAPIErrorHandling:
    """Tests for watchlist API error handling."""
    
    def test_create_watchlist_empty_name(self, auth_client):
        response = auth_client.post("/v1/watchlist", json={"watchlist_name": ""})
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_nonexistent(self, auth_client):
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = auth_client.put(f"/v1/watchlist/{fake_id}", json={"watchlist_name": "New"})
        assert response.status_code in [status.HTTP_400_BAD_REQUEST, status.HTTP_404_NOT_FOUND]
