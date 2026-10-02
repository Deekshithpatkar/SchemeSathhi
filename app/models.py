"""
Data models for the scheme update agent.
Uses Pydantic for clean, simple validation and data representation.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel, HttpUrl


class SourceRecord(BaseModel):
    """Represents an official government website in the source registry."""
    id: Optional[int] = None
    department: Optional[str] = None
    source_name: str
    official_url: str
    source_type: str = "scheme_page"
    active: bool = True
    last_checked: Optional[datetime] = None
    last_successful_check: Optional[datetime] = None
    created_at: Optional[datetime] = None
