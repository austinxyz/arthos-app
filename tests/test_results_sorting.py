"""Playwright test for results page sorting."""
import pytest
from playwright.sync_api import Page, expect
from fastapi.testclient import TestClient
from app.main import app
import time


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(scope="module")
def browser_page():
    """Create a Playwright browser page."""
    from playwright.sync_api import sync_playwright
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        yield page
        browser.close()


@pytest.mark.browser
def test_results_page_signal_sorting(browser_page: Page, client):
    """Test that results page sorts by Signal correctly."""
    # Start the FastAPI server in a separate process or use the test client
    # For this test, we'll use the test client to get the HTML
    response = client.get("/results?tickers=AAPL,MSFT,GOOGL,TSLA,AMZN")
    
    assert response.status_code == 200
    
    # Set the HTML content in the browser page
    browser_page.set_content(response.text)
    
    # Wait for DataTable to initialize
    browser_page.wait_for_selector('#metricsTable', state='visible')
    browser_page.wait_for_timeout(1000)  # Wait for DataTable to finish initializing
    
    # Get all signal values from the table
    signal_cells = browser_page.locator('#metricsTable tbody tr td:nth-child(6)')
    
    # Extract signal text from badges
    signals = []
    count = signal_cells.count()
    for i in range(count):
        cell = signal_cells.nth(i)
        # Try to get badge text first, fallback to cell text
        badge = cell.locator('.badge')
        if badge.count() > 0:
            signal_text = badge.inner_text()
        else:
            signal_text = cell.inner_text()
        signals.append(signal_text.strip())
    
    # Expected order: Extreme Oversold (5) > Oversold (4) > Neutral (3) > Overbought (2) > Extreme Overbought (1)
    # Define priority mapping - note: badges show abbreviated text (Extreme OS, Extreme OB)
    priority_map = {
        'Extreme OS': 5,  # Badge text for Extreme Oversold
        'Extreme Oversold': 5,
        'Oversold': 4,
        'Neutral': 3,
        'Overbought': 2,
        'Extreme OB': 1,  # Badge text for Extreme Overbought
        'Extreme Overbought': 1
    }
    
    # Verify signals are in descending priority order
    if len(signals) > 1:
        for i in range(len(signals) - 1):
            current_priority = priority_map.get(signals[i], 0)
            next_priority = priority_map.get(signals[i + 1], 0)
            assert current_priority >= next_priority, \
                f"Sorting incorrect: {signals[i]} (priority {current_priority}) should come before {signals[i + 1]} (priority {next_priority})"


@pytest.mark.skip(reason="Requires server to be running on localhost:8000")
def test_results_page_signal_sorting_manual(browser_page: Page):
    """Test sorting by manually navigating to a running server."""
    # This test assumes the server is running on localhost:8000
    # You would run this separately with: python run.py
    browser_page.goto("http://localhost:8000/results?tickers=AAPL,MSFT,GOOGL,TSLA,AMZN")
    
    # Wait for table to load
    browser_page.wait_for_selector('#metricsTable', state='visible')
    browser_page.wait_for_timeout(2000)  # Wait for DataTable to initialize
    
    # Get signal column values
    signal_cells = browser_page.locator('#metricsTable tbody tr td:nth-child(6)')
    
    signals = []
    count = signal_cells.count()
    for i in range(min(count, 10)):  # Check first 10 rows
        cell = signal_cells.nth(i)
        badge = cell.locator('.badge')
        if badge.count() > 0:
            signal_text = badge.inner_text()
        else:
            signal_text = cell.inner_text()
        signals.append(signal_text.strip())
        print(f"Row {i+1}: {signal_text.strip()}")
    
    # Verify sorting - note: badges show abbreviated text (Extreme OS, Extreme OB)
    priority_map = {
        'Extreme OS': 5,  # Badge text for Extreme Oversold
        'Extreme Oversold': 5,
        'Oversold': 4,
        'Neutral': 3,
        'Overbought': 2,
        'Extreme OB': 1,  # Badge text for Extreme Overbought
        'Extreme Overbought': 1
    }
    
    if len(signals) > 1:
        for i in range(len(signals) - 1):
            current_priority = priority_map.get(signals[i], 0)
            next_priority = priority_map.get(signals[i + 1], 0)
            assert current_priority >= next_priority, \
                f"Sorting incorrect at row {i+1}: {signals[i]} (priority {current_priority}) should come before {signals[i + 1]} (priority {next_priority})"

