#!/usr/bin/env python3
"""Script to completely clear the database and verify it's empty."""
import os
import sys
from pathlib import Path

# Add the app directory to the path
sys.path.insert(0, str(Path(__file__).parent))

from app.database import engine, create_db_and_tables, DATABASE_URL
from sqlmodel import Session, select, text
from app.models.watchlist import WatchList, WatchListStock
from app.models.stock_price import StockPrice, StockAttributes
from app.models.scheduler_log import SchedulerLog

def clear_database():
    """Clear all data from the database."""
    print(f"Using database: {DATABASE_URL}")
    print(f"Database file: {os.path.abspath(DATABASE_URL.replace('sqlite:///', ''))}")
    
    create_db_and_tables()
    
    print("\nClearing all tables...")
    with Session(engine) as session:
        # Clear all tables using SQLModel
        watchlists = session.exec(select(WatchList)).all()
        for wl in watchlists:
            session.delete(wl)
        
        stocks = session.exec(select(WatchListStock)).all()
        for stock in stocks:
            session.delete(stock)
        
        prices = session.exec(select(StockPrice)).all()
        for price in prices:
            session.delete(price)
        
        attributes = session.exec(select(StockAttributes)).all()
        for attr in attributes:
            session.delete(attr)
        
        logs = session.exec(select(SchedulerLog)).all()
        for log in logs:
            session.delete(log)
        
        # Also clear old tables using raw SQL
        old_tables = ['stockcache', 'fmpcache', 'stock_price_wtrmrk']
        for table in old_tables:
            try:
                session.exec(text(f'DELETE FROM {table}'))
            except:
                pass
        
        session.commit()
    
    print("✓ All tables cleared")
    
    # Verify
    print("\nVerifying database is empty...")
    with Session(engine) as session:
        watchlist_count = len(session.exec(select(WatchList)).all())
        stock_count = len(session.exec(select(WatchListStock)).all())
        price_count = len(session.exec(select(StockPrice)).all())
        attr_count = len(session.exec(select(StockAttributes)).all())
        log_count = len(session.exec(select(SchedulerLog)).all())
        
        print(f"  WatchLists: {watchlist_count}")
        print(f"  WatchListStocks: {stock_count}")
        print(f"  StockPrices: {price_count}")
        print(f"  StockAttributes: {attr_count}")
        print(f"  SchedulerLogs: {log_count}")
        
        if all(count == 0 for count in [watchlist_count, stock_count, price_count, attr_count]):
            print("\n✅ Database is completely empty!")
            return True
        else:
            print("\n⚠️  Some data still exists")
            return False

if __name__ == "__main__":
    success = clear_database()
    sys.exit(0 if success else 1)
