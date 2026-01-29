"""Tests for shared type helper utilities."""
import pytest
from uuid import UUID
from app.utils.type_helpers import to_str, safe_float


class TestToStr:
    """Tests for to_str function."""

    def test_to_str_with_uuid(self):
        """UUID should be converted to string."""
        uuid_val = UUID('12345678-1234-5678-1234-567812345678')
        result = to_str(uuid_val)
        assert result == '12345678-1234-5678-1234-567812345678'
        assert isinstance(result, str)

    def test_to_str_with_string(self):
        """String should pass through unchanged."""
        result = to_str('already-a-string')
        assert result == 'already-a-string'

    def test_to_str_with_none(self):
        """None should return None."""
        result = to_str(None)
        assert result is None


class TestSafeFloat:
    """Tests for safe_float function."""

    def test_safe_float_with_valid_number(self):
        """Valid numbers should convert correctly."""
        assert safe_float(3.14) == 3.14
        assert safe_float(42) == 42.0
        assert safe_float("3.14") == 3.14

    def test_safe_float_with_none(self):
        """None should return default."""
        assert safe_float(None) == 0.0
        assert safe_float(None, default=5.0) == 5.0

    def test_safe_float_with_nan(self):
        """NaN should return default."""
        import math
        assert safe_float(float('nan')) == 0.0
        assert safe_float(float('nan'), default=10.0) == 10.0

    def test_safe_float_with_invalid_string(self):
        """Invalid string should return default."""
        assert safe_float("not-a-number") == 0.0
        assert safe_float("not-a-number", default=-1.0) == -1.0
