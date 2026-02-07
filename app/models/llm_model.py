"""LLM model configuration stored in database."""
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class LLMModel(SQLModel, table=True):
    """Tracks available LLM models with tier (free/paid) and active status."""
    __tablename__ = "llm_model"

    id: Optional[int] = Field(default=None, primary_key=True)
    model_name: str = Field(max_length=100)
    tier: str = Field(max_length=10)  # "free" or "paid"
    is_active: bool = Field(default=False)
    created_at: datetime = Field(default_factory=datetime.utcnow)
