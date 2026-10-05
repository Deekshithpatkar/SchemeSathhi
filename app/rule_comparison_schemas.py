"""
Pydantic Schemas for Checkpoint 12: Rule Comparison.
Provides structured models for comparing old and new extracted candidate eligibility
and exclusion rule sets.
"""

from typing import List, Optional, Any, Literal
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from app.schemas import RuleItem, SchemeEvidence


class RuleComparison(BaseModel):
    """
    Represents the comparison outcome for an individual eligibility or exclusion rule.
    Links the old rule, new rule, classification, direction of impact, and grounded evidence.
    """
    old_rule: Optional[RuleItem] = Field(default=None, description="The previous rule definition if existing")
    new_rule: Optional[RuleItem] = Field(default=None, description="The updated rule definition if existing")
    change_type: Literal["added", "removed", "modified", "unchanged"] = Field(
        description="Type of change: 'added', 'removed', 'modified', 'unchanged'"
    )
    category: str = Field(
        default="other",
        description="Attribute category: income, age, landholding, residency, farmer_category, occupation, government_employee, beneficiary_category, caste_category, gender, institutional_landholder, family_status, disability, employment_status, other"
    )
    impact: Literal[
        "eligibility_more_restrictive",
        "eligibility_less_restrictive",
        "exclusion_added",
        "exclusion_removed",
        "no_eligibility_impact",
        "uncertain"
    ] = Field(
        description="Direction of impact on candidate eligibility"
    )
    evidence: Optional[SchemeEvidence] = Field(default=None, description="Physical grounding evidence for this rule/change")
    confidence: float = Field(
        default=0.90,
        ge=0.0,
        le=1.0,
        description="Semantic comparison confidence score (0.0 to 1.0). Distinct from OCR confidence."
    )
    review_required: bool = Field(default=False, description="True if ambiguity requires human verification")
    review_reasons: List[str] = Field(default_factory=list, description="Reasons triggering review")


class RuleComparisonMetadata(BaseModel):
    """Execution and audit metadata for the rule comparison."""
    pipeline_version: str = Field(default="1.0_rule_comparison")
    compared_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model_used: Optional[str] = Field(default=None, description="LLM model used if semantic comparison was required")
    deterministic_match: bool = Field(default=False, description="True if matched 100% deterministically without LLM")
    total_old_rules: int = Field(default=0)
    total_new_rules: int = Field(default=0)
    total_changes: int = Field(default=0)


class RuleComparisonResult(BaseModel):
    """
    Master result schema for Checkpoint 12: Rule Comparison.
    Answers: 'Between the old and new extracted rule sets, did the actual candidate eligibility or exclusion rules change?'
    """
    old_document: str = Field(description="Identifier or filename of the original document/rules")
    new_document: str = Field(description="Identifier or filename of the new document/rules")
    rule_changes: List[RuleComparison] = Field(
        default_factory=list,
        description="All rule comparison items (added, removed, modified, unchanged)"
    )
    added_rules: List[RuleComparison] = Field(default_factory=list, description="Rules newly introduced")
    removed_rules: List[RuleComparison] = Field(default_factory=list, description="Rules eliminated")
    modified_rules: List[RuleComparison] = Field(default_factory=list, description="Rules whose thresholds or conditions changed")
    unchanged_rules: List[RuleComparison] = Field(default_factory=list, description="Rules with identical semantic meaning")
    eligibility_relevance: Literal["none", "potentially_relevant", "clearly_relevant", "uncertain"] = Field(
        default="none",
        description="Overall eligibility relevance: 'none', 'potentially_relevant', 'clearly_relevant', 'uncertain'"
    )
    summary: str = Field(description="Clear human-readable summary of candidate eligibility changes")
    review_required: bool = Field(default=False, description="True if any rule change is uncertain or ambiguous")
    review_reasons: List[str] = Field(default_factory=list, description="Reasons for review across all rules")
    comparison_metadata: RuleComparisonMetadata = Field(description="Audit and execution parameters")
