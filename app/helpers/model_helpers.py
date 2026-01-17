"""Helper functions for dynamically working with SQLModel models."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Type
from sqlmodel import SQLModel


def get_model_fields(model_class: Type[SQLModel]) -> List[str]:
    """
    Get all field names from a SQLModel class.
    
    Args:
        model_class: The SQLModel class to inspect
        
    Returns:
        List of field names in definition order
    """
    return list(model_class.__fields__.keys())


def format_field_value(value: Any, field_name: str = "") -> str:
    """
    Format a field value for display based on its type.
    
    Args:
        value: The value to format
        field_name: Optional field name for context-aware formatting
        
    Returns:
        Formatted string representation
    """
    if value is None:
        return None
    
    if isinstance(value, datetime):
        return value.strftime('%Y-%m-%d %H:%M:%S')
    elif isinstance(value, date):
        return value.strftime('%b %d, %Y')
    elif isinstance(value, Decimal):
        if 'yield' in field_name.lower():
            return f"{float(value):.4f}%"
        elif 'amt' in field_name.lower() or 'amount' in field_name.lower() or 'price' in field_name.lower():
            return f"${float(value):.4f}"
        else:
            return f"{float(value):.4f}"
    elif isinstance(value, bool):
        return "Yes" if value else "No"
    elif isinstance(value, float):
        return f"{value:.4f}"
    else:
        return str(value)


def field_name_to_label(field_name: str, custom_labels: Optional[Dict[str, str]] = None) -> str:
    """
    Convert a field name to a human-readable label.
    
    Args:
        field_name: The field name (e.g., 'next_earnings_date')
        custom_labels: Optional dict mapping field names to custom labels
        
    Returns:
        Human-readable label (e.g., 'Next Earnings Date')
    """
    if custom_labels and field_name in custom_labels:
        return custom_labels[field_name]
    
    # Convert snake_case to Title Case
    return field_name.replace("_", " ").title()


def model_to_dict(
    instance: SQLModel,
    custom_labels: Optional[Dict[str, str]] = None,
    exclude_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Convert a SQLModel instance to a dictionary with formatted values.
    
    Args:
        instance: The model instance
        custom_labels: Optional dict mapping field names to custom labels
        exclude_fields: Optional list of field names to exclude
        
    Returns:
        Dictionary with field info
    """
    exclude_fields = exclude_fields or []
    result = {}
    
    for field_name in instance.__class__.__fields__:
        if field_name in exclude_fields:
            continue
            
        value = getattr(instance, field_name, None)
        result[field_name] = {
            "field": field_name,
            "label": field_name_to_label(field_name, custom_labels),
            "value": format_field_value(value, field_name),
            "raw_value": value
        }
    
    return result


def model_instance_to_table_row(
    instance: SQLModel,
    extra_columns: Optional[Dict[str, Any]] = None,
    exclude_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Convert a SQLModel instance to a table row dictionary.
    Useful for log tables where each row is a model instance.
    
    Args:
        instance: The model instance
        extra_columns: Optional dict of computed/extra column values
        exclude_fields: Optional list of field names to exclude
        
    Returns:
        Dictionary with all field values plus extra columns
    """
    exclude_fields = exclude_fields or []
    row = {}
    
    for field_name in instance.__class__.__fields__:
        if field_name in exclude_fields:
            continue
        row[field_name] = getattr(instance, field_name, None)
    
    # Add extra computed columns
    if extra_columns:
        row.update(extra_columns)
    
    return row


def get_table_columns(
    model_class: Type[SQLModel],
    custom_labels: Optional[Dict[str, str]] = None,
    extra_columns: Optional[List[Dict[str, str]]] = None,
    exclude_fields: Optional[List[str]] = None
) -> List[Dict[str, str]]:
    """
    Get column definitions for a table based on model fields.
    
    Args:
        model_class: The SQLModel class
        custom_labels: Optional dict mapping field names to custom labels
        extra_columns: Optional list of extra column definitions [{"field": "...", "label": "..."}]
        exclude_fields: Optional list of field names to exclude
        
    Returns:
        List of column definitions [{"field": "...", "label": "..."}]
    """
    exclude_fields = exclude_fields or []
    columns = []
    
    for field_name in model_class.__fields__:
        if field_name in exclude_fields:
            continue
        columns.append({
            "field": field_name,
            "label": field_name_to_label(field_name, custom_labels)
        })
    
    # Add extra columns
    if extra_columns:
        columns.extend(extra_columns)
    
    return columns
