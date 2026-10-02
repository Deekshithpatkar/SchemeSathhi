"""
Data models for the scheme update agent.
Uses Pydantic for clean, simple validation and data representation.
"""

from typing import Optional
from datetime import datetime
from pydantic import BaseModel


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


class DiscoveredDocument(BaseModel):
    """Represents a scheme document discovered on an official webpage."""
    document_url: str
    source_page_url: str
    title: str
    scheme_name: Optional[str] = None
    department: Optional[str] = None
    document_type: str = "guideline"  # guideline, order, circular, notification, application_form, other
    published_date: Optional[str] = None
    is_scheme_document: bool = True
