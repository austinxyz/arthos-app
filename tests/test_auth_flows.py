
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

def test_login_redirect(client):
    """Test that /login redirects to Google OIDC."""
    response = client.get("/login", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert "accounts.google.com" in response.headers["location"]

def test_logout_flows(auth_client, test_user):
    """Test logout clears session."""
    # Verify we are logged in first by accessing a protected route
    pre_logout = auth_client.post("/v1/watchlist", json={"watchlist_name": "Pre Logout Test"})
    assert pre_logout.status_code == 200, "Should be able to create watchlist before logout"

    # Perform logout
    response = auth_client.get("/logout", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/"

    # Verify session is cleared by attempting to access a protected route
    # After logout, this should fail with 401
    post_logout = auth_client.post("/v1/watchlist", json={"watchlist_name": "Post Logout Test"})
    assert post_logout.status_code == 401, "Should not be able to create watchlist after logout"
    assert "logged in" in post_logout.json()["detail"].lower()

def test_protected_route_access_denied(client):
    """Test accessing protected route without login fails/redirects."""
    # Try creating a watchlist (API)
    response = client.post("/v1/watchlist", json={"watchlist_name": "Hacker Watchlist"})
    assert response.status_code == 401
    assert "logged in" in response.json()["detail"].lower()

def test_protected_route_access_granted(auth_client, test_user):
    """Test accessing protected route with login works."""
    # Try creating a watchlist
    response = auth_client.post("/v1/watchlist", json={"watchlist_name": "Real User Watchlist"})
    assert response.status_code == 200
    data = response.json()
    assert "watchlist_id" in data
    assert data["watchlist_name"] == "Real User Watchlist"
    
    # Verify it belongs to user
    from app.services.watchlist_service import get_all_watchlists
    watchlists = get_all_watchlists(test_user.id)
    assert any(w.watchlist_name == "Real User Watchlist" for w in watchlists)
