"""Tests for the Add New RR API endpoints and page route."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app


def make_mock_option(strike, bid, ask):
    opt = MagicMock()
    opt.strike = strike
    opt.bid = bid
    opt.ask = ask
    return opt


def make_mock_chain(puts, calls):
    chain = MagicMock()
    chain.puts = puts
    chain.calls = calls
    return chain


@pytest.fixture
def client():
    return TestClient(app)


class TestRRAddPage:
    def test_rr_add_page_loads(self, client):
        """GET /rr-add returns 200 with the Add New RR form."""
        response = client.get("/rr-add")
        assert response.status_code == 200
        assert "Add New RR" in response.text
        assert "tickerInput" in response.text
        assert "expirationSelect" in response.text
        assert "putStrikeSelect" in response.text
        assert "callStrikeSelect" in response.text
        assert "callRatioSelect" in response.text
        assert "showBtn" in response.text
        assert "trackBtn" in response.text


class TestRRExpirationsAPI:
    def test_returns_leaps_expirations(self, client):
        """GET /api/rr/expirations returns LEAPS expirations for a valid ticker."""
        with patch("app.services.options_data_service.get_leaps_expirations", return_value=["2026-01-15", "2027-01-21"]):
            response = client.get("/api/rr/expirations?ticker=AAPL")
        assert response.status_code == 200
        data = response.json()
        assert "expirations" in data
        assert data["expirations"] == ["2026-01-15", "2027-01-21"]

    def test_ticker_is_uppercased(self, client):
        """Ticker is normalized to uppercase before lookup."""
        captured = {}

        def fake_get_leaps(ticker):
            captured["ticker"] = ticker
            return []

        with patch("app.services.options_data_service.get_leaps_expirations", side_effect=fake_get_leaps):
            client.get("/api/rr/expirations?ticker=aapl")

        assert captured["ticker"] == "AAPL"

    def test_empty_expirations(self, client):
        """Returns empty list when no LEAPS are found."""
        with patch("app.services.options_data_service.get_leaps_expirations", return_value=[]):
            response = client.get("/api/rr/expirations?ticker=FAKE")
        assert response.status_code == 200
        assert response.json() == {"expirations": []}


class TestRROptionsChainAPI:
    def _mock_provider(self, puts, calls):
        """Build a mock provider factory with an options chain."""
        mock_provider = MagicMock()
        mock_chain = make_mock_chain(puts=puts, calls=calls)
        mock_provider.fetch_options_chain.return_value = mock_chain
        mock_factory = MagicMock()
        mock_factory.get_options_provider.return_value = mock_provider
        mock_factory.get_default_provider.return_value = mock_provider
        return mock_factory

    def test_returns_filtered_strikes_with_stock_price(self, client, setup_database):
        """Returns puts and calls filtered by range, with stock price from DB.

        Stock price = 200.0 (1 day of data, no drift).
        put range: 90%-140% = $180-$280
        call range: 50%-150% = $100-$300
        """
        from tests.conftest import populate_test_stock_prices
        populate_test_stock_prices("TSLA", num_days=1, base_price=200.0)
        # stock_price will be exactly 200.0

        puts = [
            make_mock_option(185.0, 5.0, 5.5),   # in range (92.5%)
            make_mock_option(220.0, 3.0, 3.5),   # in range (110%)
            make_mock_option(290.0, 1.0, 1.5),   # out of range (145% > 140%)
        ]
        calls = [
            make_mock_option(110.0, 8.0, 8.5),   # in range (55%)
            make_mock_option(240.0, 4.0, 4.5),   # in range (120%)
            make_mock_option(320.0, 0.5, 0.8),   # out of range (160% > 150%)
        ]

        mock_factory = self._mock_provider(puts, calls)
        with patch("app.providers.factory.ProviderFactory", mock_factory):
            response = client.get("/api/rr/options-chain?ticker=TSLA&expiration=2026-01-15")

        assert response.status_code == 200
        data = response.json()
        assert "stock_price" in data
        assert data["stock_price"] == pytest.approx(200.0, abs=1.0)

        # Puts: 185 and 220 in range; 290 out of range
        put_strikes = [p["strike"] for p in data["puts"]]
        assert 185.0 in put_strikes
        assert 220.0 in put_strikes
        assert 290.0 not in put_strikes

        # Calls: 110 and 240 in range; 320 out of range
        call_strikes = [c["strike"] for c in data["calls"]]
        assert 110.0 in call_strikes
        assert 240.0 in call_strikes
        assert 320.0 not in call_strikes

    def test_options_sorted_by_strike(self, client, setup_database):
        """Puts and calls are returned sorted by strike price ascending."""
        from tests.conftest import populate_test_stock_prices
        populate_test_stock_prices("MSFT", num_days=5, base_price=300.0)

        puts = [
            make_mock_option(310.0, 4.0, 4.5),
            make_mock_option(280.0, 6.0, 6.5),
        ]
        calls = [
            make_mock_option(350.0, 3.0, 3.5),
            make_mock_option(200.0, 8.0, 8.5),
        ]

        mock_factory = self._mock_provider(puts, calls)
        with patch("app.providers.factory.ProviderFactory", mock_factory):
            response = client.get("/api/rr/options-chain?ticker=MSFT&expiration=2026-01-15")

        data = response.json()
        put_strikes = [p["strike"] for p in data["puts"]]
        call_strikes = [c["strike"] for c in data["calls"]]
        assert put_strikes == sorted(put_strikes)
        assert call_strikes == sorted(call_strikes)

    def test_excludes_options_with_invalid_quotes(self, client, setup_database):
        """Options with zero or missing bid/ask are excluded."""
        from tests.conftest import populate_test_stock_prices
        populate_test_stock_prices("AMZN", num_days=5, base_price=200.0)

        puts = [
            make_mock_option(190.0, 0.0, 3.0),   # bid=0, excluded
            make_mock_option(195.0, 4.0, 4.5),   # valid
        ]
        calls = [
            make_mock_option(210.0, None, 3.0),  # bid=None, excluded
            make_mock_option(220.0, 3.0, 3.5),   # valid
        ]

        mock_factory = self._mock_provider(puts, calls)
        with patch("app.providers.factory.ProviderFactory", mock_factory):
            response = client.get("/api/rr/options-chain?ticker=AMZN&expiration=2026-01-15")

        data = response.json()
        put_strikes = [p["strike"] for p in data["puts"]]
        call_strikes = [c["strike"] for c in data["calls"]]
        assert 190.0 not in put_strikes
        assert 195.0 in put_strikes
        assert 210.0 not in call_strikes
        assert 220.0 in call_strikes

    def test_mid_price_calculated_correctly(self, client, setup_database):
        """Mid price is the average of bid and ask."""
        from tests.conftest import populate_test_stock_prices
        populate_test_stock_prices("NVDA", num_days=5, base_price=500.0)

        puts = [make_mock_option(490.0, 5.0, 7.0)]  # mid = 6.0
        calls = [make_mock_option(510.0, 4.0, 6.0)]  # mid = 5.0

        mock_factory = self._mock_provider(puts, calls)
        with patch("app.providers.factory.ProviderFactory", mock_factory):
            response = client.get("/api/rr/options-chain?ticker=NVDA&expiration=2026-01-15")

        data = response.json()
        assert data["puts"][0]["mid"] == 6.0
        assert data["calls"][0]["mid"] == 5.0
