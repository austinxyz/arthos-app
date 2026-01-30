"""WatchlistStockNote model for storing notes on stocks within watchlists."""
from sqlmodel import SQLModel, Field, VARCHAR
from datetime import datetime
from typing import Optional


class WatchlistStockNote(SQLModel, table=True):
    """
    Model for storing notes on stocks within watchlists.

    Notes are per-watchlist, meaning the same stock in different watchlists
    can have different notes. This allows users to track different thesis
    or reasons for having the same stock in multiple watchlists.
    """
    __tablename__ = "watchlist_stock_notes"

    # Composite primary key: watchlist_id + ticker
    # Use VARCHAR(36) explicitly for PostgreSQL compatibility (watchlist.watchlist_id is stored as UUID in Postgres)
    watchlist_id: str = Field(
        foreign_key="watchlist.watchlist_id",
        primary_key=True,
        sa_type=VARCHAR(36),
        description="Foreign key to watchlist"
    )
    ticker: str = Field(
        max_length=10,
        primary_key=True,
        description="Stock ticker symbol"
    )
    note_text: str = Field(
        max_length=500,
        description="Note text (max 500 characters)"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the note was created"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the note was last updated"
    )
