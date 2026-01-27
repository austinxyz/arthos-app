"""WatchList models."""
from sqlmodel import SQLModel, Field, Relationship, VARCHAR
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional, List, TYPE_CHECKING
from decimal import Decimal

if TYPE_CHECKING:
    from app.models.account import Account


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
    is_public: bool = Field(
        default=False,
        description="Whether this watchlist is publicly visible to all users"
    )
    
    
    # Relationships
    stocks: List["WatchListStock"] = Relationship(back_populates="watchlist", cascade_delete=True)
    # Foreign Key to Account
    # Must match Account.id type (VARCHAR(36)) for Postgres compatibility
    account_id: Optional[UUID] = Field(default=None, foreign_key="account.id", index=True, sa_type=VARCHAR(36))
    account: Optional["Account"] = Relationship(back_populates="watchlists")


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
    entry_price: Optional[Decimal] = Field(
        default=None,
        max_digits=12,
        decimal_places=4,
        description="Price when the stock was added to the watchlist"
    )
    
    # Relationship to watchlist
    watchlist: Optional[WatchList] = Relationship(back_populates="stocks")

