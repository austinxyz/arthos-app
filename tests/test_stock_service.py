"""Tests for stock service module."""
import pytest
import pandas as pd
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from app.services.stock_service import (
    fetch_stock_data,
    fetch_intraday_data,
    calculate_sma,
    calculate_devstep,
    calculate_signal,
    calculate_5day_price_movement,
    calculate_covered_call_returns_v2,
    separate_daily_intraday,
    build_option_dict,
    process_options_chain
)


class TestSeparateDailyIntraday:
    """Tests for separate_daily_intraday helper function."""

    def test_separates_daily_from_intraday(self):
        """Test that daily and intraday data are properly separated."""
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)

        # Create mixed data with daily (midnight) and intraday (with time) timestamps
        index = pd.DatetimeIndex([
            pd.Timestamp(yesterday),  # Daily - midnight
            pd.Timestamp(today).replace(hour=10, minute=30),  # Intraday
            pd.Timestamp(today).replace(hour=14, minute=0),   # Intraday
        ])
        data = pd.DataFrame({'Close': [100, 101, 102]}, index=index)

        daily, intraday = separate_daily_intraday(data)

        assert len(daily) == 1
        assert len(intraday) == 2
        assert daily['Close'].iloc[0] == 100
        assert intraday['Close'].iloc[0] == 101

    def test_all_daily_data(self):
        """Test with only daily data (no intraday)."""
        dates = pd.date_range(end=datetime.now().date() - timedelta(days=1), periods=5)
        data = pd.DataFrame({'Close': [100, 101, 102, 103, 104]}, index=dates)

        daily, intraday = separate_daily_intraday(data)

        assert len(daily) == 5
        assert len(intraday) == 0


class TestBuildOptionDict:
    """Tests for build_option_dict helper function."""

    def test_builds_complete_dict(self):
        """Test that all option fields are properly extracted."""
        option = MagicMock()
        option.contract_symbol = "AAPL230120C00150000"
        option.last_price = 5.50
        option.bid = 5.40
        option.ask = 5.60
        option.volume = 1000
        option.open_interest = 5000
        option.implied_volatility = 0.25
        option.delta = 0.55
        option.gamma = 0.03
        option.theta = -0.05
        option.vega = 0.15
        option.rho = 0.02

        result = build_option_dict(option)

        assert result['contractSymbol'] == "AAPL230120C00150000"
        assert result['lastPrice'] == 5.50
        assert result['bid'] == 5.40
        assert result['ask'] == 5.60
        assert result['volume'] == 1000
        assert result['delta'] == 0.55

    def test_handles_none_values(self):
        """Test that None values are handled gracefully."""
        option = MagicMock()
        option.contract_symbol = "AAPL230120C00150000"
        option.last_price = None
        option.bid = None
        option.ask = None
        option.volume = None
        option.open_interest = None
        option.implied_volatility = None
        option.delta = None
        option.gamma = None
        option.theta = None
        option.vega = None
        option.rho = None

        result = build_option_dict(option)

        assert result['lastPrice'] is None
        assert result['bid'] is None
        assert result['volume'] == 0  # Default for None
        assert result['delta'] is None


class TestCalculateSMA:
    """Tests for calculate_sma function."""
    
    def test_sma_with_sufficient_data(self):
        """Test SMA calculation with sufficient data points."""
        # Create sample data with 100 days
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        prices = pd.Series(range(100, 200), index=dates)
        data = pd.DataFrame({'Close': prices})
        
        sma_50 = calculate_sma(data, 50)
        # SMA of last 50 values: (150+151+...+199)/50 = 174.5
        expected = sum(range(150, 200)) / 50
        assert sma_50 == pytest.approx(expected, rel=1e-2)
    
    def test_sma_with_insufficient_data(self):
        """Test SMA calculation when data points are less than window."""
        dates = pd.date_range(start='2024-01-01', periods=30, freq='D')
        prices = pd.Series(range(100, 130), index=dates)
        data = pd.DataFrame({'Close': prices})
        
        sma_50 = calculate_sma(data, 50)
        # Should use all available data (30 points)
        expected = sum(range(100, 130)) / 30
        assert sma_50 == pytest.approx(expected, rel=1e-2)


class TestCalculateDevstep:
    """Tests for calculate_devstep function."""
    
    def test_devstep_calculation(self):
        """Test devstep calculation."""
        # Create sample data
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        prices = pd.Series([100.0] * 100, index=dates)  # Constant price
        data = pd.DataFrame({'Close': prices})
        
        sma_50 = 100.0
        devstep = calculate_devstep(data, sma_50)
        
        # With constant prices, std dev is 0, so devstep should be 0
        assert devstep == pytest.approx(0.0, abs=1e-6)
    
    def test_devstep_with_variation(self):
        """Test devstep with price variation."""
        import numpy as np
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        # Create prices with variation - gradually increasing with some noise
        np.random.seed(42)  # For reproducibility
        base_prices = [100.0 + i * 0.1 + np.random.normal(0, 1) for i in range(100)]
        prices = pd.Series(base_prices, index=dates)
        data = pd.DataFrame({'Close': prices})
        
        sma_50 = data['Close'].tail(50).mean()
        devstep = calculate_devstep(data, sma_50)
        
        # With variation, devstep should be a valid number (not NaN or inf)
        assert not (pd.isna(devstep) or np.isinf(devstep))
        assert isinstance(devstep, (int, float))


class TestCalculateSignal:
    """Tests for calculate_signal function."""
    
    def test_signal_neutral(self):
        """Test signal calculation for neutral range."""
        assert calculate_signal(0.0) == "Neutral"
        assert calculate_signal(0.5) == "Neutral"
        assert calculate_signal(-0.5) == "Neutral"
        assert calculate_signal(1.0) == "Neutral"
        assert calculate_signal(-1.0) == "Neutral"
    
    def test_signal_overbought(self):
        """Test signal calculation for overbought range."""
        assert calculate_signal(1.5) == "Overbought"
        assert calculate_signal(2.0) == "Overbought"
    
    def test_signal_extreme_overbought(self):
        """Test signal calculation for extreme overbought."""
        assert calculate_signal(2.1) == "Extreme Overbought"
        assert calculate_signal(3.0) == "Extreme Overbought"
    
    def test_signal_oversold(self):
        """Test signal calculation for oversold range."""
        assert calculate_signal(-1.5) == "Oversold"
        assert calculate_signal(-2.0) == "Oversold"
    
    def test_signal_extreme_oversold(self):
        """Test signal calculation for extreme oversold."""
        assert calculate_signal(-2.1) == "Extreme Oversold"
        assert calculate_signal(-3.0) == "Extreme Oversold"


class TestFetchStockData:
    """Tests for fetch_stock_data function."""
    
    def test_fetch_valid_ticker(self):
        """Test fetching data for a valid ticker."""
        # Use a well-known ticker like AAPL
        data = fetch_stock_data("AAPL")
        
        assert isinstance(data, pd.DataFrame)
        assert not data.empty
        assert 'Close' in data.columns
    
    def test_fetch_invalid_ticker(self):
        """Test fetching data for an invalid ticker."""
        with pytest.raises(ValueError, match="No data found|Error fetching"):
            fetch_stock_data("INVALIDTICKER12345")
    
    def test_fetch_stock_data_includes_intraday_if_available(self):
        """Test that fetch_stock_data includes intraday data for today if available."""
        # Fetch data for a well-known ticker
        data = fetch_stock_data("AAPL")
        
        assert isinstance(data, pd.DataFrame)
        assert not data.empty
        assert 'Close' in data.columns
        
        # Check if we have intraday data (timestamps with time components)
        # Intraday data will have hour/minute components, daily data won't
        last_timestamp = pd.Timestamp(data.index[-1])
        has_intraday = last_timestamp.hour != 0 or last_timestamp.minute != 0
        
        # If market is open, we should have intraday data
        # If market is closed, we might not have it
        # So we just verify the data structure is correct
        if has_intraday:
            # We have intraday data - verify it's for today
            today = datetime.now().date()
            assert last_timestamp.date() == today, "Intraday data should be for today"
        
        # Verify the data has the expected columns
        assert all(col in data.columns for col in ['Open', 'High', 'Low', 'Close', 'Volume'])
    
    def test_fetch_intraday_data(self):
        """Test fetching intraday data for current day."""
        # Try to fetch intraday data
        intraday = fetch_intraday_data("AAPL")
        
        # Intraday data may or may not be available depending on market hours
        if intraday is not None:
            assert isinstance(intraday, pd.DataFrame)
            assert not intraday.empty
            assert 'Close' in intraday.columns
            
            # Verify it's for today
            today = datetime.now().date()
            intraday_dates = set([pd.Timestamp(ts).date() for ts in intraday.index])
            assert today in intraday_dates, "Intraday data should be for today"
            
            # Verify timestamps have time components
            has_time = any(
                pd.Timestamp(ts).hour != 0 or pd.Timestamp(ts).minute != 0 
                for ts in intraday.index
            )
            assert has_time, "Intraday data should have time components"


class TestCalculate5DayPriceMovement:
    """Tests for calculate_5day_price_movement function."""
    
    def test_5day_movement_calculation(self):
        """Test 5-day price movement calculation."""
        # Create sample data with enough days
        dates = pd.date_range(start='2024-01-01', periods=100, freq='D')
        prices = pd.Series([100.0 + i * 0.1 for i in range(100)], index=dates)
        data = pd.DataFrame({'Close': prices})
        
        sma_50 = 105.0
        movement, is_positive = calculate_5day_price_movement(data, sma_50)
        
        # Should return valid values
        assert isinstance(movement, (int, float))
        assert isinstance(is_positive, bool)
        import numpy as np
        assert not (pd.isna(movement) or np.isinf(movement))


class TestCalculateCoveredCallReturnsV2:
    """Tests for enhanced covered call returns calculation (v2)."""

    def test_basic_calculation_with_otm_call(self):
        """Test basic covered call calculation with Out-of-The-Money call."""
        # Current stock price: $100
        current_price = 100.0

        # Mock options data: One expiration, one strike
        # Expiration: 30 days from now
        expiration_date = (datetime.now().date() + timedelta(days=30)).strftime('%Y-%m-%d')

        options_data = [
            (expiration_date, {
                105.0: {  # Strike at $105 (OTM - above current price)
                    'call': {
                        'bid': 2.0,
                        'ask': 2.2,
                        'lastPrice': 2.1
                    }
                }
            })
        ]

        result = calculate_covered_call_returns_v2(options_data, current_price)

        # Should return one covered call opportunity
        assert len(result) == 1
        cc = result[0]

        # Verify structure
        assert cc['expirationDate'] == expiration_date
        assert cc['strike'] == 105.0
        assert cc['callPremium'] == 2.1  # Average of bid and ask

        # Verify return calculations
        # If exercised: (105 + 2.1 - 100) = 7.1
        assert cc['returnExercised'] == 7.1
        assert cc['returnPctExercised'] == pytest.approx(7.1, rel=0.01)  # 7.1%

        # Annualized return exercised: (7.1 * 365) / 30 = 86.42%
        assert cc['annualizedReturnExercised'] == pytest.approx(86.42, rel=0.01)

        # If not exercised: 2.1
        assert cc['returnNotExercised'] == 2.1
        assert cc['returnPctNotExercised'] == pytest.approx(2.1, rel=0.01)

        # Annualized return not exercised: (2.1 * 365) / 30 = 25.55%
        assert cc['annualizedReturnNotExercised'] == pytest.approx(25.55, rel=0.01)

        # Stock appreciation: (105 - 100) / 100 = 5%
        assert cc['stockAppreciationPct'] == pytest.approx(5.0, rel=0.01)

        # Call premium: 2.1 / 100 = 2.1%
        assert cc['callPremiumPct'] == pytest.approx(2.1, rel=0.01)

    def test_filter_itm_calls(self):
        """Test that In-The-Money calls (strike < current price) are filtered out."""
        current_price = 100.0

        # Expiration: 45 days from now
        expiration_date = (datetime.now().date() + timedelta(days=45)).strftime('%Y-%m-%d')

        options_data = [
            (expiration_date, {
                95.0: {  # Strike at $95 (ITM - below current price - should be filtered out)
                    'call': {
                        'bid': 6.0,
                        'ask': 6.4,
                        'lastPrice': 6.2
                    }
                },
                100.0: {  # Strike at $100 (ATM - at current price - should be included)
                    'call': {
                        'bid': 3.0,
                        'ask': 3.2,
                        'lastPrice': 3.1
                    }
                },
                105.0: {  # Strike at $105 (OTM - above current price - should be included)
                    'call': {
                        'bid': 2.0,
                        'ask': 2.2,
                        'lastPrice': 2.1
                    }
                }
            })
        ]

        result = calculate_covered_call_returns_v2(options_data, current_price)

        # Should only include ATM (100) and OTM (105) calls, not ITM (95)
        assert len(result) == 2

        strikes_in_result = [r['strike'] for r in result]
        assert 95.0 not in strikes_in_result, "ITM call (strike < current price) should be filtered out"
        assert 100.0 in strikes_in_result, "ATM call (strike = current price) should be included"
        assert 105.0 in strikes_in_result, "OTM call (strike > current price) should be included"

    def test_filter_premium_threshold(self):
        """Test that options with premium <= 1% are filtered out, only premium > 1% included."""
        current_price = 100.0
        expiration_date = (datetime.now().date() + timedelta(days=30)).strftime('%Y-%m-%d')

        options_data = [
            (expiration_date, {
                105.0: {  # Premium = 0.5 (0.5% - should be filtered out)
                    'call': {
                        'bid': 0.4,
                        'ask': 0.6,
                        'lastPrice': 0.5
                    }
                },
                107.5: {  # Premium = 1.0 (exactly 1.0% - should be filtered out)
                    'call': {
                        'bid': 1.0,
                        'ask': 1.0,
                        'lastPrice': 1.0
                    }
                },
                110.0: {  # Premium = 1.5 (1.5% - should be included)
                    'call': {
                        'bid': 1.4,
                        'ask': 1.6,
                        'lastPrice': 1.5
                    }
                },
                112.0: {  # Premium = 1.01 (1.01% - should be included)
                    'call': {
                        'bid': 1.01,
                        'ask': 1.01,
                        'lastPrice': 1.01
                    }
                }
            })
        ]

        result = calculate_covered_call_returns_v2(options_data, current_price)

        # Should only include strikes with premium > 1% (110 and 112, not 105 or 107.5)
        assert len(result) == 2
        assert result[0]['strike'] in [110.0, 112.0]
        assert result[1]['strike'] in [110.0, 112.0]

        # Verify exactly 1% is filtered out
        strikes_in_result = [r['strike'] for r in result]
        assert 105.0 not in strikes_in_result, "0.5% premium should be filtered out"
        assert 107.5 not in strikes_in_result, "Exactly 1.0% premium should be filtered out"
        assert 110.0 in strikes_in_result, "1.5% premium should be included"
        assert 112.0 in strikes_in_result, "1.01% premium should be included"

    def test_filter_strike_price_and_premium_combined(self):
        """Test that both strike price (>= current) and premium (> 1%) filters work together."""
        current_price = 100.0
        expiration_date = (datetime.now().date() + timedelta(days=30)).strftime('%Y-%m-%d')

        options_data = [
            (expiration_date, {
                90.0: {  # ITM, good premium (7%) - should be filtered (ITM)
                    'call': {
                        'bid': 7.0,
                        'ask': 7.0,
                        'lastPrice': 7.0
                    }
                },
                95.0: {  # ITM, good premium (5%) - should be filtered (ITM)
                    'call': {
                        'bid': 5.0,
                        'ask': 5.0,
                        'lastPrice': 5.0
                    }
                },
                99.0: {  # ITM, good premium (3%) - should be filtered (ITM)
                    'call': {
                        'bid': 3.0,
                        'ask': 3.0,
                        'lastPrice': 3.0
                    }
                },
                100.0: {  # ATM, bad premium (0.5%) - should be filtered (low premium)
                    'call': {
                        'bid': 0.5,
                        'ask': 0.5,
                        'lastPrice': 0.5
                    }
                },
                102.0: {  # OTM, good premium (2%) - should be INCLUDED
                    'call': {
                        'bid': 2.0,
                        'ask': 2.0,
                        'lastPrice': 2.0
                    }
                },
                105.0: {  # OTM, bad premium (0.8%) - should be filtered (low premium)
                    'call': {
                        'bid': 0.8,
                        'ask': 0.8,
                        'lastPrice': 0.8
                    }
                },
                110.0: {  # OTM, good premium (3%) - should be INCLUDED
                    'call': {
                        'bid': 3.0,
                        'ask': 3.0,
                        'lastPrice': 3.0
                    }
                }
            })
        ]

        result = calculate_covered_call_returns_v2(options_data, current_price)

        # Should only include OTM calls with premium > 1%: 102 and 110
        assert len(result) == 2

        strikes_in_result = [r['strike'] for r in result]

        # ITM calls should be filtered out (even with good premiums)
        assert 90.0 not in strikes_in_result, "ITM call should be filtered (strike < current)"
        assert 95.0 not in strikes_in_result, "ITM call should be filtered (strike < current)"
        assert 99.0 not in strikes_in_result, "ITM call should be filtered (strike < current)"

        # ATM/OTM calls with low premium should be filtered out
        assert 100.0 not in strikes_in_result, "ATM call with low premium should be filtered"
        assert 105.0 not in strikes_in_result, "OTM call with low premium should be filtered"

        # Only ATM/OTM calls with good premium should be included
        assert 102.0 in strikes_in_result, "OTM call with good premium should be included"
        assert 110.0 in strikes_in_result, "OTM call with good premium should be included"

    def test_ranking_similar_returns(self):
        """Test that ranking prioritizes options where exercised and not-exercised returns are similar."""
        current_price = 100.0
        expiration_date = (datetime.now().date() + timedelta(days=30)).strftime('%Y-%m-%d')

        options_data = [
            (expiration_date, {
                105.0: {  # Returns: exercised=7%, not-exercised=2% (diff=5%)
                    'call': {
                        'bid': 2.0,
                        'ask': 2.0,
                        'lastPrice': 2.0
                    }
                },
                103.0: {  # Returns: exercised=4.5%, not-exercised=1.5% (diff=3%)
                    'call': {
                        'bid': 1.5,
                        'ask': 1.5,
                        'lastPrice': 1.5
                    }
                },
                102.0: {  # Returns: exercised=3.2%, not-exercised=1.2% (diff=2%)
                    'call': {
                        'bid': 1.2,
                        'ask': 1.2,
                        'lastPrice': 1.2
                    }
                }
            })
        ]

        result = calculate_covered_call_returns_v2(options_data, current_price)

        assert len(result) == 3

        # The first result should have the smallest return difference
        assert result[0]['strike'] == 102.0  # Smallest difference
        assert result[1]['strike'] == 103.0  # Medium difference
        assert result[2]['strike'] == 105.0  # Largest difference

    def test_multiple_expirations(self):
        """Test handling of multiple expiration dates."""
        current_price = 100.0

        exp1 = (datetime.now().date() + timedelta(days=15)).strftime('%Y-%m-%d')
        exp2 = (datetime.now().date() + timedelta(days=30)).strftime('%Y-%m-%d')
        exp3 = (datetime.now().date() + timedelta(days=60)).strftime('%Y-%m-%d')

        options_data = [
            (exp1, {
                105.0: {
                    'call': {'bid': 1.5, 'ask': 1.5, 'lastPrice': 1.5}
                }
            }),
            (exp2, {
                105.0: {
                    'call': {'bid': 2.0, 'ask': 2.0, 'lastPrice': 2.0}
                }
            }),
            (exp3, {
                105.0: {
                    'call': {'bid': 3.0, 'ask': 3.0, 'lastPrice': 3.0}
                }
            })
        ]

        result = calculate_covered_call_returns_v2(options_data, current_price)

        # Should return all three (same strike, different expirations)
        assert len(result) == 3

        # Verify that annualized returns are higher for shorter durations
        # (same absolute return but fewer days means higher annualized return)
        exp1_result = [cc for cc in result if cc['expirationDate'] == exp1][0]
        exp3_result = [cc for cc in result if cc['expirationDate'] == exp3][0]

        # Shorter expiration should have higher annualized return
        assert exp1_result['annualizedReturnNotExercised'] > exp3_result['annualizedReturnNotExercised']

    def test_filter_beyond_three_months(self):
        """Test that expirations beyond 90 days are filtered out."""
        current_price = 100.0

        exp_within = (datetime.now().date() + timedelta(days=89)).strftime('%Y-%m-%d')
        exp_beyond = (datetime.now().date() + timedelta(days=91)).strftime('%Y-%m-%d')

        options_data = [
            (exp_within, {
                105.0: {
                    'call': {'bid': 2.0, 'ask': 2.0, 'lastPrice': 2.0}
                }
            }),
            (exp_beyond, {
                105.0: {
                    'call': {'bid': 3.0, 'ask': 3.0, 'lastPrice': 3.0}
                }
            })
        ]

        result = calculate_covered_call_returns_v2(options_data, current_price)

        # Should only include expiration within 90 days
        assert len(result) == 1
        assert result[0]['expirationDate'] == exp_within

    def test_empty_input(self):
        """Test handling of empty input."""
        result = calculate_covered_call_returns_v2([], 100.0)
        assert result == []

        result = calculate_covered_call_returns_v2(None, 100.0)
        assert result == []

    def test_invalid_current_price(self):
        """Test handling of invalid current price."""
        expiration_date = (datetime.now().date() + timedelta(days=30)).strftime('%Y-%m-%d')
        options_data = [
            (expiration_date, {
                105.0: {
                    'call': {'bid': 2.0, 'ask': 2.0, 'lastPrice': 2.0}
                }
            })
        ]

        # Zero price
        result = calculate_covered_call_returns_v2(options_data, 0)
        assert result == []

        # None price
        result = calculate_covered_call_returns_v2(options_data, None)
        assert result == []

        # Negative price
        result = calculate_covered_call_returns_v2(options_data, -100)
        assert result == []

    def test_missing_bid_ask_uses_last_price(self):
        """Test that when bid/ask are missing, last price is used."""
        current_price = 100.0
        expiration_date = (datetime.now().date() + timedelta(days=30)).strftime('%Y-%m-%d')

        options_data = [
            (expiration_date, {
                105.0: {
                    'call': {
                        'bid': None,
                        'ask': None,
                        'lastPrice': 2.5
                    }
                }
            })
        ]

        result = calculate_covered_call_returns_v2(options_data, current_price)

        # Should use last price as premium
        assert len(result) == 1
        assert result[0]['callPremium'] == 2.5

    def test_no_call_data_skipped(self):
        """Test that strikes without call data are skipped."""
        current_price = 100.0
        expiration_date = (datetime.now().date() + timedelta(days=30)).strftime('%Y-%m-%d')

        options_data = [
            (expiration_date, {
                105.0: {
                    'call': None  # No call data
                },
                110.0: {
                    'call': {'bid': 2.0, 'ask': 2.0, 'lastPrice': 2.0}
                }
            })
        ]

        result = calculate_covered_call_returns_v2(options_data, current_price)

        # Should only include 110 strike
        assert len(result) == 1
        assert result[0]['strike'] == 110.0
