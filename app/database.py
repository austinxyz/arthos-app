"""Database configuration using SQLModel."""
import os
from sqlmodel import SQLModel, create_engine, Session, text
from app.models.stock_cache import StockCache  # Import to register with metadata
from app.models.watchlist import WatchList, WatchListStock  # Import to register with metadata
from app.models.stock_price import StockPrice, StockPriceWatermark  # Import to register with metadata

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
    # Add cache_version column if it doesn't exist (migration for existing databases)
    _migrate_cache_version_column()
    # Add dma_50 and dma_200 columns if they don't exist (migration for existing databases)
    _migrate_stock_price_dma_columns()


def _migrate_cache_version_column():
    """Add cache_version column to stockcache table if it doesn't exist."""
    try:
        with Session(engine) as session:
            # Check database type
            is_sqlite = DATABASE_URL.startswith("sqlite")
            
            if is_sqlite:
                # SQLite-specific migration
                result = session.exec(text(
                    "PRAGMA table_info(stockcache)"
                )).all()
                
                # Check if cache_version column exists
                column_exists = any(row[1] == 'cache_version' for row in result)
                
                if not column_exists:
                    # Add the cache_version column
                    session.exec(text(
                        "ALTER TABLE stockcache ADD COLUMN cache_version INTEGER"
                    ))
                    session.commit()
                    print("Added cache_version column to stockcache table")
            else:
                # PostgreSQL-specific migration
                result = session.exec(text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'stockcache' AND column_name = 'cache_version'"
                )).all()
                
                if len(result) == 0:
                    # Add the cache_version column
                    session.exec(text(
                        "ALTER TABLE stockcache ADD COLUMN cache_version INTEGER"
                    ))
                    session.commit()
                    print("Added cache_version column to stockcache table")
    except Exception as e:
        # If migration fails, log but don't crash
        print(f"Warning: Could not migrate cache_version column: {e}")


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


def get_session():
    """Get database session."""
    with Session(engine) as session:
        yield session

