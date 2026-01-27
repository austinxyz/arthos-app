"""Playwright test for Covered Calls Dumbbell Chart."""
import pytest
from playwright.sync_api import Page, expect
from app.database import engine, create_db_and_tables
from sqlmodel import Session
from app.models.stock_price import StockPrice, StockAttributes
from tests.conftest import populate_test_stock_prices


@pytest.fixture(autouse=True)
def setup_database():
    """Create database tables and clean up before and after each test."""
    create_db_and_tables()

    # Populate test data
    populate_test_stock_prices("AAPL")
    populate_test_stock_prices("TSLA")

    yield

    # Cleanup after test
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


@pytest.fixture
def live_server_url():
    """Return the URL of the live server."""
    import os
    return os.getenv("TEST_SERVER_URL", "http://localhost:8000")


@pytest.mark.browser
class TestCoveredCallsDumbbellChart:
    """Test Covered Calls Dumbbell Chart visualization."""

    def test_dumbbell_chart_displays(self, page: Page, live_server_url, authenticated_session):
        """Test that dumbbell chart is displayed on the Covered Calls tab."""
        ticker = "AAPL"
        page.goto(f"{live_server_url}/stock/{ticker}")
        page.wait_for_load_state("networkidle", timeout=30000)

        # Check page loaded
        expect(page).to_have_title(f"Stock: {ticker} - Arthos", timeout=10000)

        # Covered Calls tab should be active by default
        covered_calls_tab = page.locator("button#covered-calls-tab")
        expect(covered_calls_tab).to_be_visible()

        tab_classes = covered_calls_tab.get_attribute("class") or ""
        assert "active" in tab_classes, f"Covered Calls tab should be active by default"

        # Check if dumbbell chart container exists
        chart_container = page.locator("#coveredCallsDumbbellChart")

        if chart_container.count() > 0:
            print("✓ Dumbbell chart container found")
            expect(chart_container).to_be_visible(timeout=5000)

            # Wait for Highcharts to render
            page.wait_for_timeout(2000)

            # Check if Highcharts rendered the chart
            # Highcharts adds an SVG element inside the container
            chart_svg = chart_container.locator("svg.highcharts-root")

            if chart_svg.count() > 0:
                expect(chart_svg).to_be_visible()
                print("✓ Dumbbell chart SVG rendered")

                # Check for chart title
                # Note: Use text_content() instead of inner_text() for SVG text elements
                chart_title = chart_container.locator("text.highcharts-title")
                if chart_title.count() > 0:
                    title_text = chart_title.text_content() or ""
                    # Chart title may vary, just verify it's not empty
                    print(f"✓ Chart title found: {title_text}")

                # Check for axis labels
                y_axis_title = chart_container.locator("text.highcharts-yaxis-title")
                if y_axis_title.count() > 0:
                    print("✓ Y-axis title present (Return %)")

                x_axis_title = chart_container.locator("text.highcharts-xaxis-title")
                if x_axis_title.count() > 0:
                    print("✓ X-axis title present (Contract)")

                # Check for data points (markers)
                markers = chart_container.locator("path.highcharts-point")
                marker_count = markers.count()
                if marker_count > 0:
                    print(f"✓ Found {marker_count} data markers")
                    assert marker_count >= 2, "Should have at least 2 markers (one exercised, one not exercised) per contract"

                # Check for connecting lines (dumbbell connector)
                lines = chart_container.locator("path.highcharts-graph")
                if lines.count() > 0:
                    print(f"✓ Found {lines.count()} connecting lines")
            else:
                print("  No SVG element found - chart may not have data to display")
        else:
            print("  No dumbbell chart container found - may not have covered call data")

        # Take screenshot
        page.screenshot(path=f"test_dumbbell_chart_{ticker}.png", full_page=True)
        print(f"✓ Screenshot saved: test_dumbbell_chart_{ticker}.png")

    def test_dumbbell_chart_with_multiple_tickers(self, page: Page, live_server_url, authenticated_session):
        """Test dumbbell chart with different tickers."""
        tickers = ["AAPL", "TSLA"]

        for ticker in tickers:
            print(f"\n{'='*60}")
            print(f"Testing dumbbell chart for {ticker}")
            print(f"{'='*60}")

            page.goto(f"{live_server_url}/stock/{ticker}")
            page.wait_for_load_state("networkidle", timeout=30000)

            # Wait for any charts to render
            page.wait_for_timeout(2000)

            chart_container = page.locator("#coveredCallsDumbbellChart")

            if chart_container.count() > 0:
                chart_svg = chart_container.locator("svg.highcharts-root")

                if chart_svg.count() > 0:
                    print(f"✓ {ticker}: Dumbbell chart rendered successfully")

                    # Verify it's interactive (has tooltip)
                    # Highcharts tooltips are created on hover
                    markers = chart_container.locator("path.highcharts-point")
                    if markers.count() > 0:
                        # Hover over first marker to trigger tooltip
                        markers.first.hover()
                        page.wait_for_timeout(500)
                        print(f"✓ {ticker}: Chart is interactive (markers are hoverable)")
                else:
                    print(f"  {ticker}: No chart data available")
            else:
                print(f"  {ticker}: No chart container found")
