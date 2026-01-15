"""Database configuration using SQLModel."""
import os
from sqlmodel import SQLModel, create_engine, Session, text
from app.models.watchlist import WatchList, WatchListStock  # Import to register with metadata
from app.models.stock_price import StockPrice, StockAttributes  # Import to register with metadata
from app.models.scheduler_log import SchedulerLog  # Import to register with metadata
from app.models.rr_watchlist import RRWatchlist, RRHistory  # Import to register with metadata
from app.models.rr_history_log import RRHistoryLog  # Import to register with metadata

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
    # Add call_price and put_price columns to rr_history if they don't exist
    _migrate_rr_history_price_columns()
    # Rename net_cost to curr_value in rr_history if needed
    _migrate_rr_history_rename_net_cost()
    # Add Collar columns to rr_watchlist and rr_history if they don't exist
    _migrate_rr_watchlist_collar_columns()
    _migrate_rr_history_collar_columns()
    # Create indexes on stock_price and stock_attributes for faster queries
    _create_stock_price_index()
    _create_stock_attributes_index()


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

