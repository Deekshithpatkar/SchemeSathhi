"""
Checkpoint 16.1: Document Text Reliability, Kannada OCR & Strict Grounding Evaluation Module.
Quantitatively measures the improvements of CP16.1 over the CP16 baseline:
- Digital text reliability detection & automatic OCR fallback
- Kannada OCR multi-engine processing (Tesseract local + Sarvam adapter)
- Committee member nomination filtering
- Hallucination eradication and strict evidence grounding
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


class BenchmarkEngineResult(BaseModel):
    """Benchmark results for a text extraction or OCR engine."""
    engine_name: str
    category: str  # 'digital_extractor' or 'ocr_engine'
    usable_text_extracted: bool
    kannada_unicode_support: bool
    mojibake_susceptible: bool
    avg_speed_per_page_seconds: float
    requires_external_credentials: bool
    notes: str


class Checkpoint16_1Evaluation(BaseModel):
    """Full CP16.1 evaluation artifact schema."""
    timestamp: str
    schemes_evaluated: int
    gold_standards: Dict[str, SchemeGoldStandard]
    
    # CP16.1 Performance Metrics
    eligibility_metrics: EvaluationMetrics
    exclusion_metrics: EvaluationMetrics
    combined_metrics: EvaluationMetrics
    
    # Document and Processing Metrics
    document_processing: DocumentQualityMetrics
    ocr_backends_evaluated: List[BenchmarkEngineResult]
    ocr_backend_selected: str
    sarvam_configured: bool
    
    # Text Reliability & Fallback Metrics
    pages_analyzed_for_reliability: int
    pages_judged_unreliable: int
    ocr_fallbacks_triggered: int
    
    # Evidence & Grounding Metrics
    evidence_quality: EvidenceQualityMetrics
    hallucinated_rules_count: int
    committee_false_positives_filtered: int
    
    # Comparison against CP16 Baseline
    baseline_cp16_comparison: Dict[str, Any]
    
    per_document_results: Dict[str, Any]
    limitations: List[str]
    recommended_next_steps: List[str]
    conclusion: str
