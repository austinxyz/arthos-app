from typing import Optional, List, TYPE_CHECKING
from datetime import datetime
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel, Relationship, VARCHAR

if TYPE_CHECKING:
    from app.models.watchlist import WatchList
    from app.models.rr_watchlist import RRWatchlist

class Account(SQLModel, table=True):
    __tablename__ = "account"
    
    id: UUID = Field(default_factory=uuid4, primary_key=True, sa_type=VARCHAR(36))
    email: str = Field(index=True, unique=True)
    google_sub: str = Field(index=True, unique=True)
    full_name: Optional[str] = None
    picture_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_login_at: Optional[datetime] = None
    
    # Relationships
    watchlists: List["WatchList"] = Relationship(back_populates="account")
    rr_watchlists: List["RRWatchlist"] = Relationship(back_populates="account")
