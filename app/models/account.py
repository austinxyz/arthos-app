from typing import Optional, List, TYPE_CHECKING, Union
from datetime import datetime
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel, Relationship, VARCHAR
from pydantic import field_validator

if TYPE_CHECKING:
    from app.models.watchlist import WatchList
    from app.models.rr_watchlist import RRWatchlist


def generate_uuid_str() -> str:
    """Generate a UUID as a string."""
    return str(uuid4())


class Account(SQLModel, table=True):
    __tablename__ = "account"

    # Store UUID as string for SQLite compatibility
    id: str = Field(default_factory=generate_uuid_str, primary_key=True, sa_type=VARCHAR(36))

    @field_validator('id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        """Convert UUID to string if needed."""
        if isinstance(v, UUID):
            return str(v)
        return v
    email: str = Field(index=True, unique=True)
    google_sub: str = Field(index=True, unique=True)
    full_name: Optional[str] = None
    picture_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login_at: Optional[datetime] = None
    
    # Relationships
    watchlists: List["WatchList"] = Relationship(back_populates="account")
    rr_watchlists: List["RRWatchlist"] = Relationship(back_populates="account")
