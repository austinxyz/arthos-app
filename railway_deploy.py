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
from sqlmodel import Session, text

# Migration flags directory
MIGRATIONS_DIR = Path("/app/data/migrations") if os.path.exists("/app/data") else Path(".migrations")
MIGRATIONS_DIR.mkdir(parents=True, exist_ok=True)

BACKFILL_ENTRY_PRICES_FLAG = MIGRATIONS_DIR / "backfill_entry_prices_done"
FIX_WATCHLIST_UUID_TYPE_FLAG = MIGRATIONS_DIR / "fix_watchlist_uuid_type_done"
CLEANUP_INVALID_TICKERS_FLAG = MIGRATIONS_DIR / "cleanup_invalid_tickers_done"
SEED_LLM_MODELS_FLAG = MIGRATIONS_DIR / "seed_llm_models_done"


def cleanup_invalid_tickers():
    """
    Remove invalid/test tickers from the database.

    These tickers were added before proper validation was in place:
    - AAPK: Invalid ticker
    - APPL: Misspelled Apple (should be AAPL)
    - SDSK: Invalid ticker
    - SDK: Invalid ticker
    """
    # Tickers to remove - these have no valid price data
    INVALID_TICKERS = ['AAPK', 'APPL', 'SDSK', 'SDK']

    print(f"  Cleaning up invalid tickers: {INVALID_TICKERS}")

    with engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        for ticker in INVALID_TICKERS:
            # Delete from watchlist_stocks
            result = conn.execute(text(
                "DELETE FROM watchlist_stocks WHERE ticker = :ticker"
            ), {"ticker": ticker})
            ws_count = result.rowcount

            # Delete from stock_price
            result = conn.execute(text(
                "DELETE FROM stock_price WHERE ticker = :ticker"
            ), {"ticker": ticker})
            sp_count = result.rowcount

            # Delete from stock_attributes
            result = conn.execute(text(
                "DELETE FROM stock_attributes WHERE ticker = :ticker"
            ), {"ticker": ticker})
            sa_count = result.rowcount

            if ws_count or sp_count or sa_count:
                print(f"    - {ticker}: removed {ws_count} watchlist entries, {sp_count} prices, {sa_count} attributes")
            else:
                print(f"    - {ticker}: not found (already clean)")

    print("  ✓ Invalid tickers cleanup complete")
    return True


def run_cleanup_invalid_tickers():
    """Run invalid tickers cleanup if not already done."""
    if CLEANUP_INVALID_TICKERS_FLAG.exists():
        print("✓ Invalid tickers cleanup already completed, skipping...")
        return

    print("=" * 60)
    print("Running invalid tickers cleanup...")
    print("=" * 60)

    try:
        cleanup_invalid_tickers()

        # Mark as completed
        CLEANUP_INVALID_TICKERS_FLAG.touch()
        print("✓ Invalid tickers cleanup completed and marked as done")
    except Exception as e:
        print(f"⚠ Invalid tickers cleanup failed: {e}")
        import traceback
        traceback.print_exc()
        # Not critical - don't raise


def migrate_watchlist_uuid_to_varchar():
    """
    Migrate existing watchlist.watchlist_id from UUID to VARCHAR(36).

    This is needed because the original table used UUID type but our foreign
    key references (watchlist_stocks, watchlist_stock_notes) use VARCHAR(36)
    for SQLite compatibility. PostgreSQL requires exact type matches for FKs.
    """
    print("  Checking if watchlist.watchlist_id needs type migration...")

    # Use autocommit mode for DDL operations to avoid transaction issues
    from sqlalchemy.engine import Engine
    original_isolation_level = engine.execution_options.isolation_level if hasattr(engine.execution_options, 'isolation_level') else None

    with engine.connect() as conn:
        # Set autocommit mode for DDL
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")

        # Check current type of watchlist_id
        result = conn.execute(text("""
            SELECT data_type
            FROM information_schema.columns
            WHERE table_name = 'watchlist'
            AND column_name = 'watchlist_id'
        """))
        current_type = result.scalar()

        if current_type and 'uuid' in current_type.lower():
            print(f"  Found watchlist_id type: {current_type}")
            print("  Migrating watchlist_id from UUID to VARCHAR(36)...")

            # Step 1: Drop foreign key constraints that reference watchlist.watchlist_id
            # Using separate execution blocks to avoid transaction abort issues
            print("    - Dropping foreign key constraints...")

            # Drop watchlist_stocks FK
            try:
                conn.execute(text("ALTER TABLE watchlist_stocks DROP CONSTRAINT IF EXISTS watchlist_stocks_watchlist_id_fkey"))
                print("      - Dropped watchlist_stocks foreign key")
            except Exception as e:
                print(f"      - watchlist_stocks FK: {e}")

            # Drop watchlist_stock_notes FK (table may not exist yet)
            try:
                conn.execute(text("ALTER TABLE watchlist_stock_notes DROP CONSTRAINT IF EXISTS watchlist_stock_notes_watchlist_id_fkey"))
                print("      - Dropped watchlist_stock_notes foreign key")
            except Exception as e:
                print(f"      - watchlist_stock_notes FK: {e}")

            # Step 2: Change watchlist_id type from UUID to VARCHAR(36)
            print("    - Altering watchlist.watchlist_id type to VARCHAR(36)...")
            conn.execute(text("""
                ALTER TABLE watchlist
                ALTER COLUMN watchlist_id TYPE VARCHAR(36)
                USING watchlist_id::text
            """))

            print("  ✓ Migration complete: watchlist_id is now VARCHAR(36)")
            return True
        elif current_type and ('character varying' in current_type.lower() or current_type == 'varchar'):
            print(f"  ✓ watchlist_id already VARCHAR(36), skipping migration")
            return False
        else:
            print(f"  ? Unknown type: {current_type}, skipping migration")
            return False


def unwrap_result(obj):
    """Unwrap SQLAlchemy Row object if needed."""
    if not obj:
        return obj
    
    # If it has no close_price/ticker attribute but is indexable, try getting first item
    # checking for _mapping is a good way to identify SQLAlchemy Rows
    if hasattr(obj, "_mapping") and hasattr(obj, "__getitem__"):
        try:
            return obj[0]
        except (IndexError, TypeError):
            return obj
    return obj


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
        
        # Debug type of first item if exists
        if stocks_without_price:
            print(f"Debug: Type of first item: {type(stocks_without_price[0])}")
            print(f"Debug: First item repr: {stocks_without_price[0]}")
        
        for stock in stocks_without_price:
            # Unwrap stock object
            stock_obj = unwrap_result(stock)
            
            # Additional check to ensure we have the model instance
            if not hasattr(stock_obj, "ticker"):
                print(f"  ⚠ Skipping item: Cannot access 'ticker' on {type(stock_obj)}")
                continue
                
            ticker = stock_obj.ticker.upper()
            date_added = stock_obj.date_added.date() if hasattr(stock_obj.date_added, 'date') else stock_obj.date_added
            
            # Try to get closing price on the date added
            price_statement = select(StockPrice).where(
                StockPrice.ticker == ticker,
                StockPrice.price_date == date_added
            )
            price_record = unwrap_result(session.exec(price_statement).first())
            
            if not price_record:
                # Fallback: get the closest price before or on that date
                price_statement = select(StockPrice).where(
                    StockPrice.ticker == ticker,
                    StockPrice.price_date <= date_added
                ).order_by(StockPrice.price_date.desc())
                price_record = unwrap_result(session.exec(price_statement).first())
            
            if not price_record:
                # Last fallback: get the earliest available price
                price_statement = select(StockPrice).where(
                    StockPrice.ticker == ticker
                ).order_by(StockPrice.price_date.asc())
                price_record = unwrap_result(session.exec(price_statement).first())
            
            if price_record and price_record.close_price:
                # Update the entry_price
                # Need to refetch stock in current session to update
                db_stock = session.get(WatchListStock, (stock_obj.watchlist_id, stock_obj.ticker))
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


def run_fix_watchlist_uuid_type_migration():
    """Run watchlist UUID to VARCHAR migration if not already done."""
    if FIX_WATCHLIST_UUID_TYPE_FLAG.exists():
        print("✓ Watchlist UUID type migration already completed, skipping...")
        return

    print("=" * 60)
    print("Running watchlist UUID to VARCHAR migration...")
    print("=" * 60)

    try:
        migrated = migrate_watchlist_uuid_to_varchar()

        if migrated:
            # Mark as completed
            FIX_WATCHLIST_UUID_TYPE_FLAG.touch()
            print("✓ Watchlist UUID type migration completed and marked as done")
    except Exception as e:
        print(f"⚠ Watchlist UUID type migration failed: {e}")
        import traceback
        traceback.print_exc()
        raise


def run_seed_llm_models():
    """Seed LLM models if not already done."""
    if SEED_LLM_MODELS_FLAG.exists():
        print("✓ LLM models seed already completed, skipping...")
        return

    print("=" * 60)
    print("Seeding LLM models...")
    print("=" * 60)

    try:
        from app.services.llm_model_service import seed_default_models
        seed_default_models()

        SEED_LLM_MODELS_FLAG.touch()
        print("✓ LLM models seed completed and marked as done")
    except Exception as e:
        print(f"⚠ LLM models seed failed: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Run all deployment migrations."""
    print("=" * 60)
    print("RAILWAY DEPLOYMENT SCRIPT")
    print("=" * 60)

    # 0. Run watchlist UUID type migration (must be before create_db_and_tables)
    print("\n0. Checking watchlist schema compatibility...")
    run_fix_watchlist_uuid_type_migration()

    # 1. Run database migrations
    print("\n1. Running database migrations...")
    create_db_and_tables()
    print("✓ Database migrations complete")

    # 2. Run one-time backfill
    print("\n2. Checking one-time migrations...")
    run_backfill_entry_prices_task()

    # 3. Cleanup invalid tickers
    print("\n3. Checking invalid tickers cleanup...")
    run_cleanup_invalid_tickers()

    # 4. Seed LLM models
    print("\n4. Checking LLM models seed...")
    run_seed_llm_models()

    print("\n" + "=" * 60)
    print("DEPLOYMENT COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
