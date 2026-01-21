"""Delete stock price data for specific dates to test scheduler."""
from sqlmodel import Session, select, delete
from app.database import engine
from app.models.stock_price import StockPrice
from datetime import date

def delete_stock_data_for_dates(dates_to_delete):
    """
    Delete stock price data for specific dates.
    
    Args:
        dates_to_delete: List of date objects to delete
    """
    with Session(engine) as session:
        for target_date in dates_to_delete:
            # Count records before deletion
            count_stmt = select(StockPrice).where(StockPrice.price_date == target_date)
            records = session.exec(count_stmt).all()
            count = len(records)
            
            if count == 0:
                print(f"No records found for {target_date}")
                continue
            
            # Show what will be deleted
            print(f"\nFound {count} records for {target_date}:")
            tickers = set(r.ticker for r in records)
            print(f"  Tickers: {', '.join(sorted(tickers))}")
            
            # Delete the records
            delete_stmt = delete(StockPrice).where(StockPrice.price_date == target_date)
            session.exec(delete_stmt)
            session.commit()
            
            print(f"✓ Deleted {count} records for {target_date}")

if __name__ == "__main__":
    # Dates to delete: 2026-01-20 and 2026-01-16
    dates_to_delete = [
        date(2026, 1, 20),
        date(2026, 1, 16)
    ]
    
    print("=" * 80)
    print("Deleting stock price data for test dates")
    print("=" * 80)
    
    delete_stock_data_for_dates(dates_to_delete)
    
    print("\n" + "=" * 80)
    print("✓ Deletion complete!")
    print("=" * 80)
    print("\nYou can now run the scheduler to test if it repopulates the data.")
    
    print("\n" + "=" * 80)
    print("✓ Deletion complete!")
    print("=" * 80)
    print("\nYou can now run the scheduler to test if it repopulates the data.")
