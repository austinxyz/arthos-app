"""Tests for data converter utilities."""
import pytest
import pandas as pd
from datetime import date, datetime
from app.providers.base import StockPriceData
from app.providers.converters import (
    stock_price_data_to_dataframe,
    aggregate_intraday_to_daily
)


class TestStockPriceDataToDataframe:
    """Tests for stock_price_data_to_dataframe function."""

    def test_empty_list_returns_empty_dataframe(self):
        """Test that empty list returns empty DataFrame."""
        result = stock_price_data_to_dataframe([])
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 0

    def test_single_data_point(self):
        """Test converting single data point."""
        data = [
            StockPriceData(
                date=date(2026, 1, 20),
                open=150.0,
                high=152.0,
                low=149.0,
                close=151.0,
                volume=1000000
            )
        ]
        df = stock_price_data_to_dataframe(data)

        assert len(df) == 1
        assert "Open" in df.columns
        assert "High" in df.columns
        assert "Low" in df.columns
        assert "Close" in df.columns
        assert "Volume" in df.columns
        assert df.iloc[0]["Close"] == 151.0

    def test_multiple_data_points(self):
        """Test converting multiple data points."""
        data = [
            StockPriceData(
                date=date(2026, 1, 20),
                open=150.0,
                high=152.0,
                low=149.0,
                close=151.0,
                volume=1000000
            ),
            StockPriceData(
                date=date(2026, 1, 21),
                open=151.0,
                high=153.0,
                low=150.0,
                close=152.0,
                volume=1100000
            )
        ]
        df = stock_price_data_to_dataframe(data)

        assert len(df) == 2
        assert df.iloc[0]["Close"] == 151.0
        assert df.iloc[1]["Close"] == 152.0

    def test_dataframe_is_sorted_by_date(self):
        """Test that DataFrame is sorted by date ascending."""
        data = [
            StockPriceData(
                date=date(2026, 1, 21),
                open=151.0,
                high=153.0,
                low=150.0,
                close=152.0,
                volume=1100000
            ),
            StockPriceData(
                date=date(2026, 1, 20),
                open=150.0,
                high=152.0,
                low=149.0,
                close=151.0,
                volume=1000000
            )
        ]
        df = stock_price_data_to_dataframe(data)

        # Check that dates are sorted
        dates = df.index.tolist()
        assert dates[0] < dates[1]
        assert df.iloc[0]["Close"] == 151.0  # Jan 20
        assert df.iloc[1]["Close"] == 152.0  # Jan 21

    def test_preserve_time_false_uses_date_only(self):
        """Test that preserve_time=False uses date only."""
        data = [
            StockPriceData(
                date=date(2026, 1, 20),
                timestamp=datetime(2026, 1, 20, 9, 30, 0),
                open=150.0,
                high=152.0,
                low=149.0,
                close=151.0,
                volume=1000000
            )
        ]
        df = stock_price_data_to_dataframe(data, preserve_time=False)

        # Index should be date-only (time component zeroed out)
        index_date = df.index[0]
        assert index_date.hour == 0
        assert index_date.minute == 0
        assert index_date.second == 0

    def test_preserve_time_true_uses_timestamp(self):
        """Test that preserve_time=True preserves timestamp."""
        data = [
            StockPriceData(
                date=date(2026, 1, 20),
                timestamp=datetime(2026, 1, 20, 9, 30, 0),
                open=150.0,
                high=152.0,
                low=149.0,
                close=151.0,
                volume=1000000
            )
        ]
        df = stock_price_data_to_dataframe(data, preserve_time=True)

        # Index should include time component
        index_datetime = df.index[0]
        assert index_datetime.hour == 9
        assert index_datetime.minute == 30

    def test_preserve_time_true_falls_back_to_date_if_no_timestamp(self):
        """Test that preserve_time=True falls back to date if timestamp is None."""
        data = [
            StockPriceData(
                date=date(2026, 1, 20),
                timestamp=None,
                open=150.0,
                high=152.0,
                low=149.0,
                close=151.0,
                volume=1000000
            )
        ]
        df = stock_price_data_to_dataframe(data, preserve_time=True)

        # Should still work, using date
        assert len(df) == 1
        assert df.iloc[0]["Close"] == 151.0


class TestAggregateIntradayToDaily:
    """Tests for aggregate_intraday_to_daily function."""

    def test_empty_list_raises_error(self):
        """Test that empty list raises ValueError."""
        with pytest.raises(ValueError, match="Cannot aggregate empty intraday data"):
            aggregate_intraday_to_daily([])

    def test_single_data_point(self):
        """Test aggregating single data point."""
        data = [
            StockPriceData(
                date=date(2026, 1, 20),
                open=150.0,
                high=152.0,
                low=149.0,
                close=151.0,
                volume=1000000
            )
        ]
        result = aggregate_intraday_to_daily(data)

        assert result.date == date(2026, 1, 20)
        assert result.open == 150.0
        assert result.close == 151.0
        assert result.high == 152.0
        assert result.low == 149.0
        assert result.volume == 1000000

    def test_multiple_data_points_aggregates_correctly(self):
        """Test aggregating multiple intraday data points."""
        data = [
            StockPriceData(
                date=date(2026, 1, 20),
                timestamp=datetime(2026, 1, 20, 9, 30, 0),
                open=150.0,
                high=151.0,
                low=149.5,
                close=150.5,
                volume=500000
            ),
            StockPriceData(
                date=date(2026, 1, 20),
                timestamp=datetime(2026, 1, 20, 10, 30, 0),
                open=150.5,
                high=152.0,
                low=150.0,
                close=151.5,
                volume=600000
            ),
            StockPriceData(
                date=date(2026, 1, 20),
                timestamp=datetime(2026, 1, 20, 11, 30, 0),
                open=151.5,
                high=153.0,
                low=151.0,
                close=152.0,
                volume=400000
            )
        ]
        result = aggregate_intraday_to_daily(data)

        # Open should be first entry's open
        assert result.open == 150.0

        # Close should be last entry's close
        assert result.close == 152.0

        # High should be max of all highs
        assert result.high == 153.0

        # Low should be min of all lows
        assert result.low == 149.5

        # Volume should be sum of all volumes
        assert result.volume == 1500000

        # Date should match
        assert result.date == date(2026, 1, 20)

    def test_aggregation_handles_equal_values(self):
        """Test that aggregation works when all values are equal."""
        data = [
            StockPriceData(
                date=date(2026, 1, 20),
                open=150.0,
                high=150.0,
                low=150.0,
                close=150.0,
                volume=100000
            ),
            StockPriceData(
                date=date(2026, 1, 20),
                open=150.0,
                high=150.0,
                low=150.0,
                close=150.0,
                volume=100000
            )
        ]
        result = aggregate_intraday_to_daily(data)

        assert result.open == 150.0
        assert result.high == 150.0
        assert result.low == 150.0
        assert result.close == 150.0
        assert result.volume == 200000
