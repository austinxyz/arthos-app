"""Check what stock price data exists for AAPL."""
from sqlmodel import Session, select
from app.database import engine
from app.models.stock_price import StockPrice
from datetime import date

def check_aapl_data():
    """Check AAPL stock price data."""
    with Session(engine) as session:
        # Get all AAPL records
        stmt = select(StockPrice).where(StockPrice.ticker == "AAPL").order_by(StockPrice.price_date.desc())
        records = session.exec(stmt).all()
        
        print("=" * 80)
        print(f"Found {len(records)} total records for AAPL")
        print("=" * 80)
        
        if records:
            print("\nMost recent 10 records:")
            print("-" * 80)
            for record in records[:10]:
                print(f"  {record.price_date}: Open=${record.open_price}, Close=${record.close_price}")
            
            # Check specifically for 1/20 and 1/16
            print("\n" + "=" * 80)
            print("Checking for specific dates:")
            print("=" * 80)
            
            for check_date in [date(2026, 1, 20), date(2026, 1, 16)]:
                found = [r for r in records if r.price_date == check_date]
                if found:
                    print(f"\n❌ FOUND data for {check_date}:")
                    for r in found:
                        print(f"   Ticker: {r.ticker}, Open: ${r.open_price}, Close: ${r.close_price}")
                else:
                    print(f"\n✓ No data found for {check_date}")

if __name__ == "__main__":
    check_aapl_data()
