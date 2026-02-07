"""Production authentication fixtures for Playwright browser tests against live environment.

This module provides fixtures for testing against production (my.arthos.app) using
a real Google OAuth test account.

Usage:
    TEST_SERVER_URL=https://my.arthos.app pytest tests/test_*_browser.py -v
"""
import os
import pytest
from playwright.sync_api import Page, expect
import logging

logger = logging.getLogger(__name__)


@pytest.fixture
def production_test_account():
    """Get production test account credentials from environment.

    Returns:
        dict: Contains 'email' and 'password' for test account

    Raises:
        ValueError: If credentials not found in environment
    """
    email = os.getenv("TEST_GOOGLE_EMAIL")
    password = os.getenv("TEST_GOOGLE_PASSWORD")

    if not email or not password:
        raise ValueError(
            "Production test credentials not found. "
            "Set TEST_GOOGLE_EMAIL and TEST_GOOGLE_PASSWORD environment variables."
        )

    return {"email": email, "password": password}


@pytest.fixture
def authenticated_production_session(page: Page, live_server_url: str, production_test_account: dict):
    """Authenticate against production using Google OAuth.

    This fixture logs in to the application using the real Google OAuth flow.
    It handles the Google login page and returns to the application authenticated.

    Args:
        page: Playwright page object
        live_server_url: URL of the server (production or local)
        production_test_account: Test account credentials

    Returns:
        str: The authenticated email address

    Note:
        Only use this fixture when TEST_SERVER_URL points to production.
        For local testing, use the regular authenticated_session fixture.
    """
    is_production = "my.arthos.app" in live_server_url

    if not is_production:
        pytest.skip("This fixture is only for production testing")

    email = production_test_account["email"]
    password = production_test_account["password"]

    logger.info(f"Authenticating to {live_server_url} with {email}")

    # Navigate to home page (will redirect to login)
    page.goto(live_server_url)

    # Check if already logged in
    if "Login" not in page.content() and "Sign Up" not in page.content():
        logger.info("Already authenticated, skipping login")
        return email

    # Click login button
    page.click('a[href="/login"]')

    # Wait for Google OAuth page
    page.wait_for_url("**/accounts.google.com/**", timeout=10000)

    # Fill in email
    page.fill('input[type="email"]', email)
    page.click('button:has-text("Next"), #identifierNext')

    # Wait for password page
    page.wait_for_selector('input[type="password"]', timeout=10000)

    # Fill in password
    page.fill('input[type="password"]', password)
    page.click('button:has-text("Next"), #passwordNext')

    # Wait for redirect back to app
    page.wait_for_url(f"{live_server_url}/**", timeout=15000)

    # Verify we're logged in
    expect(page.locator("body")).not_to_contain_text("Login")
    logger.info(f"Successfully authenticated as {email}")

    return email


@pytest.fixture
def skip_if_not_production(live_server_url: str):
    """Skip test if not running against production.

    Usage:
        def test_something(skip_if_not_production):
            # This test only runs against production
            ...
    """
    if "my.arthos.app" not in live_server_url:
        pytest.skip("This test only runs against production")
