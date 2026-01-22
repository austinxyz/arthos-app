"""Playwright test for results page sorting."""
import pytest
from playwright.sync_api import Page, expect

@pytest.fixture
def live_server_url():
    """Get the live server URL from environment or use default."""
    import os
    return os.getenv("TEST_SERVER_URL", "http://localhost:8000")

@pytest.mark.browser
def test_results_page_signal_sorting(page: Page, live_server_url):
    """Test that results page sorts by Signal correctly."""
    # Build URL with tickers that provide a mix of signals
    # using known tickers from setup_test_data or minimal set
    url = f"{live_server_url}/results?tickers=AAPL,MSFT,GOOGL,TSLA,AMZN"
    
    # Navigate to results page
    response = page.goto(url)
    expect(page).to_have_title("Stock Metrics - Arthos")
    
    # Wait for DataTable to initialize and be visible
    table = page.locator("#metricsTable")
    expect(table).to_be_visible()
    
    # Wait for DataTables processing (if any) or simply wait a moment for sort to apply
    # DataTables sort is synchronous on init but DOM update might need a tick
    page.wait_for_timeout(1000)
    
    # Get all signal values from the table (column 6, which is index 5)
    # nth-child is 1-based, so index 5 is child 6
    signal_cells = page.locator('#metricsTable tbody tr td:nth-child(6)')
    
    # Extract signal text from badges
    signals = []
    count = signal_cells.count()
    print(f"Found {count} rows")
    
    for i in range(count):
        cell = signal_cells.nth(i)
        # Try to get badge text first, fallback to cell text
        badge = cell.locator('.badge')
        if badge.count() > 0:
            signal_text = badge.inner_text()
        else:
            signal_text = cell.inner_text()
        signals.append(signal_text.strip())
        print(f"Row {i}: {signal_text.strip()}")
    
    # Expected order: Extreme Oversold (5) > Oversold (4) > Neutral (3) > Overbought (2) > Extreme Overbought (1)
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
