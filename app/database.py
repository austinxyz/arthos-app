"""Database configuration using SQLModel."""
from sqlmodel import SQLModel, create_engine, Session, text
from app.models.stock_cache import StockCache  # Import to register with metadata
from app.models.watchlist import WatchList, WatchListStock  # Import to register with metadata

# Database URL - using SQLite for now, can be easily swapped for Postgres later
DATABASE_URL = "sqlite:///arthos.db"

# Create engine - separated for easy swapping to Postgres
engine = create_engine(DATABASE_URL, echo=True)


def create_db_and_tables():
    """Create database tables."""
    SQLModel.metadata.create_all(engine)
    # Add cache_version column if it doesn't exist (migration for existing databases)
    _migrate_cache_version_column()


def _migrate_cache_version_column():
    """Add cache_version column to stockcache table if it doesn't exist."""
    try:
        with Session(engine) as session:
            # Check if cache_version column exists
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
    except Exception as e:
        # If migration fails, log but don't crash
        print(f"Warning: Could not migrate cache_version column: {e}")


def get_session():
    """Get database session."""
    with Session(engine) as session:
        yield session

