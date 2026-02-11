"""
Shared utility functions for route handlers.
"""
from fastapi import HTTPException, Request
import os


def _require_admin(request: Request):
    """Check that the request comes from an admin user. Raises HTTPException if not."""
    user = request.session.get("user") if hasattr(request, "session") else None
    if not user:
        raise HTTPException(status_code=403, detail="Admin access required. Please log in.")

    admin_email = os.getenv("ADMIN_EMAIL")
    if not admin_email or user.get("email") != admin_email:
        raise HTTPException(status_code=403, detail="Admin access required.")


def _format_duration(seconds: float) -> str:
    """Format duration in seconds to human-readable string."""
    if seconds is None:
        return "N/A"

    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"
