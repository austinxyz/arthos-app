"""Risk Reversal Watchlist models."""
from sqlmodel import SQLModel, Field, Relationship, VARCHAR
from datetime import datetime, date
from uuid import UUID, uuid4
from typing import Optional, List, TYPE_CHECKING
from decimal import Decimal
from pydantic import field_validator

if TYPE_CHECKING:
    from app.models.account import Account


def generate_uuid_str() -> str:
    """Generate a UUID as a string."""
    return str(uuid4())


class RRWatchlist(SQLModel, table=True):
    """Risk Reversal Watchlist model."""
    __tablename__ = "rr_watchlist"

    # Store UUID as string for SQLite compatibility
    id: str = Field(
        default_factory=generate_uuid_str,
        primary_key=True,
        sa_type=VARCHAR(36),
        description="Unique identifier for the RR watchlist entry"
    )
    ticker: str = Field(
        max_length=10,
        description="Stock ticker symbol"
    )
    call_strike: Decimal = Field(
        description="Call strike price"
    )
    call_quantity: int = Field(
        default=1,
        description="Number of call contracts"
    )
    put_strike: Decimal = Field(
        description="Put strike price"
    )
    put_quantity: int = Field(
        default=1,
        description="Number of put contracts"
    )
    stock_price: Decimal = Field(
        description="Stock price when the RR was saved"
    )
    date_added: datetime = Field(
        default_factory=datetime.now,
        description="When the entry was created"
    )
    entry_price: Decimal = Field(
        description="Net cost when this record was created"
    )
    call_option_quote: Decimal = Field(
        description="Call option quote (avg of bid/ask) when saved"
    )
    put_option_quote: Decimal = Field(
        description="Put option quote (avg of bid/ask) when saved"
    )
    expiration: date = Field(
        description="Options expiration date"
    )
    ratio: str = Field(
        max_length=10,
        default="1:1",
        description="Ratio of puts to calls (e.g., '1:1', '1:2', 'Collar')"
    )
    expired_yn: str = Field(
        max_length=1,
        default="N",
        description="Whether the options have expired (Y/N)"
    )
    
    # Collar-specific fields (optional - only used when ratio='Collar')
    short_call_strike: Optional[Decimal] = Field(
        default=None,
        description="Short call strike price for Collar strategy"
    )
    short_call_quantity: Optional[int] = Field(
        default=None,
        description="Number of short call contracts for Collar strategy"
    )
    short_call_option_quote: Optional[Decimal] = Field(
        default=None,
        description="Short call option quote (avg of bid/ask) when saved"
    )
    collar_type: Optional[str] = Field(
        default=None,
        max_length=10,
        description="Collar sub-type (e.g., '1:1', '1:2')"
    )
    
    # Relationships
    history: List["RRHistory"] = Relationship(back_populates="rr_entry", cascade_delete=True)
    # Foreign Key to Account - stored as VARCHAR(36) for SQLite compatibility
    account_id: Optional[str] = Field(default=None, foreign_key="account.id", index=True, sa_type=VARCHAR(36))
    account: Optional["Account"] = Relationship(back_populates="rr_watchlists")

    @field_validator('id', 'account_id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        """Convert UUID to string if needed."""
        if isinstance(v, UUID):
            return str(v)
        return v


class RRHistory(SQLModel, table=True):
    """Risk Reversal History model."""
    __tablename__ = "rr_history"

    # Store UUID as string for SQLite compatibility
    id: str = Field(
        default_factory=generate_uuid_str,
        primary_key=True,
        sa_type=VARCHAR(36),
        description="Unique identifier for the history entry"
    )
    rr_uuid: str = Field(
        foreign_key="rr_watchlist.id",
        sa_type=VARCHAR(36),
        description="Foreign key to rr_watchlist"
    )
    ticker: str = Field(
        max_length=10,
        description="Stock ticker symbol"
    )
    history_date: date = Field(
        description="Date for which the data represents"
    )
    curr_value: Decimal = Field(
        description="Current value based on current option quote prices"
    )
    call_price: Decimal = Field(
        description="Call option price used in net cost calculation"
    )
    put_price: Decimal = Field(
        description="Put option price used in net cost calculation"
    )
    short_call_price: Optional[Decimal] = Field(
        default=None,
        description="Short call option price for Collar strategy"
    )

    # Relationship to watchlist entry
    rr_entry: Optional[RRWatchlist] = Relationship(back_populates="history")

    @field_validator('id', 'rr_uuid', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        """Convert UUID to string if needed."""
        if isinstance(v, UUID):
            return str(v)
        return v
