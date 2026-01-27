"""Cached options strategy models for storing pre-computed strategy calculations."""
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import Numeric
from datetime import date, datetime
from decimal import Decimal
from typing import Optional


class CachedCoveredCall(SQLModel, table=True):
    """Cached covered call strategy calculations."""
    __tablename__ = "cached_covered_call"

    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str = Field(max_length=8, index=True)
    expiration_date: date = Field(description="Options expiration date")
    strike: Decimal = Field(
        sa_column=Column(Numeric(12, 2)),
        description="Strike price"
    )
    call_premium: Decimal = Field(
        sa_column=Column(Numeric(12, 2)),
        description="Call option premium (mid price)"
    )
    return_exercised: Decimal = Field(
        sa_column=Column(Numeric(12, 2)),
        description="Dollar return if exercised"
    )
    return_pct_exercised: Decimal = Field(
        sa_column=Column(Numeric(12, 4)),
        description="Percent return if exercised"
    )
    annualized_return_exercised: Decimal = Field(
        sa_column=Column(Numeric(12, 4)),
        description="Annualized return if exercised"
    )
    return_not_exercised: Decimal = Field(
        sa_column=Column(Numeric(12, 2)),
        description="Dollar return if not exercised"
    )
    return_pct_not_exercised: Decimal = Field(
        sa_column=Column(Numeric(12, 4)),
        description="Percent return if not exercised"
    )
    annualized_return_not_exercised: Decimal = Field(
        sa_column=Column(Numeric(12, 4)),
        description="Annualized return if not exercised"
    )
    return_difference: Decimal = Field(
        sa_column=Column(Numeric(12, 4)),
        description="Absolute difference between exercised and not-exercised return %"
    )
    days_to_expiration: int = Field(description="Days until expiration")
    current_price: Decimal = Field(
        sa_column=Column(Numeric(12, 2)),
        description="Stock price at computation time"
    )
    computed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when strategy was computed"
    )


class CachedRiskReversal(SQLModel, table=True):
    """Cached risk reversal strategy calculations."""
    __tablename__ = "cached_risk_reversal"

    id: Optional[int] = Field(default=None, primary_key=True)
    ticker: str = Field(max_length=8, index=True)
    expiration_date: date = Field(description="Options expiration date")
    ratio: str = Field(max_length=10, description="Strategy ratio: 1:1, 1:2, or Collar")
    put_strike: Decimal = Field(
        sa_column=Column(Numeric(12, 2)),
        description="Put strike price"
    )
    call_strike: Decimal = Field(
        sa_column=Column(Numeric(12, 2)),
        description="Call strike price"
    )
    short_call_strike: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 2)),
        description="Sold call strike price (Collar only)"
    )
    put_premium: Decimal = Field(
        sa_column=Column(Numeric(12, 2)),
        description="Put option premium (mid price)"
    )
    call_premium: Decimal = Field(
        sa_column=Column(Numeric(12, 2)),
        description="Call option premium (mid price)"
    )
    short_call_premium: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 2)),
        description="Sold call premium (Collar only)"
    )
    net_cost: Decimal = Field(
        sa_column=Column(Numeric(12, 2)),
        description="Net cost of strategy"
    )
    cost_pct: Decimal = Field(
        sa_column=Column(Numeric(12, 4)),
        description="Net cost as percent of stock price"
    )
    days_to_expiration: int = Field(description="Days until expiration")
    put_risk: Decimal = Field(
        sa_column=Column(Numeric(12, 2)),
        description="Put risk (strike * 100)"
    )
    current_price: Decimal = Field(
        sa_column=Column(Numeric(12, 2)),
        description="Stock price at computation time"
    )
    collar_type: Optional[str] = Field(
        default=None,
        max_length=5,
        description="Collar type: 1:1 or 1:2 (Collar only)"
    )
    put_breakeven: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 2)),
        description="Put breakeven price"
    )
    call_breakeven: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 2)),
        description="Call breakeven price"
    )
    computed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp when strategy was computed"
    )
