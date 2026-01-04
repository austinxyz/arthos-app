"""Stock cache model for storing yfinance responses."""
from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional
import json


class StockCache(SQLModel, table=True):
    """Model for caching stock data from yfinance."""
    
    ticker: str = Field(primary_key=True, description="Stock ticker symbol")
    data: str = Field(description="JSON string of cached stock data DataFrame")
    cache_timestamp: datetime = Field(default_factory=datetime.now, description="When the cache entry was created")
    cache_version: Optional[int] = Field(default=None, description="Cache version for structure changes")
    
    class Config:
        """Pydantic config."""
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

