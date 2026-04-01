"""Unit tests for OCC option symbol parser."""
import pytest
from datetime import date, timedelta

from app.utils.option_symbol import parse_option_symbol


class TestParseOptionSymbol:
    """Tests for parse_option_symbol()."""

    def test_valid_put_symbol(self):
        result = parse_option_symbol("NFLX281215P00105000")
        assert result["normalized_symbol"] == "NFLX281215P00105000"
        assert result["ticker"] == "NFLX"
        assert result["expiration"] == date(2028, 12, 15)
        assert result["option_type"] == "put"
        assert result["strike"] == 105.0

    def test_valid_call_symbol(self):
        result = parse_option_symbol("AAPL300117C00150000")
        assert result["ticker"] == "AAPL"
        assert result["expiration"] == date(2030, 1, 17)
        assert result["option_type"] == "call"
        assert result["strike"] == 150.0

    def test_case_insensitive(self):
        result = parse_option_symbol("nflx281215p00105000")
        assert result["normalized_symbol"] == "NFLX281215P00105000"

    def test_single_letter_ticker(self):
        result = parse_option_symbol("F300620C00010000")
        assert result["ticker"] == "F"

    def test_six_letter_ticker(self):
        result = parse_option_symbol("GOOGLS300620C00100000")
        assert result["ticker"] == "GOOGLS"

    def test_strike_with_cents(self):
        # 00152500 = 152.500 -> $152.50
        result = parse_option_symbol("AAPL300117C00152500")
        assert result["strike"] == 152.5

    def test_invalid_format_empty(self):
        with pytest.raises(ValueError, match="non-empty string"):
            parse_option_symbol("")

    def test_invalid_format_no_match(self):
        with pytest.raises(ValueError, match="OCC format"):
            parse_option_symbol("BADFORMAT")

    def test_invalid_format_lowercase_type(self):
        # After normalization 'p' becomes 'P', so this is actually valid
        result = parse_option_symbol("NFLX281215p00105000")
        assert result["option_type"] == "put"

    def test_invalid_date(self):
        # 990230 = Feb 30, which doesn't exist
        with pytest.raises(ValueError):
            parse_option_symbol("AAPL990230C00100000")

    def test_past_expiration(self):
        # Use a clearly past date: 2020-01-17
        with pytest.raises(ValueError, match="past"):
            parse_option_symbol("AAPL200117C00100000")

    def test_expiration_today_is_valid(self):
        # Today's expiration is valid — options expire at market close, not midnight
        today = date.today()
        symbol = f"AAPL{today.strftime('%y%m%d')}C00100000"
        result = parse_option_symbol(symbol)
        assert result["expiration"] == today

    def test_expiration_tomorrow_is_valid(self):
        tomorrow = date.today() + timedelta(days=1)
        symbol = f"AAPL{tomorrow.strftime('%y%m%d')}C00100000"
        result = parse_option_symbol(symbol)
        assert result["expiration"] == tomorrow

    def test_none_input(self):
        with pytest.raises((ValueError, AttributeError)):
            parse_option_symbol(None)
