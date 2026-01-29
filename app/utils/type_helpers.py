"""Shared type conversion utilities."""
from typing import Optional, Union
from uuid import UUID


def to_str(value: Union[str, UUID, None]) -> Optional[str]:
    """
    Convert UUID to string, pass through strings, return None for None.

    Used for comparing account_id values that may come from different sources:
    - PostgreSQL returns UUID objects when reading from database
    - Session stores strings
    - Model validators convert to strings

    Args:
        value: A UUID, string, or None

    Returns:
        String representation or None
    """
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    return value


def safe_float(value, default: float = 0.0) -> float:
    """
    Safely convert a value to float, returning default if None or NaN.

    Args:
        value: Value to convert (can be None, NaN, or numeric)
        default: Default value to return if conversion fails

    Returns:
        Float value or default
    """
    import pandas as pd

    if value is None:
        return default
    if pd.isna(value):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
