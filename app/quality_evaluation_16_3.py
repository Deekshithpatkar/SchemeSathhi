"""
Checkpoint 16.3: Rule Semantic Validation & Evidence Consistency Evaluation Module.
Evaluates:
- Semantic consistency between English rule claims and authoritative Kannada evidence
- Contradiction detection (e.g. land owner vs landless, polarity inversions)
- Household constraint and beneficiary limit classification
- Precision, Recall, F1, and Grounding under strict semantic validation
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.quality_evaluation import (
    GOLD_STANDARDS_5_SCHEMES,
    calculate_evaluation_metrics,
    EvaluationMetrics,
    EvidenceQualityMetrics,
    SchemeGoldStandard,
)


class SemanticValidationMetrics(BaseModel):
    """Metrics tracking semantic consistency and contradiction detection."""
    total_rules_audited: int
    supported_rules_count: int
    contradicted_rules_count: int
    insufficient_rules_count: int
    review_required_count: int
    evidence_entailment_accuracy: float  # Percentage of accepted rules that are truly entailed
    contradiction_detection_rate: float  # Percentage of semantic inversions caught
    unsupported_claim_rate: float        # Percentage of rules making claims beyond evidence
    review_capture_rate: float           # Percentage of questionable rules flagged for human review
    true_negative_accuracy: float        # True-negative preservation across administrative docs


class SemanticErrorDetail(BaseModel):
    """Details of a semantic contradiction or mismatch caught by validation."""
    scheme: str
    rule_text: str
    original_kannada_evidence: str
    error_type: str
    status: str
    action_taken: str


class Checkpoint16_3Evaluation(BaseModel):
    """Full CP16.3 evaluation artifact schema."""
    timestamp: str
    schemes_evaluated: int
    gold_standards: Dict[str, SchemeGoldStandard]

    # Performance Metrics
    eligibility_metrics: EvaluationMetrics
    exclusion_metrics: EvaluationMetrics
    combined_metrics: EvaluationMetrics

    # Semantic Validation Specifics
    semantic_validation_metrics: SemanticValidationMetrics
    semantic_errors_caught: List[SemanticErrorDetail]

    # Multi-Checkpoint Comparison (CP16 vs CP16.1 vs CP16.2 vs CP16.3)
    comparison_table: Dict[str, Any]

    # Per-Document Breakdown
    per_document_results: Dict[str, Any]

    limitations: List[str]
    safe_to_proceed_to_cp17: bool
    conclusion: str
