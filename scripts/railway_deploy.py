"""
Railway deployment script - runs migrations and one-time setup tasks.

This script is designed to run on Railway deployment. It checks for
migration flags and runs one-time tasks that haven't been executed yet.
"""

import os
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import create_db_and_tables

# Migration flags directory
MIGRATIONS_DIR = Path("/app/data/migrations") if os.path.exists("/app/data") else Path(".migrations")
MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)

BACKFILL_ENTRY_PRICES_FLAG = MIGRATIONS_DIR / "backfill_entry_prices_done"


def run_backfill_entry_prices():
    """Run entry price backfill if not already done."""
    if BACKFILL_ENTRY_PRICES_FLAG.exists():
        print("✓ Entry price backfill already completed, skipping...")
        return
    
    print("=" * 60)
    print("Running entry price backfill migration...")
    print("=" * 60)
    
    try:
        from scripts.backfill_entry_prices import backfill_entry_prices
        backfill_entry_prices()
        
        # Mark as completed
        BACKFILL_ENTRY_PRICES_FLAG.touch()
        print("✓ Entry price backfill completed and marked as done")
    except Exception as e:
        print(f"⚠ Entry price backfill failed: {e}")
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
    run_backfill_entry_prices()
    
    print("\n" + "=" * 60)
    print("DEPLOYMENT COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
