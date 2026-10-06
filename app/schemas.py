"""
Pydantic schemas for Checkpoint 10: Semantic Eligibility & Rule Extraction.
Laser-focused on extracting rules that determine candidate qualification (eligible vs excluded).
Preserves physical evidence, separates OCR confidence from semantic confidence,
and ensures internal consistency for review flags.
"""

from typing import List, Optional, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, model_validator


class SchemeEvidence(BaseModel):
    """
    Physical evidence grounding an extracted rule or piece of information.
    Points directly to the Step 9 source coordinates, table cells, or text.
    """
    page_number: int = Field(default=1, description="1-based page number where evidence was found")
    source_text: Optional[str] = Field(default=None, description="Verbatim or near-verbatim text from the document")
    section: Optional[str] = Field(default=None, description="Section heading or context if available")
    table_index: Optional[int] = Field(default=None, description="0-based table index on the page")
    row_index: Optional[int] = Field(default=None, description="0-based row index within the table")
    column_index: Optional[int] = Field(default=None, description="0-based column index within the table")
    cell_text: Optional[str] = Field(default=None, description="Extracted text from the specific cell")
    ocr_confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="Physical OCR confidence percentage (0-100) from Step 9"
    )
    original_kannada_evidence: Optional[str] = Field(
        default=None,
        description="Original verbatim Kannada source text"
    )
    english_interpretation: Optional[str] = Field(
        default=None,
        description="English translation or semantic interpretation of the rule/evidence"
    )


class RuleItem(BaseModel):
    """
    Individual candidate eligibility or exclusion rule.
    Determines whether a candidate qualifies for the scheme.
    """
    rule: str = Field(description="Clear statement of the eligibility or exclusion rule")
    type: str = Field(
        default="eligibility",
        description="Type of rule: 'eligibility' (must satisfy) or 'exclusion' (disqualifies candidate)"
    )
    value: Optional[Any] = Field(
        default=None,
        description="Specific threshold, criteria, or boolean requirement (null if unstated)"
    )
    category: Optional[str] = Field(
        default="general",
        description="Category: age, income, occupation, land_ownership, land_size, residency, caste/category, employment, farmer_status, beneficiary_status, family_status, geographic_location, other"
    )
    evidence: Optional[SchemeEvidence] = Field(default=None, description="Physical grounding for this rule")
    semantic_confidence: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Semantic extraction confidence score (0.0 to 1.0, default 0.85). Never assume 1.0 automatically."
    )
    review_required: bool = Field(default=False, description="Flag indicating human review is needed")
    review_reasons: List[str] = Field(
        default_factory=list,
        description="Reasons for review (e.g. low OCR confidence, ambiguous wording)"
    )

    @model_validator(mode="before")
    @classmethod
    def cap_semantic_confidence(cls, data: Any) -> Any:
        """Prevent naive 1.0 semantic confidence on scanned extraction."""
        if isinstance(data, dict):
            sem_conf = data.get("semantic_confidence")
            if sem_conf is not None:
                try:
                    val = float(sem_conf)
                    # Cap at 0.95 to avoid false 100% certainty for NLP extraction
                    if val >= 1.0:
                        data["semantic_confidence"] = 0.90
                except (ValueError, TypeError):
                    data["semantic_confidence"] = 0.85
            else:
                data["semantic_confidence"] = 0.85
        return data


class ExtractionMetadata(BaseModel):
    """
    Metadata recording execution parameters, model, and validation metrics.
    """
    pipeline_version: str = Field(default="1.0_semantic_extraction")
    model: str = Field(description="Name of the LLM model used")
    processed_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source_document: str = Field(description="Filename of the source document")
    validation_status: str = Field(default="valid", description="Status: valid, review_needed, partial, failed")
    rule_count: int = Field(default=0, description="Total number of eligibility & exclusion rules extracted")
    review_required_count: int = Field(default=0, description="Number of items or issues requiring human review")
    errors: List[str] = Field(default_factory=list, description="Any validation or parsing errors encountered")


def is_rule_absence_statement(text: Optional[str]) -> bool:
    """
    Returns True if the statement merely asserts the absence of rules
    (e.g., 'No specific exclusion rules provided in the document', 'No exclusions mentioned').
    """
    if not text:
        return False
    t = str(text).strip().lower()
    absence_markers = [
        "no specific exclusion",
        "no exclusion rule",
        "no exclusions mentioned",
        "no specific exclusion criteria",
        "no exclusion criteria",
        "no exclusion rules provided",
        "no exclusions provided",
        "no exclusion provided",
        "no exclusions found",
        "no exclusion stated",
        "no specific eligibility",
        "no eligibility rule",
        "no eligibility criteria",
        "no eligibility rules provided",
        "no eligibility provided",
        "no specific rules",
        "none mentioned",
        "none provided",
        "none stated",
        "not mentioned in document",
        "not specified in document",
        "not provided in document",
        "not available in document",
        "ಯಾವುದೇ ಅನರ್ಹತೆ ನಿಯಮಗಳಿಲ್ಲ",
        "ಯಾವುದೇ ಅರ್ಹತಾ ನಿಯಮಗಳಿಲ್ಲ",
    ]
    for m in absence_markers:
        if m in t:
            return True
    if t.startswith(("no exclusion", "no eligibility", "no specific exclusion", "no candidate exclusion")):
        return True
    return False


class SchemeExtraction(BaseModel):
    """
    Master schema for Checkpoint 10: Semantic Eligibility & Rule Extraction.
    Focused exclusively on candidate qualification rules (eligibility and exclusions).
    """
    scheme_name: Optional[str] = Field(default=None, description="Official or common scheme name")
    department: Optional[str] = Field(default=None, description="Nodal government department or ministry")
    document_type: Optional[str] = Field(
        default=None,
        description="Type: guidelines, government_order, circular, notification, application_form, unknown"
    )
    document_date: Optional[str] = Field(default=None, description="Official document or circular date")
    version_information: Optional[str] = Field(default=None, description="Government Order (GO) number or version label")
    purpose: Optional[str] = Field(default=None, description="Stated objective or purpose of the scheme/document")

    # Core Candidate Qualification Rules
    eligibility_rules: List[RuleItem] = Field(
        default_factory=list,
        description="Rules establishing candidate eligibility (e.g. farmer status, land size, income ceiling, age range, residency)"
    )
    exclusion_rules: List[RuleItem] = Field(
        default_factory=list,
        description="Rules establishing candidate disqualification/exclusion (e.g. government employees, existing beneficiaries, income above threshold)"
    )

    sources: List[str] = Field(default_factory=list, description="Source URLs or filenames")
    review_required: bool = Field(default=False, description="Flag indicating the document requires human review")
    review_reasons: List[str] = Field(default_factory=list, description="Summary of reasons why review is required")

    extraction_metadata: Optional[ExtractionMetadata] = Field(default=None, description="Audit and execution metadata")

    @property
    def eligibility(self) -> List[RuleItem]:
        """Backward-compatibility alias."""
        return self.eligibility_rules

    @property
    def exclusions(self) -> List[RuleItem]:
        """Backward-compatibility alias."""
        return self.exclusion_rules


    @model_validator(mode="before")
    @classmethod
    def sanitize_input(cls, data: Any) -> Any:
        """
        Sanitizes raw LLM inputs:
        1. Maps 'eligibility' -> 'eligibility_rules' and 'exclusions' -> 'exclusion_rules' if provided.
        2. Converts null lists into empty lists.
        3. Cleans empty dummy rule objects.
        4. Drops fake rules that merely assert absence of exclusions or eligibility criteria.
        """
        if isinstance(data, dict):
            # Backward-compatible mapping of aliases
            if "eligibility" in data and "eligibility_rules" not in data:
                data["eligibility_rules"] = data.pop("eligibility")
            if "exclusions" in data and "exclusion_rules" not in data:
                data["exclusion_rules"] = data.pop("exclusions")

            list_fields = ["eligibility_rules", "exclusion_rules", "sources", "review_reasons"]
            for lf in list_fields:
                val = data.get(lf)
                if val is None:
                    data[lf] = []
                elif isinstance(val, list):
                    clean_list = []
                    for item in val:
                        if isinstance(item, dict):
                            # Clean empty evidence objects
                            if isinstance(item.get("evidence"), dict) and not any(v is not None for v in item["evidence"].values()):
                                item["evidence"] = None

                            rule_str = str(item.get("rule", "")).strip()
                            # Require non-empty rule statement
                            if not rule_str or rule_str.lower() in ("null", "none", ""):
                                continue

                            # Drop fake rules asserting absence of criteria (e.g. "No specific exclusion rules provided")
                            ev_text = ""
                            if isinstance(item.get("evidence"), dict):
                                ev_text = str(item["evidence"].get("source_text", ""))
                            if is_rule_absence_statement(rule_str) or is_rule_absence_statement(ev_text):
                                continue

                            # Ensure type field is consistent
                            if lf == "exclusion_rules" and not item.get("type"):
                                item["type"] = "exclusion"
                            elif lf == "eligibility_rules" and not item.get("type"):
                                item["type"] = "eligibility"

                        clean_list.append(item)
                    data[lf] = clean_list
        return data

    @model_validator(mode="after")
    def sync_review_required(self) -> "SchemeExtraction":
        """If any review reasons are present, automatically mark review_required as True."""
        if self.review_reasons and len(self.review_reasons) > 0:
            self.review_required = True
        return self
