"""Centralized authentication fixtures for Playwright browser tests.

This module provides reusable fixtures for creating authenticated test sessions.
Uses manual cookie injection with signed session data, matching the server's
SessionMiddleware configuration.
"""
import os
import pytest
from uuid import uuid4, UUID
from playwright.sync_api import Page
from itsdangerous import URLSafeTimedSerializer
from sqlmodel import Session
from app.database import engine
from app.models.account import Account
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


@pytest.fixture
def test_account(setup_database) -> Account:
    """Create a test account in database and clean up after test.
    
    Returns:
        Account: The created test account object
    
    Yields the account and ensures cleanup happens even if test fails.
    """
    account_id = uuid4()
    
    # Create test account
    with Session(engine) as session:
        account = Account(
            id=account_id,
            email=f"test_{account_id}@example.com",
            google_sub=f"test_sub_{account_id}",
            full_name="Test User",
            picture_url="http://example.com/pic.jpg",
            created_at=datetime.now(),
            last_login_at=datetime.now()
        )
        session.add(account)
        session.commit()
        session.refresh(account)
        logger.info(f"Created test account: {account_id}")
    
    yield account
    
    # Cleanup: Delete account and all associated data
    # Note: Cascade deletes should handle watchlists and RR entries
    with Session(engine) as session:
        account_obj = session.get(Account, account_id)
        if account_obj:
            session.delete(account_obj)
            session.commit()
            logger.info(f"Cleaned up test account: {account_id}")


@pytest.fixture
def authenticated_session(page: Page, live_server_url: str, test_account: Account) -> UUID:
    """Inject session cookie for authenticated test account.
    
    Args:
        page: Playwright page object
        live_server_url: Base URL of the test server
        test_account: Test account from test_account fixture
    
    Returns:
        UUID: The account ID (same as test_account.id)
    
    This fixture automatically injects a signed session cookie that authenticates
    the browser as the test account. Use this fixture in any test that needs to
    interact with authenticated features.
    """
    # Authenticate via test endpoint which sets the session cookie server-side
    # This avoids issues with SECRET_KEY mismatch or serializer differences
    login_url = f"{live_server_url}/_test/login/{test_account.id}"
    logger.info(f"Authenticating via endpoint: {login_url}")
    
    response = page.goto(login_url)
    assert response.ok, f"Failed to authenticate via test endpoint: {response.status} {response.status_text}"
    
    # Verify session cookie was set
    cookies = page.context.cookies()
    session_cookie = next((c for c in cookies if c["name"] == "session"), None)
    assert session_cookie, "Session cookie not found after authentication"
            
    return test_account.id


@pytest.fixture
def unauthenticated_session(page: Page) -> None:
    """Ensure no authentication session exists.
    
    Use this fixture for tests that need to verify unauthenticated behavior,
    such as redirects to login page.
    """
    # Clear all cookies to ensure no session
    page.context.clear_cookies()
    logger.info("Cleared all cookies for unauthenticated session")

