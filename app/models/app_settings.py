"""Generic key-value application settings stored in database."""
from datetime import datetime
from sqlmodel import SQLModel, Field


class AppSettings(SQLModel, table=True):
    """Simple key-value store for application settings."""
    __tablename__ = "app_settings"

    key: str = Field(primary_key=True, max_length=50)
    value: str = Field(max_length=255)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
