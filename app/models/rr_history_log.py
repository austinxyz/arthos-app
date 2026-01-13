"""RR History scheduler log model for tracking RR history update execution."""
from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional


class RRHistoryLog(SQLModel, table=True):
    """Model for logging RR history update runs."""
    __tablename__ = "rr_history_log"
    
    id: Optional[int] = Field(
        default=None,
        primary_key=True,
        description="Auto-incrementing sequence ID"
    )
    start_time: datetime = Field(
        description="Timestamp when RR history update started"
    )
    end_time: Optional[datetime] = Field(
        default=None,
        description="Timestamp when RR history update finished"
    )
    notes: Optional[str] = Field(
        default=None,
        description="Notes about the update run (e.g., count of entries updated)"
    )
