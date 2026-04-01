"""Integration tests for GET /optionquote/{option_symbol} endpoint."""
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.providers.base import OptionQuote
from app.providers.exceptions import DataNotAvailableError


@pytest.fixture
def client():
    return TestClient(app)


def _make_quote(**kwargs) -> OptionQuote:
    defaults = dict(
        contract_symbol="NFLX281215P00105000",
        strike=105.0,
        bid=2.50,
        ask=2.70,
        last_price=2.55,
        volume=312,
        open_interest=1540,
        implied_volatility=34.5,
        delta=-0.23,
        gamma=0.011,
        theta=-0.04,
        vega=0.18,
        rho=-0.07,
    )
    defaults.update(kwargs)
    return OptionQuote(**defaults)


class TestOptionQuoteEndpoint:

    def test_valid_symbol_returns_200(self, client):
        quote = _make_quote()
        with patch("app.services.option_quote_service.ProviderFactory") as mock_factory, \
             patch("app.services.option_quote_service._quote_cache", {}):
            provider = MagicMock()
            provider.fetch_option_quote.return_value = quote
            provider.get_provider_name.return_value = "MarketData.app"
            mock_factory.get_options_provider.return_value = provider

            response = client.get("/optionquote/NFLX281215P00105000")

        assert response.status_code == 200
        data = response.json()
        assert data["symbol"] == "NFLX281215P00105000"
        assert data["bid"] == 2.50
        assert data["ask"] == 2.70
        assert data["mid"] == 2.60
        assert data["last_price"] == 2.55
        assert data["strike"] == 105.0
        assert data["provider"] == "MarketData.app"

    def test_greeks_included(self, client):
        quote = _make_quote()
        with patch("app.services.option_quote_service.ProviderFactory") as mock_factory, \
             patch("app.services.option_quote_service._quote_cache", {}):
            provider = MagicMock()
            provider.fetch_option_quote.return_value = quote
            provider.get_provider_name.return_value = "MarketData.app"
            mock_factory.get_options_provider.return_value = provider

            response = client.get("/optionquote/NFLX281215P00105000")

        greeks = response.json()["greeks"]
        assert greeks["delta"] == -0.23
        assert greeks["gamma"] == 0.011
        assert greeks["theta"] == -0.04
        assert greeks["vega"] == 0.18
        assert greeks["rho"] == -0.07

    def test_null_greeks_when_unavailable(self, client):
        quote = _make_quote(delta=None, gamma=None, theta=None, vega=None, rho=None)
        with patch("app.services.option_quote_service.ProviderFactory") as mock_factory, \
             patch("app.services.option_quote_service._quote_cache", {}):
            provider = MagicMock()
            provider.fetch_option_quote.return_value = quote
            provider.get_provider_name.return_value = "yfinance"
            mock_factory.get_options_provider.return_value = provider

            response = client.get("/optionquote/NFLX281215P00105000")

        greeks = response.json()["greeks"]
        assert all(v is None for v in greeks.values())

    def test_mid_is_null_when_bid_or_ask_missing(self, client):
        quote = _make_quote(bid=None, ask=2.70)
        with patch("app.services.option_quote_service.ProviderFactory") as mock_factory, \
             patch("app.services.option_quote_service._quote_cache", {}):
            provider = MagicMock()
            provider.fetch_option_quote.return_value = quote
            provider.get_provider_name.return_value = "MarketData.app"
            mock_factory.get_options_provider.return_value = provider

            response = client.get("/optionquote/NFLX281215P00105000")

        assert response.json()["mid"] is None

    def test_prices_rounded_to_2dp(self, client):
        quote = _make_quote(bid=2.5012345, ask=2.6987654, last_price=2.5555555)
        with patch("app.services.option_quote_service.ProviderFactory") as mock_factory, \
             patch("app.services.option_quote_service._quote_cache", {}):
            provider = MagicMock()
            provider.fetch_option_quote.return_value = quote
            provider.get_provider_name.return_value = "MarketData.app"
            mock_factory.get_options_provider.return_value = provider

            response = client.get("/optionquote/NFLX281215P00105000")

        data = response.json()
        assert data["bid"] == 2.50
        assert data["ask"] == 2.70
        assert data["last_price"] == 2.56

    def test_provider_returns_none_gives_404(self, client):
        with patch("app.services.option_quote_service.ProviderFactory") as mock_factory, \
             patch("app.services.option_quote_service._quote_cache", {}):
            provider = MagicMock()
            provider.fetch_option_quote.return_value = None
            provider.get_provider_name.return_value = "MarketData.app"
            mock_factory.get_options_provider.return_value = provider

            response = client.get("/optionquote/NFLX281215P00105000")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_invalid_symbol_gives_422(self, client):
        response = client.get("/optionquote/BADFORMAT")
        assert response.status_code == 422
        assert "OCC format" in response.json()["detail"]

    def test_past_expiration_gives_422(self, client):
        response = client.get("/optionquote/AAPL200117C00100000")
        assert response.status_code == 422
        assert "past" in response.json()["detail"].lower()

    def test_rate_limit_triggers_yfinance_fallback(self, client):
        quote = _make_quote(delta=None, gamma=None, theta=None, vega=None, rho=None)
        with patch("app.services.option_quote_service.ProviderFactory") as mock_factory, \
             patch("app.services.option_quote_service._quote_cache", {}), \
             patch("app.services.option_quote_service.YFinanceProvider", autospec=True) as mock_yf_cls:
            primary = MagicMock()
            primary.fetch_option_quote.side_effect = DataNotAvailableError("rate limit exceeded")
            primary.get_provider_name.return_value = "MarketData.app"
            mock_factory.get_options_provider.return_value = primary

            yf_instance = MagicMock()
            yf_instance.fetch_option_quote.return_value = quote
            yf_instance.get_provider_name.return_value = "YFinanceProvider"
            mock_yf_cls.return_value = yf_instance

            response = client.get("/optionquote/NFLX281215P00105000")

        assert response.status_code == 200
        assert response.json()["provider"] == "YFinanceProvider"

    def test_non_rate_limit_provider_error_gives_503(self, client):
        with patch("app.services.option_quote_service.ProviderFactory") as mock_factory, \
             patch("app.services.option_quote_service._quote_cache", {}):
            provider = MagicMock()
            provider.fetch_option_quote.side_effect = DataNotAvailableError("connection timeout")
            provider.get_provider_name.return_value = "MarketData.app"
            mock_factory.get_options_provider.return_value = provider

            response = client.get("/optionquote/NFLX281215P00105000")

        assert response.status_code == 503

    def test_case_insensitive_symbol_in_url(self, client):
        quote = _make_quote()
        with patch("app.services.option_quote_service.ProviderFactory") as mock_factory, \
             patch("app.services.option_quote_service._quote_cache", {}):
            provider = MagicMock()
            provider.fetch_option_quote.return_value = quote
            provider.get_provider_name.return_value = "MarketData.app"
            mock_factory.get_options_provider.return_value = provider

            response = client.get("/optionquote/nflx281215p00105000")

        assert response.status_code == 200
        assert response.json()["symbol"] == "NFLX281215P00105000"


class TestSimpleMode:

    def test_simple_returns_plain_text_mid(self, client):
        quote = _make_quote(bid=2.50, ask=2.70, last_price=2.55)
        with patch("app.services.option_quote_service.ProviderFactory") as mock_factory, \
             patch("app.services.option_quote_service._quote_cache", {}):
            provider = MagicMock()
            provider.fetch_option_quote.return_value = quote
            provider.get_provider_name.return_value = "MarketData.app"
            mock_factory.get_options_provider.return_value = provider

            response = client.get("/optionquote/NFLX281215P00105000?simple=true")

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert response.text == "2.60"  # mid, not last_price

    def test_simple_returns_mid_even_when_last_price_present(self, client):
        quote = _make_quote(bid=3.00, ask=4.00, last_price=2.00)
        with patch("app.services.option_quote_service.ProviderFactory") as mock_factory, \
             patch("app.services.option_quote_service._quote_cache", {}):
            provider = MagicMock()
            provider.fetch_option_quote.return_value = quote
            provider.get_provider_name.return_value = "MarketData.app"
            mock_factory.get_options_provider.return_value = provider

            response = client.get("/optionquote/NFLX281215P00105000?simple=true")

        assert response.status_code == 200
        assert response.text == "3.50"  # (3.00 + 4.00) / 2

    def test_simple_returns_404_when_no_price_at_all(self, client):
        quote = _make_quote(last_price=None, bid=None, ask=None)
        with patch("app.services.option_quote_service.ProviderFactory") as mock_factory, \
             patch("app.services.option_quote_service._quote_cache", {}):
            provider = MagicMock()
            provider.fetch_option_quote.return_value = quote
            provider.get_provider_name.return_value = "MarketData.app"
            mock_factory.get_options_provider.return_value = provider

            response = client.get("/optionquote/NFLX281215P00105000?simple=true")

        assert response.status_code == 404

    def test_simple_price_always_2_decimal_places(self, client):
        quote = _make_quote(bid=10.0, ask=10.0)  # mid = 10.00
        with patch("app.services.option_quote_service.ProviderFactory") as mock_factory, \
             patch("app.services.option_quote_service._quote_cache", {}):
            provider = MagicMock()
            provider.fetch_option_quote.return_value = quote
            provider.get_provider_name.return_value = "MarketData.app"
            mock_factory.get_options_provider.return_value = provider

            response = client.get("/optionquote/NFLX281215P00105000?simple=true")

        assert response.text == "10.00"

    def test_without_simple_param_returns_json(self, client):
        quote = _make_quote()
        with patch("app.services.option_quote_service.ProviderFactory") as mock_factory, \
             patch("app.services.option_quote_service._quote_cache", {}):
            provider = MagicMock()
            provider.fetch_option_quote.return_value = quote
            provider.get_provider_name.return_value = "MarketData.app"
            mock_factory.get_options_provider.return_value = provider

            response = client.get("/optionquote/NFLX281215P00105000")

        assert response.headers["content-type"].startswith("application/json")
