"""
Pydantic Schemas for Checkpoint 11: Document Comparison.
Provides structured, strictly validated models for two-level document comparison:
Level 1: Deterministic Python comparison (hashes, metadata, page diffs, OCR noise detection)
Level 2: Semantic comparison (LLM classification of text differences and eligibility relevance)
"""

from typing import List, Optional, Any, Literal
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class MetadataChange(BaseModel):
    """Represents a change in document metadata between old and new versions."""
    field: str = Field(description="Name of the metadata field that changed")
    old_value: Optional[Any] = Field(default=None, description="Previous value")
    new_value: Optional[Any] = Field(default=None, description="Updated value")


class TextChange(BaseModel):
    """
    Represents an individual text difference on a page.
    Distinguishes real modifications from OCR noise and formatting differences.
    """
    page_number: int = Field(description="1-based page number where difference occurs")
    change_type: str = Field(
        description="Type: 'modified', 'added', 'removed', 'ocr_noise', 'formatting'"
    )
    old_text: Optional[str] = Field(default=None, description="Original text snippet")
    new_text: Optional[str] = Field(default=None, description="New text snippet")
    similarity_ratio: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Character/token similarity ratio (0.0 to 1.0)"
    )
    is_ocr_noise: bool = Field(
        default=False,
        description="True if difference is minor spelling/punctuation/scanning artefact without policy change"
    )
    section: Optional[str] = Field(default=None, description="Section or block title if available")


class PageComparison(BaseModel):
    """Page-level status and comparison metrics."""
    page_number: int = Field(description="1-based page number")
    status: str = Field(
        description="Status: 'unchanged', 'modified', 'added', 'removed'"
    )
    similarity_ratio: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Overall text similarity ratio for the page"
    )
    text_changes: List[TextChange] = Field(
        default_factory=list,
        description="List of specific text differences found on this page"
    )
    old_page_type: Optional[str] = Field(default=None, description="TEXT, SCANNED, TABLE, FORM")
    new_page_type: Optional[str] = Field(default=None, description="TEXT, SCANNED, TABLE, FORM")


class SemanticChangeItem(BaseModel):
    """Semantic classification and assessment of an individual change."""
    category: str = Field(
        description="Classification: 'eligibility_related', 'exclusion_related', 'administrative', 'procedural', 'document_status', 'formatting', 'unclear'"
    )
    description: str = Field(description="Human-readable explanation of what changed")
    eligibility_relevance: str = Field(
        default="none",
        description="Impact: 'none', 'potentially_relevant', 'clearly_relevant', 'uncertain'"
    )
    affected_attribute: Optional[str] = Field(
        default=None,
        description="E.g. age, income, landholding, farmer_category, residency, employment_exclusion"
    )
    old_evidence: Optional[str] = Field(default=None, description="Verbatim quote from old text")
    new_evidence: Optional[str] = Field(default=None, description="Verbatim quote from new text")


class ComparisonMetadata(BaseModel):
    """Audit and execution metadata for the comparison."""
    pipeline_version: str = Field(default="1.0_document_comparison")
    compared_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    model_used: Optional[str] = Field(default=None, description="LLM model used for Level 2 comparison")
    old_sha256: Optional[str] = Field(default=None, description="SHA-256 fingerprint of old document")
    new_sha256: Optional[str] = Field(default=None, description="SHA-256 fingerprint of new document")
    deterministic_match: bool = Field(default=False, description="True if identical without LLM invocation")
    total_pages_old: int = Field(default=0)
    total_pages_new: int = Field(default=0)
    pages_modified: int = Field(default=0)
    pages_added: int = Field(default=0)
    pages_removed: int = Field(default=0)


class DocumentComparison(BaseModel):
    """
    Master schema for Checkpoint 11: Document Comparison.
    Contains results of deterministic Level 1 comparison and optional semantic Level 2 comparison.
    """
    old_document: str = Field(description="Identifier or filename of the original document")
    new_document: str = Field(description="Identifier or filename of the new document")
    hash_status: Literal["identical", "different"] = Field(
        description="Binary hash equality: 'identical' or 'different'"
    )
    overall_status: str = Field(
        default="unchanged",
        description="Overall verdict: 'unchanged', 'possible_change', 'different_document'"
    )
    metadata_changes: List[MetadataChange] = Field(
        default_factory=list,
        description="List of changes detected in document metadata"
    )
    page_comparisons: List[PageComparison] = Field(
        default_factory=list,
        description="Page-level comparison breakdown"
    )
    text_changes: List[TextChange] = Field(
        default_factory=list,
        description="Extracted text differences across all pages"
    )
    semantic_comparison_required: bool = Field(
        default=False,
        description="True if changes warrant Level 2 LLM semantic interpretation"
    )
    semantic_changes: List[SemanticChangeItem] = Field(
        default_factory=list,
        description="LLM-interpreted semantic change items"
    )
    semantic_summary: Optional[str] = Field(
        default=None,
        description="Concise summary of semantic differences"
    )
    eligibility_relevance: Literal["none", "potentially_relevant", "clearly_relevant", "uncertain"] = Field(
        default="none",
        description="Eligibility impact: 'none', 'potentially_relevant', 'clearly_relevant', or 'uncertain'"
    )
    review_required: bool = Field(
        default=False,
        description="True if human review is needed due to ambiguity, OCR noise, or unrelated documents"
    )
    review_reasons: List[str] = Field(
        default_factory=list,
        description="Specific reasons triggering review flag"
    )
    comparison_metadata: ComparisonMetadata = Field(
        description="Execution and audit metadata"
    )
