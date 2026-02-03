"""Stock price models for storing historical price data."""
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import Numeric, UniqueConstraint, Text
from datetime import date, datetime
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
    iv: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 4)),
        description="Implied volatility (ATM options average) for this date"
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
    next_dividend_date: Optional[date] = Field(
        default=None,
        description="Next ex-dividend date"
    )
    # Implied Volatility data
    current_iv: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 4)),
        description="Current implied volatility (ATM options average)"
    )
    iv_rank: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 4)),
        description="IV Rank: (Current IV - 52wk Low) / (52wk High - 52wk Low) * 100"
    )
    iv_percentile: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 4)),
        description="IV Percentile: % of days in past year with lower IV"
    )
    iv_high_52w: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 4)),
        description="52-week high implied volatility"
    )
    iv_low_52w: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 4)),
        description="52-week low implied volatility"
    )
    # Pre-computed trading metrics (updated by scheduler)
    devstep: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 4)),
        description="Number of standard deviations from 50-day SMA"
    )
    signal: Optional[str] = Field(
        default=None,
        max_length=20,
        description="Trading signal (Strong Buy, Buy, Neutral, Sell, Strong Sell)"
    )
    movement_5day_stddev: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 4)),
        description="5-day price movement in standard deviations"
    )
    stddev_50d: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 4)),
        description="50-day standard deviation of close prices"
    )
    # LLM-generated insights
    insights_json: Optional[str] = Field(
        default=None,
        sa_column=Column(Text),
        description="JSON string with LLM-generated insights (going_right/going_wrong)"
    )
    insights_updated_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp when insights were last fetched from LLM"
    )