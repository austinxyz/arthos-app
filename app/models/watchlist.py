"""WatchList models."""
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional, List


class WatchList(SQLModel, table=True):
    """WatchList model."""
    __tablename__ = "watchlist"
    
    watchlist_id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        description="Unique watchlist identifier"
    )
    watchlist_name: str = Field(
        max_length=128,
        description="WatchList name (alphanumeric and spaces only)"
    )
    date_added: datetime = Field(
        default_factory=datetime.now,
        description="When the watchlist was created"
    )
    date_modified: datetime = Field(
        default_factory=datetime.now,
        description="When the watchlist was last updated"
    )
    description: Optional[str] = Field(
        default=None,
        max_length=265,
        description="Optional brief description of the watchlist (max 265 characters)"
    )
    
    # Relationship to watchlist stocks
    stocks: List["WatchListStock"] = Relationship(back_populates="watchlist", cascade_delete=True)


class WatchListStock(SQLModel, table=True):
    """WatchList stock model."""
    __tablename__ = "watchlist_stocks"
    
    watchlist_id: UUID = Field(
        foreign_key="watchlist.watchlist_id",
        primary_key=True,
        description="Foreign key to watchlist"
    )
    ticker: str = Field(
        max_length=10,
        primary_key=True,
        description="Stock ticker symbol"
    )
    date_added: datetime = Field(
        default_factory=datetime.now,
        description="When the stock was added to the watchlist"
    )
    
    # Relationship to watchlist
    watchlist: Optional[WatchList] = Relationship(back_populates="stocks")

