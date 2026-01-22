"""Database configuration using SQLModel."""
import os
from sqlmodel import SQLModel, create_engine, Session, text, select
from app.models.watchlist import WatchList, WatchListStock  # Import to register with metadata
from app.models.stock_price import StockPrice, StockAttributes  # Import to register with metadata
from app.models.scheduler_log import SchedulerLog  # Import to register with metadata
from app.models.rr_watchlist import RRWatchlist, RRHistory
from app.models.rr_history_log import RRHistoryLog  # Import to register with metadata
from app.models.account import Account # New import, fixed typo

# Database URL - supports both SQLite (local dev) and PostgreSQL (production)
# Railway provides DATABASE_URL environment variable automatically
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///arthos.db")

# Convert Railway's postgres:// URL to postgresql:// if needed (SQLAlchemy requirement)
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Create engine - separated for easy swapping to Postgres
# Disable echo in production for better performance
echo_sql = os.getenv("ECHO_SQL", "false").lower() == "true"
engine = create_engine(DATABASE_URL, echo=echo_sql)


def create_db_and_tables():
    """Create database tables."""
    SQLModel.metadata.create_all(engine)
    # Add dma_50 and dma_200 columns if they don't exist (migration for existing databases)
    _migrate_stock_price_dma_columns()
    # Migrate stock_price_wtrmrk to stock_attributes (rename table and add new columns)
    _migrate_stock_attributes_table()
    # Add earnings date columns to stock_attributes if they don't exist
    _migrate_stock_attributes_earnings_columns()
    # Add next_dividend_date column to stock_attributes if it doesn't exist
    _migrate_stock_attributes_dividend_date_column()
    # Fix dividend yield values that were incorrectly multiplied by 100
    _fix_dividend_yield_values()
    # Add call_price and put_price columns to rr_history if they don't exist
    _migrate_rr_history_price_columns()
    # Rename net_cost to curr_value in rr_history if needed
    _migrate_rr_history_rename_net_cost()
    # Add Collar columns to rr_watchlist and rr_history if they don't exist
    _migrate_rr_watchlist_collar_columns()
    _migrate_rr_history_collar_columns()
    # Add IV columns to stock_attributes if they don't exist
    _migrate_stock_attributes_iv_columns()
    # Add IV column to stock_price if it doesn't exist
    _migrate_stock_price_iv_column()
    # Add description column to watchlist if it doesn't exist
    _migrate_watchlist_description_column()
    # Create indexes on stock_price and stock_attributes for faster queries
    _create_stock_price_index()
    _create_stock_attributes_index()
    
    # Account Feature Migrations
    _create_account_table()
    _migrate_watchlist_account_column()
    _migrate_rr_watchlist_account_column()
    _migrate_data_ownership_to_default_account()
    
    # Public Watchlist Feature Migrations
    _migrate_watchlist_is_public_column()
    _migrate_watchlist_stocks_entry_price_column()
    


def _migrate_stock_price_dma_columns():
    """Add dma_50 and dma_200 columns to stock_price table if they don't exist."""
    try:
        with Session(engine) as session:
            # Check database type
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            if is_sqlite:
                # SQLite-specific migration
                result = session.exec(text(
                    "PRAGMA table_info(stock_price)"
                )).all()
                
                # Check which columns exist
                columns = {row[1] for row in result}
                
                if 'dma_50' not in columns:
                    # Add the dma_50 column
                    session.exec(text(
                        "ALTER TABLE stock_price ADD COLUMN dma_50 NUMERIC(12, 4)"
                    ))
                    session.commit()
                    print("Added dma_50 column to stock_price table")
                
                if 'dma_200' not in columns:
                    # Add the dma_200 column
                    session.exec(text(
                        "ALTER TABLE stock_price ADD COLUMN dma_200 NUMERIC(12, 4)"
                    ))
                    session.commit()
                    print("Added dma_200 column to stock_price table")
            else:
                # PostgreSQL-specific migration
                result = session.exec(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'stock_price' AND column_name IN ('dma_50', 'dma_200')"
                )).all()
                
                existing_columns = {row[0] for row in result}
                
                if 'dma_50' not in existing_columns:
                    # Add the dma_50 column
                    session.exec(text(
                        "ALTER TABLE stock_price ADD COLUMN dma_50 NUMERIC(12, 4)"
                    ))
                    session.commit()
                    print("Added dma_50 column to stock_price table")
                
                if 'dma_200' not in existing_columns:
                    # Add the dma_200 column
                    session.exec(text(
                        "ALTER TABLE stock_price ADD COLUMN dma_200 NUMERIC(12, 4)"
                    ))
                    session.commit()
                    print("Added dma_200 column to stock_price table")
    except Exception as e:
        # If migration fails, log but don't crash
        print(f"Warning: Could not migrate stock_price DMA columns: {e}")


def _migrate_stock_attributes_table():
    """Migrate stock_price_wtrmrk table to stock_attributes (rename and add new columns)."""
    try:
        with Session(engine) as session:
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            if is_sqlite:
                # SQLite - check if old table exists
                result = session.exec(text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='stock_price_wtrmrk'"
                )).all()
                
                if len(result) > 0:
                    # Check if new table exists
                    result_new = session.exec(text(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='stock_attributes'"
                    )).all()
                    
                    if len(result_new) == 0:
                        # Rename table and add new columns
                        session.exec(text(
                            "ALTER TABLE stock_price_wtrmrk RENAME TO stock_attributes"
                        ))
                        session.commit()
                        print("Renamed stock_price_wtrmrk to stock_attributes")
                    
                    # Add new columns if they don't exist
                    result = session.exec(text(
                        "PRAGMA table_info(stock_attributes)"
                    )).all()
                    columns = {row[1] for row in result}
                    
                    if 'dividend_amt' not in columns:
                        session.exec(text(
                            "ALTER TABLE stock_attributes ADD COLUMN dividend_amt NUMERIC(12, 4)"
                        ))
                        session.commit()
                        print("Added dividend_amt column to stock_attributes table")
                    
                    if 'dividend_yield' not in columns:
                        session.exec(text(
                            "ALTER TABLE stock_attributes ADD COLUMN dividend_yield NUMERIC(12, 4)"
                        ))
                        session.commit()
                        print("Added dividend_yield column to stock_attributes table")
            else:
                # PostgreSQL - check if old table exists
                result = session.exec(text(
                    "SELECT tablename FROM pg_tables WHERE tablename = 'stock_price_wtrmrk'"
                )).all()
                
                if len(result) > 0:
                    # Check if new table exists
                    result_new = session.exec(text(
                        "SELECT tablename FROM pg_tables WHERE tablename = 'stock_attributes'"
                    )).all()
                    
                    if len(result_new) == 0:
                        # Rename table
                        session.exec(text(
                            "ALTER TABLE stock_price_wtrmrk RENAME TO stock_attributes"
                        ))
                        session.commit()
                        print("Renamed stock_price_wtrmrk to stock_attributes")
                    
                    # Add new columns if they don't exist
                    result = session.exec(text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'stock_attributes' AND column_name IN ('dividend_amt', 'dividend_yield')"
                    )).all()
                    existing_columns = {row[0] for row in result}
                    
                    if 'dividend_amt' not in existing_columns:
                        session.exec(text(
                            "ALTER TABLE stock_attributes ADD COLUMN dividend_amt NUMERIC(12, 4)"
                        ))
                        session.commit()
                        print("Added dividend_amt column to stock_attributes table")
                    
                    if 'dividend_yield' not in existing_columns:
                        session.exec(text(
                            "ALTER TABLE stock_attributes ADD COLUMN dividend_yield NUMERIC(12, 4)"
                        ))
                        session.commit()
                        print("Added dividend_yield column to stock_attributes table")
    except Exception as e:
        # If migration fails, log but don't crash
        print(f"Warning: Could not migrate stock_attributes table: {e}")


def _migrate_stock_attributes_earnings_columns():
    """Add next_earnings_date and is_earnings_date_estimate columns to stock_attributes table if they don't exist."""
    try:
        with Session(engine) as session:
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            if is_sqlite:
                # SQLite - check if columns exist
                result = session.exec(text(
                    "PRAGMA table_info(stock_attributes)"
                )).all()
                columns = {row[1] for row in result}
                
                if 'next_earnings_date' not in columns:
                    session.exec(text(
                        "ALTER TABLE stock_attributes ADD COLUMN next_earnings_date DATE"
                    ))
                    session.commit()
                    print("Added next_earnings_date column to stock_attributes table")
                
                if 'is_earnings_date_estimate' not in columns:
                    session.exec(text(
                        "ALTER TABLE stock_attributes ADD COLUMN is_earnings_date_estimate BOOLEAN"
                    ))
                    session.commit()
                    print("Added is_earnings_date_estimate column to stock_attributes table")
            else:
                # PostgreSQL - check if columns exist
                result = session.exec(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'stock_attributes' AND column_name IN ('next_earnings_date', 'is_earnings_date_estimate')"
                )).all()
                existing_columns = {row[0] for row in result}
                
                if 'next_earnings_date' not in existing_columns:
                    session.exec(text(
                        "ALTER TABLE stock_attributes ADD COLUMN next_earnings_date DATE"
                    ))
                    session.commit()
                    print("Added next_earnings_date column to stock_attributes table")
                
                if 'is_earnings_date_estimate' not in existing_columns:
                    session.exec(text(
                        "ALTER TABLE stock_attributes ADD COLUMN is_earnings_date_estimate BOOLEAN"
                    ))
                    session.commit()
                    print("Added is_earnings_date_estimate column to stock_attributes table")
    except Exception as e:
        # If migration fails, log but don't crash
        print(f"Warning: Could not migrate stock_attributes earnings columns: {e}")


def _migrate_stock_attributes_dividend_date_column():
    """Add next_dividend_date column to stock_attributes table if it doesn't exist."""
    try:
        with Session(engine) as session:
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            if is_sqlite:
                # SQLite - check if column exists
                result = session.exec(text(
                    "PRAGMA table_info(stock_attributes)"
                )).all()
                columns = {row[1] for row in result}
                
                if 'next_dividend_date' not in columns:
                    session.exec(text(
                        "ALTER TABLE stock_attributes ADD COLUMN next_dividend_date DATE"
                    ))
                    session.commit()
                    print("Added next_dividend_date column to stock_attributes table")
            else:
                # PostgreSQL - check if column exists
                result = session.exec(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'stock_attributes' AND column_name = 'next_dividend_date'"
                )).all()
                
                if not result:
                    session.exec(text(
                        "ALTER TABLE stock_attributes ADD COLUMN next_dividend_date DATE"
                    ))
                    session.commit()
                    print("Added next_dividend_date column to stock_attributes table")
    except Exception as e:
        # If migration fails, log but don't crash
        print(f"Warning: Could not migrate stock_attributes dividend date column: {e}")


def _fix_dividend_yield_values():
    """
    One-time fix for dividend yield values that were incorrectly multiplied by 100.
    yfinance returns dividendYield as a percentage (e.g., 2.43 means 2.43%),
    but old code incorrectly multiplied by 100 again, resulting in 243% instead of 2.43%.
    
    This migration divides all dividend yields > 20 by 100 to correct them.
    """
    try:
        with Session(engine) as session:
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            # Update dividend yields that are > 20 (clearly wrong - no stock has 20%+ yield)
            # These values were incorrectly multiplied by 100
            if is_sqlite:
                result = session.exec(text(
                    "UPDATE stock_attributes SET dividend_yield = dividend_yield / 100 "
                    "WHERE dividend_yield > 20"
                ))
            else:
                result = session.exec(text(
                    "UPDATE stock_attributes SET dividend_yield = dividend_yield / 100 "
                    "WHERE dividend_yield > 20"
                ))
            
            session.commit()
            
            # Check how many were updated
            affected = result.rowcount if hasattr(result, 'rowcount') else 0
            if affected > 0:
                print(f"Fixed {affected} incorrect dividend yield values (divided by 100)")
    except Exception as e:
        # If migration fails, log but don't crash
        print(f"Warning: Could not fix dividend yield values: {e}")


def _migrate_rr_history_price_columns():
    """Add call_price and put_price columns to rr_history table if they don't exist."""
    try:
        with Session(engine) as session:
            # Check database type
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            if is_sqlite:
                # SQLite-specific migration
                result = session.exec(text(
                    "PRAGMA table_info(rr_history)"
                )).all()
                
                column_names = [row[1] for row in result]
                
                # Add call_price column if it doesn't exist
                if 'call_price' not in column_names:
                    session.exec(text(
                        "ALTER TABLE rr_history ADD COLUMN call_price DECIMAL"
                    ))
                    session.commit()
                    print("Added call_price column to rr_history table")
                
                # Add put_price column if it doesn't exist
                if 'put_price' not in column_names:
                    session.exec(text(
                        "ALTER TABLE rr_history ADD COLUMN put_price DECIMAL"
                    ))
                    session.commit()
                    print("Added put_price column to rr_history table")
            else:
                # PostgreSQL-specific migration
                # Check if call_price column exists
                result = session.exec(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'rr_history' AND column_name = 'call_price'"
                )).first()
                
                if not result:
                    session.exec(text(
                        "ALTER TABLE rr_history ADD COLUMN call_price DECIMAL"
                    ))
                    session.commit()
                    print("Added call_price column to rr_history table")
                
                # Check if put_price column exists
                result = session.exec(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'rr_history' AND column_name = 'put_price'"
                )).first()
                
                if not result:
                    session.exec(text(
                        "ALTER TABLE rr_history ADD COLUMN put_price DECIMAL"
                    ))
                    session.commit()
                    print("Added put_price column to rr_history table")
    except Exception as e:
        print(f"Warning: Could not migrate rr_history price columns: {e}")


def _migrate_rr_history_rename_net_cost():
    """Rename net_cost column to curr_value in rr_history table if it exists."""
    try:
        with Session(engine) as session:
            # Check database type
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            if is_sqlite:
                # SQLite-specific migration
                result = session.exec(text(
                    "PRAGMA table_info(rr_history)"
                )).all()
                
                column_names = [row[1] for row in result]
                
                # Rename net_cost to curr_value if net_cost exists and curr_value doesn't
                if 'net_cost' in column_names and 'curr_value' not in column_names:
                    # SQLite doesn't support ALTER TABLE RENAME COLUMN directly in older versions
                    # We'll use a workaround: create new table, copy data, drop old, rename new
                    session.exec(text(
                        "CREATE TABLE rr_history_new AS "
                        "SELECT id, rr_uuid, ticker, history_date, "
                        "net_cost AS curr_value, call_price, put_price "
                        "FROM rr_history"
                    ))
                    session.exec(text("DROP TABLE rr_history"))
                    session.exec(text("ALTER TABLE rr_history_new RENAME TO rr_history"))
                    session.commit()
                    print("Renamed net_cost column to curr_value in rr_history table")
            else:
                # PostgreSQL-specific migration
                # Check if net_cost column exists and curr_value doesn't
                result = session.exec(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'rr_history' AND column_name IN ('net_cost', 'curr_value')"
                )).all()
                existing_columns = {row[0] for row in result}
                
                if 'net_cost' in existing_columns and 'curr_value' not in existing_columns:
                    session.exec(text(
                        "ALTER TABLE rr_history RENAME COLUMN net_cost TO curr_value"
                    ))
                    session.commit()
                    print("Renamed net_cost column to curr_value in rr_history table")
    except Exception as e:
        print(f"Warning: Could not migrate rr_history net_cost column: {e}")


def _migrate_rr_watchlist_collar_columns():
    """Add Collar-specific columns to rr_watchlist table if they don't exist."""
    try:
        with Session(engine) as session:
            # Check database type
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            collar_columns = [
                ('short_call_strike', 'DECIMAL'),
                ('short_call_quantity', 'INTEGER'),
                ('short_call_option_quote', 'DECIMAL'),
                ('collar_type', 'VARCHAR(10)')
            ]
            
            if is_sqlite:
                # SQLite-specific migration
                result = session.exec(text(
                    "PRAGMA table_info(rr_watchlist)"
                )).all()
                
                existing_columns = {row[1] for row in result}
                
                for col_name, col_type in collar_columns:
                    if col_name not in existing_columns:
                        session.exec(text(
                            f"ALTER TABLE rr_watchlist ADD COLUMN {col_name} {col_type}"
                        ))
                        session.commit()
                        print(f"Added {col_name} column to rr_watchlist table")
            else:
                # PostgreSQL-specific migration
                result = session.exec(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'rr_watchlist'"
                )).all()
                
                existing_columns = {row[0] for row in result}
                
                for col_name, col_type in collar_columns:
                    if col_name not in existing_columns:
                        session.exec(text(
                            f"ALTER TABLE rr_watchlist ADD COLUMN {col_name} {col_type}"
                        ))
                        session.commit()
                        print(f"Added {col_name} column to rr_watchlist table")
    except Exception as e:
        print(f"Warning: Could not migrate rr_watchlist Collar columns: {e}")


def _migrate_rr_history_collar_columns():
    """Add short_call_price column to rr_history table if it doesn't exist."""
    try:
        with Session(engine) as session:
            # Check database type
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            if is_sqlite:
                # SQLite-specific migration
                result = session.exec(text(
                    "PRAGMA table_info(rr_history)"
                )).all()
                
                existing_columns = {row[1] for row in result}
                
                if 'short_call_price' not in existing_columns:
                    session.exec(text(
                        "ALTER TABLE rr_history ADD COLUMN short_call_price DECIMAL"
                    ))
                    session.commit()
                    print("Added short_call_price column to rr_history table")
            else:
                # PostgreSQL-specific migration
                result = session.exec(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'rr_history' AND column_name = 'short_call_price'"
                )).first()
                
                if not result:
                    session.exec(text(
                        "ALTER TABLE rr_history ADD COLUMN short_call_price DECIMAL"
                    ))
                    session.commit()
                    print("Added short_call_price column to rr_history table")
    except Exception as e:
        print(f"Warning: Could not migrate rr_history Collar columns: {e}")


def _migrate_stock_attributes_iv_columns():
    """Add IV-related columns to stock_attributes table if they don't exist."""
    try:
        with Session(engine) as session:
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            # Columns to add: current_iv, iv_rank, iv_percentile, iv_high_52w, iv_low_52w
            iv_columns = [
                ('current_iv', 'DECIMAL(12, 4)'),
                ('iv_rank', 'DECIMAL(12, 4)'),
                ('iv_percentile', 'DECIMAL(12, 4)'),
                ('iv_high_52w', 'DECIMAL(12, 4)'),
                ('iv_low_52w', 'DECIMAL(12, 4)')
            ]
            
            if is_sqlite:
                # SQLite-specific migration
                for col_name, col_type in iv_columns:
                    result = session.exec(text(
                        f"PRAGMA table_info(stock_attributes)"
                    )).all()
                    
                    column_exists = any(row[1] == col_name for row in result)
                    
                    if not column_exists:
                        session.exec(text(
                            f"ALTER TABLE stock_attributes ADD COLUMN {col_name} {col_type}"
                        ))
                        session.commit()
                        print(f"Added {col_name} column to stock_attributes table")
            else:
                # PostgreSQL-specific migration
                for col_name, col_type in iv_columns:
                    result = session.exec(text(
                        "SELECT column_name FROM information_schema.columns "
                        f"WHERE table_name = 'stock_attributes' AND column_name = '{col_name}'"
                    )).first()
                    
                    if not result:
                        # Use DECIMAL for PostgreSQL
                        pg_type = 'DECIMAL' if 'DECIMAL' in col_type else col_type
                        session.exec(text(
                            f"ALTER TABLE stock_attributes ADD COLUMN {col_name} {pg_type}"
                        ))
                        session.commit()
                        print(f"Added {col_name} column to stock_attributes table")
    except Exception as e:
        print(f"Warning: Could not migrate stock_attributes IV columns: {e}")


def _migrate_stock_price_iv_column():
    """Add iv column to stock_price table if it doesn't exist."""
    try:
        with Session(engine) as session:
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            if is_sqlite:
                # SQLite-specific migration
                result = session.exec(text(
                    "PRAGMA table_info(stock_price)"
                )).all()
                
                column_exists = any(row[1] == 'iv' for row in result)
                
                if not column_exists:
                    session.exec(text(
                        "ALTER TABLE stock_price ADD COLUMN iv DECIMAL(12, 4)"
                    ))
                    session.commit()
                    print("Added iv column to stock_price table")
            else:
                # PostgreSQL-specific migration
                result = session.exec(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'stock_price' AND column_name = 'iv'"
                )).first()
                
                if not result:
                    session.exec(text(
                        "ALTER TABLE stock_price ADD COLUMN iv DECIMAL(12, 4)"
                    ))
                    session.commit()
                    print("Added iv column to stock_price table")
    except Exception as e:
        print(f"Warning: Could not migrate stock_price IV column: {e}")


def _migrate_watchlist_description_column():
    """Add description column to watchlist table if it doesn't exist."""
    try:
        with Session(engine) as session:
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            if is_sqlite:
                # SQLite-specific migration
                result = session.exec(text(
                    "PRAGMA table_info(watchlist)"
                )).all()
                
                column_exists = any(row[1] == 'description' for row in result)
                
                if not column_exists:
                    session.exec(text(
                        "ALTER TABLE watchlist ADD COLUMN description VARCHAR(265)"
                    ))
                    session.commit()
                    print("Added description column to watchlist table")
            else:
                # PostgreSQL-specific migration
                result = session.exec(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'watchlist' AND column_name = 'description'"
                )).first()
                
                if not result:
                    session.exec(text(
                        "ALTER TABLE watchlist ADD COLUMN description VARCHAR(265)"
                    ))
                    session.commit()
                    print("Added description column to watchlist table")
    except Exception as e:
        print(f"Warning: Could not migrate watchlist description column: {e}")


def _create_stock_price_index():
    """Create index on stock_price(ticker, price_date) for faster queries."""
    try:
        with Session(engine) as session:
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            if is_sqlite:
                # SQLite - check if index exists
                result = session.exec(text(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_stock_price_ticker_date'"
                )).all()
                
                if len(result) == 0:
                    # Create index
                    session.exec(text(
                        "CREATE INDEX idx_stock_price_ticker_date ON stock_price(ticker, price_date)"
                    ))
                    session.commit()
                    print("Created index idx_stock_price_ticker_date on stock_price table")
            else:
                # PostgreSQL - check if index exists
                result = session.exec(text(
                    "SELECT indexname FROM pg_indexes WHERE tablename = 'stock_price' AND indexname = 'idx_stock_price_ticker_date'"
                )).all()
                
                if len(result) == 0:
                    # Create index
                    session.exec(text(
                        "CREATE INDEX idx_stock_price_ticker_date ON stock_price(ticker, price_date)"
                    ))
                    session.commit()
                    print("Created index idx_stock_price_ticker_date on stock_price table")
    except Exception as e:
        # If index creation fails, log but don't crash
        print(f"Warning: Could not create stock_price index: {e}")


def _create_stock_attributes_index():
    """Create index on stock_attributes(latest_date) for faster queries when checking for updates."""
    try:
        with Session(engine) as session:
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            if is_sqlite:
                # SQLite - check if index exists
                result = session.exec(text(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_stock_attributes_latest_date'"
                )).all()
                
                if len(result) == 0:
                    # Create index
                    session.exec(text(
                        "CREATE INDEX idx_stock_attributes_latest_date ON stock_attributes(latest_date)"
                    ))
                    session.commit()
                    print("Created index idx_stock_attributes_latest_date on stock_attributes table")
            else:
                # PostgreSQL - check if index exists
                result = session.exec(text(
                    "SELECT indexname FROM pg_indexes WHERE tablename = 'stock_attributes' AND indexname = 'idx_stock_attributes_latest_date'"
                )).all()
                
                if len(result) == 0:
                    # Create index
                    session.exec(text(
                        "CREATE INDEX idx_stock_attributes_latest_date ON stock_attributes(latest_date)"
                    ))
                    session.commit()
                    print("Created index idx_stock_attributes_latest_date on stock_attributes table")
    except Exception as e:
        # If index creation fails, log but don't crash
        print(f"Warning: Could not create stock_attributes index: {e}")


def get_session():
    """Get database session."""
    with Session(engine) as session:
        yield session


def _create_account_table():
    """Create account table if it doesn't exist."""
    try:
        with Session(engine) as session:
            is_sqlite = DATABASE_URL.startswith("sqlite")

            if is_sqlite:
                result = session.exec(text("SELECT name FROM sqlite_master WHERE type='table' AND name='account'")).all()
                if not result:
                    SQLModel.metadata.create_all(engine)
                    print("Created account table")
            else:
                result = session.exec(text("SELECT tablename FROM pg_tables WHERE tablename = 'account'")).all()
                if not result:
                    SQLModel.metadata.create_all(engine)
                    print("Created account table")
    except Exception as e:
        print(f"Warning: Could not create account table: {e}")


def _migrate_watchlist_account_column():
    """Add account_id column to watchlist table if it doesn't exist."""
    try:
        with Session(engine) as session:
            is_sqlite = DATABASE_URL.startswith("sqlite")

            if is_sqlite:
                result = session.exec(text("PRAGMA table_info(watchlist)")).all()
                if not any(row[1] == 'account_id' for row in result):
                    session.exec(text("ALTER TABLE watchlist ADD COLUMN account_id CHAR(36)"))
                    session.commit()
                    print("Added account_id column to watchlist table")

                # Check if index exists before creating (check both old and new names)
                indexes = session.exec(text(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name IN ('idx_watchlist_account_id', 'idx_watchlist_user_id')"
                )).all()
                if not indexes:
                    session.exec(text("CREATE INDEX idx_watchlist_account_id ON watchlist(account_id)"))
                    session.commit()
                    print("Created index idx_watchlist_account_id")
            else:
                result = session.exec(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'watchlist' AND column_name = 'account_id'")).first()
                if not result:
                    session.exec(text("ALTER TABLE watchlist ADD COLUMN account_id UUID"))
                    session.commit()
                    print("Added account_id column to watchlist table")

                # Check if index exists before creating (PostgreSQL) - check both old and new names
                index_exists = session.exec(text(
                    "SELECT indexname FROM pg_indexes WHERE tablename = 'watchlist' AND indexname IN ('idx_watchlist_account_id', 'idx_watchlist_user_id')"
                )).first()
                if not index_exists:
                    session.exec(text("CREATE INDEX idx_watchlist_account_id ON watchlist(account_id)"))
                    session.commit()
                    print("Created index idx_watchlist_account_id")
    except Exception as e:
        print(f"Warning: Could not migrate watchlist account_id column: {e}")


def _migrate_rr_watchlist_account_column():
    """Add account_id column to rr_watchlist table if it doesn't exist."""
    try:
        with Session(engine) as session:
            is_sqlite = DATABASE_URL.startswith("sqlite")

            if is_sqlite:
                result = session.exec(text("PRAGMA table_info(rr_watchlist)")).all()
                if not any(row[1] == 'account_id' for row in result):
                    session.exec(text("ALTER TABLE rr_watchlist ADD COLUMN account_id CHAR(36)"))
                    session.commit()
                    print("Added account_id column to rr_watchlist table")

                # Check if index exists before creating (check both old and new names)
                indexes = session.exec(text(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name IN ('idx_rr_watchlist_account_id', 'idx_rr_watchlist_user_id')"
                )).all()
                if not indexes:
                    session.exec(text("CREATE INDEX idx_rr_watchlist_account_id ON rr_watchlist(account_id)"))
                    session.commit()
                    print("Created index idx_rr_watchlist_account_id")
            else:
                result = session.exec(text("SELECT column_name FROM information_schema.columns WHERE table_name = 'rr_watchlist' AND column_name = 'account_id'")).first()
                if not result:
                    session.exec(text("ALTER TABLE rr_watchlist ADD COLUMN account_id UUID"))
                    session.commit()
                    print("Added account_id column to rr_watchlist table")

                # Check if index exists before creating (PostgreSQL) - check both old and new names
                index_exists = session.exec(text(
                    "SELECT indexname FROM pg_indexes WHERE tablename = 'rr_watchlist' AND indexname IN ('idx_rr_watchlist_account_id', 'idx_rr_watchlist_user_id')"
                )).first()
                if not index_exists:
                    session.exec(text("CREATE INDEX idx_rr_watchlist_account_id ON rr_watchlist(account_id)"))
                    session.commit()
                    print("Created index idx_rr_watchlist_account_id")
    except Exception as e:
        print(f"Warning: Could not migrate rr_watchlist account_id column: {e}")


def _migrate_data_ownership_to_default_account():
    """Create default account kgajjala@gmail.com and assign all orphaned data to it."""
    try:
        from uuid import uuid4
        from datetime import datetime

        default_email = "kgajjala@gmail.com"
        default_account_id = None

        with Session(engine) as session:
            # Check if default account exists
            try:
                result = session.exec(text(f"SELECT id FROM account WHERE email = '{default_email}'")).first()
                if result:
                    default_account_id = result[0]
                    print(f"Found existing account {default_email} with ID {default_account_id}")
            except Exception as e:
                print(f"Could not query account table: {e}")
                return

            # Create account if it doesn't exist
            if not default_account_id:
                new_id = str(uuid4())
                now_str = datetime.utcnow().isoformat()

                try:
                    session.exec(text(
                        f"INSERT INTO account (id, email, google_sub, full_name, created_at) "
                        f"VALUES ('{new_id}', '{default_email}', 'migration_placeholder', 'Karthik Gajjala', '{now_str}')"
                    ))
                    session.commit()
                    default_account_id = new_id
                    print(f"✅ Created default account {default_email} with ID {new_id}")
                except Exception as e:
                    session.rollback()
                    print(f"ERROR: Could not create default account: {e}")
                    return

            if not default_account_id:
                print("ERROR: Could not find or create default account")
                return

            # Update orphaned watchlists
            try:
                result = session.exec(text(
                    f"UPDATE watchlist SET account_id = '{default_account_id}' WHERE account_id IS NULL"
                ))
                watchlist_updated = result.rowcount if hasattr(result, 'rowcount') else 0
                session.commit()
                print(f"✅ Assigned {watchlist_updated} orphaned watchlists to {default_email}")
            except Exception as e:
                session.rollback()
                print(f"Warning: Could not update watchlist ownership: {e}")

            # Update orphaned rr_watchlist entries
            try:
                result = session.exec(text(
                    f"UPDATE rr_watchlist SET account_id = '{default_account_id}' WHERE account_id IS NULL"
                ))
                rr_updated = result.rowcount if hasattr(result, 'rowcount') else 0
                session.commit()
                print(f"✅ Assigned {rr_updated} orphaned RR entries to {default_email}")
            except Exception as e:
                session.rollback()
                print(f"Warning: Could not update rr_watchlist ownership: {e}")

            print(f"✅ Data ownership migration complete for {default_email}")

    except Exception as e:
        print(f"Warning: Could not migrate data ownership: {e}")


def _migrate_watchlist_is_public_column():
    """Add is_public column to watchlist table if it doesn't exist."""
    try:
        with Session(engine) as session:
            is_sqlite = DATABASE_URL.startswith("sqlite")

            if is_sqlite:
                result = session.exec(text("PRAGMA table_info(watchlist)")).all()
                column_exists = any(row[1] == 'is_public' for row in result)

                if not column_exists:
                    session.exec(text(
                        "ALTER TABLE watchlist ADD COLUMN is_public BOOLEAN DEFAULT 0"
                    ))
                    session.commit()
                    print("Added is_public column to watchlist table")
            else:
                result = session.exec(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'watchlist' AND column_name = 'is_public'"
                )).first()

                if not result:
                    session.exec(text(
                        "ALTER TABLE watchlist ADD COLUMN is_public BOOLEAN DEFAULT FALSE"
                    ))
                    session.commit()
                    print("Added is_public column to watchlist table")
    except Exception as e:
        print(f"Warning: Could not migrate watchlist is_public column: {e}")


def _migrate_watchlist_stocks_entry_price_column():
    """Add entry_price column to watchlist_stocks table if it doesn't exist."""
    try:
        with Session(engine) as session:
            is_sqlite = DATABASE_URL.startswith("sqlite")

            if is_sqlite:
                result = session.exec(text("PRAGMA table_info(watchlist_stocks)")).all()
                column_exists = any(row[1] == 'entry_price' for row in result)

                if not column_exists:
                    session.exec(text(
                        "ALTER TABLE watchlist_stocks ADD COLUMN entry_price NUMERIC(12, 4)"
                    ))
                    session.commit()
                    print("Added entry_price column to watchlist_stocks table")
            else:
                result = session.exec(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'watchlist_stocks' AND column_name = 'entry_price'"
                )).first()

                if not result:
                    session.exec(text(
                        "ALTER TABLE watchlist_stocks ADD COLUMN entry_price NUMERIC(12, 4)"
                    ))
                    session.commit()
                    print("Added entry_price column to watchlist_stocks table")
    except Exception as e:
        print(f"Warning: Could not migrate watchlist_stocks entry_price column: {e}")


