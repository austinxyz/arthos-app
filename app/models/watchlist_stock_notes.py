"""WatchlistStockNote model for storing notes on stocks within watchlists."""
from sqlmodel import SQLModel, Field
from sqlalchemy import Column, String, ForeignKey
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
    # Use sa_column for explicit ON DELETE CASCADE
    watchlist_id: str = Field(
        sa_column=Column(
            String,
            ForeignKey("watchlist.watchlist_id", ondelete="CASCADE"),
            primary_key=True
        ),
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
