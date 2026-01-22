"""
One-time script to backfill entry_price for existing watchlist stocks.

This script populates entry_price using the closing price from stock_price table
based on the date the stock was added to the watchlist. If no data exists for
that exact date, it uses the earliest available price.

Usage:
    python -m scripts.backfill_entry_prices
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select
from app.database import engine
from app.models.watchlist import WatchListStock
from app.models.stock_price import StockPrice
from datetime import date


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


if __name__ == "__main__":
    backfill_entry_prices()
