"""
Railway deployment script - runs migrations and one-time setup tasks.

This script is designed to run on Railway deployment. It checks for
migration flags and runs one-time tasks that haven't been executed yet.
"""

import os
import sys
from pathlib import Path
from sqlalchemy import select

# Add current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import create_db_and_tables, engine
from app.models.watchlist import WatchListStock
from app.models.stock_price import StockPrice
from sqlmodel import Session

# Migration flags directory
MIGRATIONS_DIR = Path("/app/data/migrations") if os.path.exists("/app/data") else Path(".migrations")
MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)

BACKFILL_ENTRY_PRICES_FLAG = MIGRATIONS_DIR / "backfill_entry_prices_done"


def backfill_entry_prices():
    """Backfill entry_price for existing watchlist stocks."""
    print("=" * 60)
    print("Backfilling entry_price for existing watchlist stocks")
    print("=" * 60)
    
    updated_count = 0
    skipped_count = 0
    no_data_count = 0
    
    with Session(engine) as session:
        # Get all watchlist stocks without entry_price
        statement = select(WatchListStock).where(WatchListStock.entry_price == None)
        stocks_without_price = session.exec(statement).all()
        
        print(f"Found {len(stocks_without_price)} stocks without entry_price")
        
        for stock in stocks_without_price:
            ticker = stock.ticker.upper()
            date_added = stock.date_added.date() if hasattr(stock.date_added, 'date') else stock.date_added
            
            # Try to get closing price on the date added
            price_statement = select(StockPrice).where(
                StockPrice.ticker == ticker,
                StockPrice.price_date == date_added
            )
            price_record = session.exec(price_statement).first()
            
            if not price_record:
                # Fallback: get the closest price before or on that date
                price_statement = select(StockPrice).where(
                    StockPrice.ticker == ticker,
                    StockPrice.price_date <= date_added
                ).order_by(StockPrice.price_date.desc())
                price_record = session.exec(price_statement).first()
            
            if not price_record:
                # Last fallback: get the earliest available price
                price_statement = select(StockPrice).where(
                    StockPrice.ticker == ticker
                ).order_by(StockPrice.price_date.asc())
                price_record = session.exec(price_statement).first()
            
            if price_record and price_record.close_price:
                # Update the entry_price
                # Need to refetch stock in current session to update
                db_stock = session.get(WatchListStock, (stock.watchlist_id, stock.ticker))
                if db_stock:
                    db_stock.entry_price = price_record.close_price
                    session.add(db_stock)
                    updated_count += 1
                    print(f"  ✓ {ticker}: entry_price = ${price_record.close_price:.2f} (from {price_record.price_date})")
                else:
                    skipped_count += 1
                    print(f"  ⚠ {ticker}: Could not refetch stock for update")
            else:
                no_data_count += 1
                print(f"  ✗ {ticker}: No price data available in database")
        
        # Commit all updates
        session.commit()
    
    print("=" * 60)
    print(f"Backfill complete!")
    print(f"  Updated: {updated_count}")
    print(f"  No data: {no_data_count}")
    print(f"  Skipped: {skipped_count}")
    print("=" * 60)


def run_backfill_entry_prices_task():
    """Run entry price backfill if not already done."""
    if BACKFILL_ENTRY_PRICES_FLAG.exists():
        print("✓ Entry price backfill already completed, skipping...")
        return
    
    print("=" * 60)
    print("Running entry price backfill migration...")
    print("=" * 60)
    
    try:
        backfill_entry_prices()
        
        # Mark as completed
        BACKFILL_ENTRY_PRICES_FLAG.touch()
        print("✓ Entry price backfill completed and marked as done")
    except Exception as e:
        print(f"⚠ Entry price backfill failed: {e}")
        import traceback
        traceback.print_exc()
        print("This is not critical - new stocks will still get entry prices")


def main():
    """Run all deployment migrations."""
    print("=" * 60)
    print("RAILWAY DEPLOYMENT SCRIPT")
    print("=" * 60)
    
    # 1. Run database migrations
    print("\n1. Running database migrations...")
    create_db_and_tables()
    print("✓ Database migrations complete")
    
    # 2. Run one-time backfill
    print("\n2. Checking one-time migrations...")
    run_backfill_entry_prices_task()
    
    print("\n" + "=" * 60)
    print("DEPLOYMENT COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
