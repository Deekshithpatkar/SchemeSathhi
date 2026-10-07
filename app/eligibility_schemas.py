"""
Checkpoint 17: Citizen Eligibility Result Schemas.

Defines the structured output models for deterministic rule evaluation and scheme decisions.
"""

from enum import Enum
from typing import Optional, List, Dict, Any, Union
from datetime import datetime, timezone
from pydantic import BaseModel, Field


class DecisionStatus(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class RuleEvaluationStatus(str, Enum):
    MATCH = "MATCH"
    NO_MATCH = "NO_MATCH"
    UNKNOWN = "UNKNOWN"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RuleEvaluationResult(BaseModel):
    """Result of evaluating a single scheme rule against a citizen profile."""
    rule_id: Optional[Union[int, str]] = None
    rule: str
    rule_type: str = "eligibility"  # 'eligibility', 'exclusion'
    rule_scope: str = "candidate"  # 'candidate', 'household', 'beneficiary_limit', 'administrative'
    status: RuleEvaluationStatus = RuleEvaluationStatus.UNKNOWN
    matched: Optional[bool] = None  # True if condition triggered, False if not, None if unknown
    reason: str = ""
    evidence: Optional[str] = None
    original_kannada_evidence: Optional[str] = None
    english_interpretation: Optional[str] = None
    page_number: Optional[int] = None
    source_url: Optional[str] = None
    confidence: float = 1.0
    review_required: bool = False
    evidence_consistency_status: Optional[str] = "SUPPORTED"
    semantic_validation_confidence: Optional[float] = 1.0


class EligibilityResult(BaseModel):
    """Comprehensive evaluation result for a citizen profile against a Karnataka scheme."""
    scheme_key: str
    scheme_name: str
    citizen_identifier: Optional[str] = None
    decision: DecisionStatus
    summary: str
    eligibility_results: List[RuleEvaluationResult] = Field(default_factory=list)
    exclusion_results: List[RuleEvaluationResult] = Field(default_factory=list)
    household_results: List[RuleEvaluationResult] = Field(default_factory=list)
    review_reasons: List[str] = Field(default_factory=list)
    missing_information: List[str] = Field(default_factory=list)
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    version_label: Optional[str] = None
    version_status: Optional[str] = "ACTIVE"
    evaluated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    engine_version: str = "17.0_deterministic"
