"""
Checkpoint 16.2: Kannada Rule Understanding & Recall Evaluation Module.
Measures Kannada semantic rule extraction, recall improvement, bilingual interpretation,
and zero-hallucination safety across the 5 benchmark documents.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

from app.quality_evaluation import (
    GOLD_STANDARDS_5_SCHEMES,
    calculate_evaluation_metrics,
    EvaluationMetrics,
    DocumentQualityMetrics,
    EvidenceQualityMetrics,
    SchemeGoldStandard,
)


class DiagnosticExperimentResult(BaseModel):
    """Results of a diagnostic experiment from CP16.2."""
    experiment_id: str
    name: str
    description: str
    model_or_service: str
    tp: int
    fp: int
    fn: int
    precision: Optional[float]
    recall: float
    f1: float
    avg_latency_per_page_seconds: float
    key_findings: str


class Checkpoint16_2Evaluation(BaseModel):
    """Full CP16.2 evaluation artifact schema."""
    timestamp: str
    schemes_evaluated: int
    gold_standards: Dict[str, SchemeGoldStandard]

    # CP16.2 Performance Metrics
    eligibility_metrics: EvaluationMetrics
    exclusion_metrics: EvaluationMetrics
    combined_metrics: EvaluationMetrics

    # Grounding & Safety Metrics
    evidence_quality: EvidenceQualityMetrics
    hallucinated_rules_count: int
    committee_false_positives_filtered: int
    funding_allocations_filtered: int
    external_knowledge_importation_rejected: int

    # Kannada Understanding Specifics
    kannada_evidence_preserved_count: int
    english_interpretations_generated_count: int
    bilingual_grounding_verified: bool

    # Multi-Experiment Diagnostic Results (Experiments A through E)
    experiments: List[DiagnosticExperimentResult]

    # Baseline Comparisons (CP16 vs CP16.1 vs CP16.2)
    comparison_table: Dict[str, Any]

    # Per-Document Results Breakdown
    per_document_results: Dict[str, Any]

    # Diagnostic Q&A (Answers to the 10 Diagnostic Questions)
    diagnostic_qa: Dict[str, str]

    limitations: List[str]
    production_architecture_recommendation: str
    checkpoint17_roadmap: List[str]
    conclusion: str
