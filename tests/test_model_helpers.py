"""Tests for model helper functions."""
import pytest
from datetime import date, datetime
from decimal import Decimal
from app.helpers.model_helpers import (
    get_model_fields,
    format_field_value,
    field_name_to_label,
    model_to_dict,
    model_instance_to_table_row,
    get_table_columns
)
from app.models.stock_price import StockAttributes


class TestGetModelFields:
    """Tests for get_model_fields function."""

    def test_get_model_fields_returns_list(self):
        """Test that get_model_fields returns a list of field names."""
        fields = get_model_fields(StockAttributes)
        assert isinstance(fields, list)
        assert len(fields) > 0
        assert "ticker" in fields
        assert "earliest_date" in fields
        assert "latest_date" in fields


class TestFormatFieldValue:
    """Tests for format_field_value function."""

    def test_format_none_value(self):
        """Test formatting None value."""
        result = format_field_value(None)
        assert result is None

    def test_format_datetime(self):
        """Test formatting datetime value."""
        dt = datetime(2026, 1, 20, 15, 30, 45)
        result = format_field_value(dt)
        assert result == "2026-01-20 15:30:45"

    def test_format_date(self):
        """Test formatting date value."""
        d = date(2026, 1, 20)
        result = format_field_value(d)
        assert result == "Jan 20, 2026"

    def test_format_decimal_yield(self):
        """Test formatting decimal value with 'yield' in field name."""
        value = Decimal("0.0375")
        result = format_field_value(value, "dividend_yield")
        assert result == "0.0375%"

    def test_format_decimal_price(self):
        """Test formatting decimal value with 'price' in field name."""
        value = Decimal("150.25")
        result = format_field_value(value, "close_price")
        assert result == "$150.2500"

    def test_format_decimal_amount(self):
        """Test formatting decimal value with 'amt' in field name."""
        value = Decimal("2.50")
        result = format_field_value(value, "dividend_amt")
        assert result == "$2.5000"

    def test_format_decimal_generic(self):
        """Test formatting generic decimal value."""
        value = Decimal("123.456")
        result = format_field_value(value, "some_field")
        assert result == "123.4560"

    def test_format_boolean_true(self):
        """Test formatting boolean True."""
        result = format_field_value(True)
        assert result == "Yes"

    def test_format_boolean_false(self):
        """Test formatting boolean False."""
        result = format_field_value(False)
        assert result == "No"

    def test_format_float(self):
        """Test formatting float value."""
        result = format_field_value(123.456)
        assert result == "123.4560"

    def test_format_string(self):
        """Test formatting string value."""
        result = format_field_value("AAPL")
        assert result == "AAPL"


class TestFieldNameToLabel:
    """Tests for field_name_to_label function."""

    def test_convert_snake_case_to_title_case(self):
        """Test converting snake_case to Title Case."""
        result = field_name_to_label("next_earnings_date")
        assert result == "Next Earnings Date"

    def test_convert_single_word(self):
        """Test converting single word."""
        result = field_name_to_label("ticker")
        assert result == "Ticker"

    def test_custom_label_override(self):
        """Test that custom labels override default conversion."""
        custom_labels = {"next_earnings_date": "Earnings"}
        result = field_name_to_label("next_earnings_date", custom_labels)
        assert result == "Earnings"

    def test_no_custom_label_uses_default(self):
        """Test that without custom label, default conversion is used."""
        custom_labels = {"other_field": "Other"}
        result = field_name_to_label("next_earnings_date", custom_labels)
        assert result == "Next Earnings Date"


class TestModelToDict:
    """Tests for model_to_dict function."""

    def test_model_to_dict_basic(self):
        """Test basic model to dict conversion."""
        attr = StockAttributes(
            ticker="AAPL",
            earliest_date=date(2024, 1, 1),
            latest_date=date(2026, 1, 20),
            dividend_amt=Decimal("0.25"),
            dividend_yield=Decimal("0.015")
        )
        result = model_to_dict(attr)

        assert "ticker" in result
        assert result["ticker"]["label"] == "Ticker"
        assert result["ticker"]["value"] == "AAPL"
        assert result["ticker"]["raw_value"] == "AAPL"

    def test_model_to_dict_with_exclude_fields(self):
        """Test model to dict with excluded fields."""
        attr = StockAttributes(
            ticker="AAPL",
            earliest_date=date(2024, 1, 1),
            latest_date=date(2026, 1, 20)
        )
        result = model_to_dict(attr, exclude_fields=["earliest_date", "latest_date"])

        assert "ticker" in result
        assert "earliest_date" not in result
        assert "latest_date" not in result

    def test_model_to_dict_with_custom_labels(self):
        """Test model to dict with custom labels."""
        attr = StockAttributes(
            ticker="AAPL",
            earliest_date=date(2024, 1, 1),
            latest_date=date(2026, 1, 20)
        )
        custom_labels = {"ticker": "Symbol"}
        result = model_to_dict(attr, custom_labels=custom_labels)

        assert result["ticker"]["label"] == "Symbol"


class TestModelInstanceToTableRow:
    """Tests for model_instance_to_table_row function."""

    def test_model_to_table_row_basic(self):
        """Test converting model to table row."""
        attr = StockAttributes(
            ticker="AAPL",
            earliest_date=date(2024, 1, 1),
            latest_date=date(2026, 1, 20)
        )
        result = model_instance_to_table_row(attr)

        assert result["ticker"] == "AAPL"
        assert result["earliest_date"] == date(2024, 1, 1)
        assert result["latest_date"] == date(2026, 1, 20)

    def test_model_to_table_row_with_extra_columns(self):
        """Test model to table row with extra columns."""
        attr = StockAttributes(
            ticker="AAPL",
            earliest_date=date(2024, 1, 1),
            latest_date=date(2026, 1, 20)
        )
        extra = {"computed_field": "value"}
        result = model_instance_to_table_row(attr, extra_columns=extra)

        assert result["ticker"] == "AAPL"
        assert result["computed_field"] == "value"

    def test_model_to_table_row_with_exclude_fields(self):
        """Test model to table row with excluded fields."""
        attr = StockAttributes(
            ticker="AAPL",
            earliest_date=date(2024, 1, 1),
            latest_date=date(2026, 1, 20)
        )
        result = model_instance_to_table_row(attr, exclude_fields=["earliest_date"])

        assert "ticker" in result
        assert "earliest_date" not in result
        assert "latest_date" in result


class TestGetTableColumns:
    """Tests for get_table_columns function."""

    def test_get_table_columns_basic(self):
        """Test getting table columns from model."""
        columns = get_table_columns(StockAttributes)

        assert isinstance(columns, list)
        assert len(columns) > 0
        assert any(col["field"] == "ticker" for col in columns)
        assert any(col["label"] == "Ticker" for col in columns)

    def test_get_table_columns_with_custom_labels(self):
        """Test getting table columns with custom labels."""
        custom_labels = {"ticker": "Symbol"}
        columns = get_table_columns(StockAttributes, custom_labels=custom_labels)

        ticker_col = next(col for col in columns if col["field"] == "ticker")
        assert ticker_col["label"] == "Symbol"

    def test_get_table_columns_with_extra_columns(self):
        """Test getting table columns with extra columns."""
        extra = [{"field": "computed", "label": "Computed Value"}]
        columns = get_table_columns(StockAttributes, extra_columns=extra)

        assert any(col["field"] == "ticker" for col in columns)
        assert any(col["field"] == "computed" for col in columns)

    def test_get_table_columns_with_exclude_fields(self):
        """Test getting table columns with excluded fields."""
        columns = get_table_columns(StockAttributes, exclude_fields=["earliest_date"])

        assert any(col["field"] == "ticker" for col in columns)
        assert not any(col["field"] == "earliest_date" for col in columns)
