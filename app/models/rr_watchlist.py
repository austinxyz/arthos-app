"""Risk Reversal Watchlist models."""
from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime, date
from uuid import UUID, uuid4
from typing import Optional, List
from decimal import Decimal


class RRWatchlist(SQLModel, table=True):
    """Risk Reversal Watchlist model."""
    __tablename__ = "rr_watchlist"
    
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
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
        description="Ratio of puts to calls (e.g., '1:1', '1:2')"
    )
    expired_yn: str = Field(
        max_length=1,
        default="N",
        description="Whether the options have expired (Y/N)"
    )
    
    # Relationship to history
    history: List["RRHistory"] = Relationship(back_populates="rr_entry", cascade_delete=True)


class RRHistory(SQLModel, table=True):
    """Risk Reversal History model."""
    __tablename__ = "rr_history"
    
    id: UUID = Field(
        default_factory=uuid4,
        primary_key=True,
        description="Unique identifier for the history entry"
    )
    rr_uuid: UUID = Field(
        foreign_key="rr_watchlist.id",
        description="Foreign key to rr_watchlist"
    )
    ticker: str = Field(
        max_length=10,
        description="Stock ticker symbol"
    )
    history_date: date = Field(
        description="Date for which the data represents"
    )
    net_cost: Decimal = Field(
        description="Recomputed net cost based on current option quote prices"
    )
    
    # Relationship to watchlist entry
    rr_entry: Optional[RRWatchlist] = Relationship(back_populates="history")
