"""Test what data new stocks actually get."""
import yfinance as yf
from datetime import date, timedelta

ticker = "AAPL"
today = date(2026, 1, 20)  # Tuesday

print(f"Testing NEW STOCK behavior for {ticker}")
print(f"Today: {today} (Tuesday)")
print("=" * 70)

# Simulate new stock: 2 years ago to today
print("\nNEW STOCK: 2 years ago to today")
start = today - timedelta(days=730)
end = today
print(f"Range: {start} to {end}")

stock = yf.Ticker(ticker)
hist = stock.history(start=start, end=end)

print(f"Result: {len(hist)} rows")
if not hist.empty:
    print(f"First date: {hist.index[0].date()}")
    print(f"Last date: {hist.index[-1].date()}")
    
    # Check if today's data is included
    dates = [idx.date() for idx in hist.index]
    if today in dates:
        print(f"\n✅ TODAY'S DATA ({today}) IS INCLUDED!")
        today_row = hist[hist.index.date == today].iloc[0]
        print(f"   Close: ${today_row['Close']:.2f}")
    else:
        print(f"\n❌ TODAY'S DATA ({today}) IS NOT INCLUDED")
        print(f"   Most recent date: {dates[-1]}")
else:
    print("Empty DataFrame")
