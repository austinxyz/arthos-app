#!/usr/bin/env python3
"""Debug script to check database status and server connection."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.database import engine, create_db_and_tables, DATABASE_URL
from sqlmodel import Session, select
from app.models.watchlist import WatchList, WatchListStock
from app.models.stock_price import StockPrice, StockAttributes

def check_database():
    """Check what's in the database."""
    print("=" * 60)
    print("DATABASE DIAGNOSTICS")
    print("=" * 60)
    print(f"\nDatabase URL: {DATABASE_URL}")
    
    if DATABASE_URL.startswith('sqlite'):
        db_file = DATABASE_URL.replace('sqlite:///', '')
        if not os.path.isabs(db_file):
            db_file = os.path.abspath(db_file)
        print(f"Database file: {db_file}")
        print(f"File exists: {os.path.exists(db_file)}")
        if os.path.exists(db_file):
            print(f"File size: {os.path.getsize(db_file)} bytes")
    
    create_db_and_tables()
    
    print("\n" + "=" * 60)
    print("DATABASE CONTENTS")
    print("=" * 60)
    
    with Session(engine) as session:
        watchlists = session.exec(select(WatchList)).all()
        print(f"\nWatchLists: {len(watchlists)}")
        for wl in watchlists:
            print(f"  - {wl.watchlist_name} (ID: {wl.watchlist_id})")
            stocks = session.exec(select(WatchListStock).where(WatchListStock.watchlist_id == wl.watchlist_id)).all()
            print(f"    Stocks: {len(stocks)}")
            for stock in stocks:
                attr = session.get(StockAttributes, stock.ticker.upper())
                earnings = attr.next_earnings_date if attr else None
                print(f"      - {stock.ticker}: earnings={earnings}")
        
        print(f"\nStockAttributes: {len(session.exec(select(StockAttributes)).all())}")
        for attr in session.exec(select(StockAttributes)).all():
            print(f"  - {attr.ticker}: earnings={attr.next_earnings_date}, latest={attr.latest_date}")
        
        print(f"\nStockPrices: {len(session.exec(select(StockPrice)).all())} total records")
        tickers = set(p.ticker for p in session.exec(select(StockPrice)).all())
        print(f"  Unique tickers: {sorted(tickers)}")

if __name__ == "__main__":
    check_database()
