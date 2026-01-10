"""Scheduler log model for tracking scheduler execution."""
from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional


class SchedulerLog(SQLModel, table=True):
    """Model for logging scheduler execution runs."""
    __tablename__ = "scheduler_log"
    
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="Auto-incrementing sequence ID"
    )
    start_time: datetime = Field(
        description="Timestamp when scheduler run started"
    )
    end_time: Optional[datetime] = Field(
        default=None,
        description="Timestamp when scheduler run finished"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Notes about the scheduler run (e.g., count of stocks fetched)"
    )
