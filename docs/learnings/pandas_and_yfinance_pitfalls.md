# Learnings: Avoiding Common Pitfalls

This document captures key learnings from debugging sessions to help avoid repeating the same mistakes in the future.

## 1. Pandas Boolean Checks (CRITICAL)

### The Problem
Using Python's built-in boolean checks (`if`, `not`, `and`, `or`) on pandas objects can cause the error:
```
The truth value of a Series is ambiguous. Use a.empty, a.bool(), a.item(), a.any() or a.all().
```

### ❌ DON'T DO THIS
```python
if data:                       # WRONG - ambiguous if data is a Series/DataFrame
if not data:                   # WRONG
if data and len(data) > 0:     # WRONG - 'and' evaluates both sides as booleans
if hist_data:                  # WRONG - even for lists returned by providers
```

### ✅ DO THIS INSTEAD
```python
# For DataFrames:
if data.empty:                 # Check if DataFrame is empty
if not data.empty:             # Check if DataFrame has data

# For lists:
if data is None or len(data) == 0:    # Explicit None and length check
if data is not None and len(data) > 0: # Explicit check for data presence

# For Series inside if statements:
if isinstance(value, pd.Series):
    value = value.iloc[-1]     # Get scalar from Series before boolean check
```

### Why This Happens
When you use `if series` or `and`/`or` with a Series, Python tries to convert it to a single boolean. But a Series has multiple values, so it's ambiguous which one to use.

---

## 2. DataFrame Index Lookups with Duplicates

### The Problem
`df.loc[key, column]` returns a **Series** (not a scalar) if the index has duplicate values for that key.

### ❌ DON'T DO THIS
```python
value = df.loc[date, 'column']
if pd.notna(value):  # CRASHES if value is a Series
    result = Decimal(str(value))
```

### ✅ DO THIS INSTEAD
```python
value = df.loc[date, 'column']
if isinstance(value, pd.Series):
    value = value.iloc[-1]  # Get the last (most recent) value
if pd.notna(value):
    result = Decimal(str(value))
```

---

## 3. yfinance API Behavior

### End Date is EXCLUSIVE
yfinance's `end` parameter excludes that date from results.

```python
# To get data INCLUDING today:
stock.history(start=start_date, end=today + timedelta(days=1))

# This gets data up to but NOT including today:
stock.history(start=start_date, end=today)  # EXCLUDES today!
```

### Non-Trading Days as Start Date
If `start_date` is a non-trading day (weekend, holiday), yfinance returns **empty** even if `end_date` is valid.

```python
# WRONG - if Jan 17 is Saturday, returns empty
stock.history(start=date(2026, 1, 17), end=date(2026, 1, 21))

# CORRECT - skip weekends
while start_date.weekday() >= 5:
    start_date += timedelta(days=1)
```

---

## 4. Timezone Handling

### The Problem
`datetime.now()` uses server local time. Railway runs in **UTC**, PyCharm/local runs in **your timezone**.

### ❌ DON'T DO THIS
```python
today = datetime.now().date()  # Uses server timezone!
```

### ✅ DO THIS INSTEAD
```python
from zoneinfo import ZoneInfo

ET_TIMEZONE = ZoneInfo("America/New_York")
today = datetime.now(ET_TIMEZONE).date()  # Always Eastern Time
```

### Why This Matters for Stock Data
- Market hours are 9:30 AM - 4:00 PM **Eastern Time**
- Using server time in Railway (UTC) causes wrong date calculations
- A request at 6 PM PT on Monday might be seen as 2 AM Tuesday UTC

---

## 5. Logging for Production Debugging

### Make Logging Level Configurable
```python
import os
import logging

log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
```

### Configure at Module Level (not in run.py)
Railway doesn't use `run.py` - it runs uvicorn directly. Put logging config in `main.py`.

### Add Comprehensive Debug Logs
When debugging data flow issues, log:
- Input parameters
- API responses (type, length, first/last items)
- Intermediate data transformations
- Final output

---

## 6. Two-Step Data Fetching Pattern

The scheduler should use this simplified pattern:

```python
def fetch_stock_data(ticker):
    # Step 1: Fetch historical data if gap exists
    if no_attributes or gap_days > 1:
        hist_data = fetch_historical(start, end + 1day)  # +1 for exclusive end
    
    # Step 2: ALWAYS fetch intraday for today
    intraday = fetch_intraday(today)
    
    # Step 3: Combine and save
    all_data = hist_data + intraday
    save(all_data)
```

---

## 7. Testing Checklist

Before deploying changes to stock data fetching:

- [ ] Test with new stocks (no existing attributes)
- [ ] Test with existing stocks (has attributes, need updates)
- [ ] Test after weekends (Friday → Monday)
- [ ] Test after holidays
- [ ] Test during market hours (intraday data available)
- [ ] Test after market close (daily data finalized)
- [ ] Test in Railway production (UTC timezone)

---

## Summary of Files Fixed

| File | Issue | Fix |
|------|-------|-----|
| `stock_service.py` | `if not hist_data:` | `if hist_data is None or len(hist_data) == 0:` |
| `stock_price_service.py` | `if hist_data:` (multiple) | `if hist_data is not None and len(hist_data) > 0:` |
| `stock_price_service.py` | `if intraday_data and...` | `if intraday_data is not None and...` |
| `stock_price_service.py` | `ma_df.loc` returning Series | Added `isinstance(val, pd.Series)` check |
| `stock_price_service.py` | `datetime.now().date()` | `datetime.now(ET_TIMEZONE).date()` |
| `stock_price_service.py` | `end_date = today` | `end_date = today + timedelta(days=1)` |

---

*Last updated: January 20, 2026*
