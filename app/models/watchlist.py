"""WatchList models."""
from sqlmodel import SQLModel, Field, Relationship, VARCHAR
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional, List, TYPE_CHECKING
from decimal import Decimal
from pydantic import field_validator

if TYPE_CHECKING:
    from app.models.account import Account


def generate_uuid_str() -> str:
    """Generate a UUID as a string."""
    return str(uuid4())


class WatchList(SQLModel, table=True):
    """WatchList model."""
    __tablename__ = "watchlist"

    # Store UUID as string for SQLite compatibility
    watchlist_id: str = Field(
        default_factory=generate_uuid_str,
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
    # Foreign Key to Account - stored as VARCHAR(36) for SQLite compatibility
    account_id: Optional[str] = Field(default=None, foreign_key="account.id", index=True, sa_type=VARCHAR(36))
    account: Optional["Account"] = Relationship(back_populates="watchlists")

    @field_validator('watchlist_id', 'account_id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        """Convert UUID to string if needed."""
        if isinstance(v, UUID):
            return str(v)
        return v


class WatchListStock(SQLModel, table=True):
    """WatchList stock model."""
    __tablename__ = "watchlist_stocks"

    # Store UUID as string for SQLite compatibility
    watchlist_id: str = Field(
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

    @field_validator('watchlist_id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        """Convert UUID to string if needed."""
        if isinstance(v, UUID):
            return str(v)
        return v

