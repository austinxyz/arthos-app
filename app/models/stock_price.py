"""Stock price models for storing historical price data."""
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import Numeric, UniqueConstraint
from datetime import date
from decimal import Decimal
from typing import Optional


class StockPrice(SQLModel, table=True):
    """Model for storing daily stock price data."""
    __tablename__ = "stock_price"
    
    price_date: date = Field(
        primary_key=True,
        description="Trading day for the stock prices"
    )
    ticker: str = Field(
        max_length=8,
        primary_key=True,
        description="Stock ticker symbol"
    )
    open_price: Decimal = Field(
        sa_column=Column(Numeric(12, 4)),
        description="Opening price"
    )
    close_price: Decimal = Field(
        sa_column=Column(Numeric(12, 4)),
        description="Closing price"
    )
    high_price: Decimal = Field(
        sa_column=Column(Numeric(12, 4)),
        description="Highest price"
    )
    low_price: Decimal = Field(
        sa_column=Column(Numeric(12, 4)),
        description="Lowest price"
    )
    dma_50: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 4)),
        description="50-day moving average"
    )
    dma_200: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 4)),
        description="200-day moving average"
    )
    
    __table_args__ = (
        UniqueConstraint("ticker", "price_date", name="uq_stock_price_ticker_date"),
    )


class StockAttributes(SQLModel, table=True):
    """Model for storing stock attributes and tracking date ranges of available stock price data."""
    __tablename__ = "stock_attributes"
    
    ticker: str = Field(
        max_length=8,
        primary_key=True,
        description="Stock ticker symbol"
    )
    earliest_date: date = Field(
        description="Earliest date with data available in stock_price table"
    )
    latest_date: date = Field(
        description="Latest date with data available in stock_price table"
    )
    dividend_amt: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 4)),
        description="Annual dividend amount for the stock"
    )
    dividend_yield: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 4)),
        description="Dividend yield as a percentage (dividend amount divided by current stock price)"
    )
    next_earnings_date: Optional[date] = Field(
        default=None,
        description="Next earnings announcement date"
    )
    is_earnings_date_estimate: Optional[bool] = Field(
        default=None,
        description="Whether the earnings date is an estimate"
    )