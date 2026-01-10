# yfinance API Differences: Historical vs Current Data

## Overview

yfinance provides different methods and behaviors for fetching historical data vs current day's data. Understanding these differences is crucial for reliable data fetching.

## Key Differences

### 1. **Historical Data (Past Dates)**
- **Method**: `stock.history(start=date1, end=date2)`
- **Returns**: Daily aggregated OHLC data (one row per trading day)
- **Availability**: Always available for past dates
- **Data Structure**: DataFrame with date index, columns: Open, High, Low, Close, Volume
- **Example**:
  ```python
  hist = stock.history(start='2026-01-01', end='2026-01-08')
  # Returns: Daily data for Jan 1-8, 2026
  ```

### 2. **Current Day - Intraday Data**
- **Method**: `stock.history(period='1d', interval='1m')`
- **Returns**: Minute-by-minute data for the current/last trading day
- **Availability**: Only available during/after market hours
- **Data Structure**: DataFrame with timestamp index (minute-level), same OHLC columns
- **Limitations**: 
  - Returns empty if market hasn't opened yet
  - Returns empty if market is closed and data hasn't been finalized
  - May return previous day's data if today is a weekend/holiday
- **Example**:
  ```python
  intraday = stock.history(period='1d', interval='1m')
  # Returns: Minute-by-minute data for today (if market is open)
  ```

### 3. **Current Day - Daily Aggregated**
- **Method**: `stock.history(start=today, end=today+1)`
- **Returns**: Daily aggregated OHLC for today (if available)
- **Availability**: Only available after market closes and data is finalized
- **Data Structure**: DataFrame with date index, one row for today
- **Limitations**:
  - Returns empty if market hasn't closed yet
  - Returns empty on weekends/holidays
  - May have delays after market close
- **Example**:
  ```python
  today_data = stock.history(start='2026-01-09', end='2026-01-10')
  # Returns: Daily data for Jan 9, 2026 (if market closed and data available)
  ```

## Common Issues

### Issue 1: Requesting Today's Data Before Market Closes
- **Problem**: `stock.history(start=today, end=today+1)` returns empty if market is still open
- **Solution**: Use `period='1d', interval='1m'` during market hours, or wait until after market close

### Issue 2: Requesting Today's Data on Weekends
- **Problem**: Both methods return empty on weekends
- **Solution**: Check if today is a trading day, or fetch yesterday's data instead

### Issue 3: Data Not Immediately Available After Market Close
- **Problem**: Even after 4 PM ET, today's daily data might not be available immediately
- **Solution**: Use a fallback to fetch yesterday's data, or retry after a delay

## Best Practices

1. **For Historical Data**: Always use `start/end` dates
2. **For Current Day During Market Hours**: Use `period='1d', interval='1m'` and aggregate
3. **For Current Day After Market Close**: Try `start=today, end=today+1` first, fallback to `period='5d'` to get recent days
4. **For Incremental Updates**: Fetch a wider range (e.g., last 5 days) and filter to only new dates

## Recommended Approach for Scheduler

When `latest_date` is yesterday and today's data isn't available:
1. Try `period='5d'` to get last 5 days (includes today if available, yesterday if not)
2. Filter to only dates after `latest_date`
3. This handles both "today not available yet" and "weekend/holiday" scenarios
