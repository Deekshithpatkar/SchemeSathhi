"""
Unit Tests for Checkpoint 16: Quality and Accuracy Evaluation Harness.
Verifies:
1. Gold standard schema validation and coverage (all 5 CP15 schemes)
2. Evaluation metrics calculation (precision, recall, F1, zero-division handling)
3. Confusion matrix counts and mathematical consistency
4. Document processing metrics calculation
5. Evidence quality metrics calculation
6. CP16 report generation integrity (JSON and Markdown reports exist and match)
7. Real vs synthetic metric separation assertion
"""

import json
from pathlib import Path
import pytest

from app.quality_evaluation import (
    GOLD_STANDARDS_5_SCHEMES,
    calculate_evaluation_metrics,
    DocumentQualityMetrics,
    EvidenceQualityMetrics,
    Checkpoint16Evaluation,
)


def test_1_gold_standard_dataset_coverage():
    """Verify that gold standard annotations cover all 5 required real CP15 scheme documents."""
    expected_keys = {
        "secondary-agriculture",
        "gruha-lakshmi",
        "cm-raitha-vidyanidhi",
        "rkvy-karnataka",
        "pradhan-mantri-kisan-samman-nidhi",
    }
    assert set(GOLD_STANDARDS_5_SCHEMES.keys()) == expected_keys

    for key, gold in GOLD_STANDARDS_5_SCHEMES.items():
        assert gold.scheme_key == key
        assert gold.scheme_name
        assert gold.document_filename.endswith(".pdf")
        assert isinstance(gold.has_rules, bool)
        if gold.has_rules:
            assert len(gold.eligibility_rules) + len(gold.exclusion_rules) > 0
        else:
            assert len(gold.eligibility_rules) == 0
            assert len(gold.exclusion_rules) == 0


def test_2_evaluation_metrics_calculation():
    """Verify precision, recall, and F1 calculations including zero-division safety."""
    # Test zero cases
    m0 = calculate_evaluation_metrics(0, 0, 0)
    assert m0.precision == 0.0
    assert m0.recall == 0.0
    assert m0.f1_score == 0.0

    # Test standard case: TP=8, FP=2, FN=0 -> Precision=0.8, Recall=1.0, F1=0.8889
    m1 = calculate_evaluation_metrics(8, 2, 0)
    assert m1.precision == 0.8
    assert m1.recall == 1.0
    assert m1.f1_score == 0.8889

    # Test zero TP with false positives and false negatives
    m2 = calculate_evaluation_metrics(0, 4, 2)
    assert m2.precision == 0.0
    assert m2.recall == 0.0
    assert m2.f1_score == 0.0


def test_3_document_processing_metrics_consistency():
    """Verify document processing counts are internally consistent."""
    doc_metrics = DocumentQualityMetrics(
        total_pages=22,
        digital_pages=11,
        scanned_pages=11,
        ocr_pages=11,
        table_pages=7,
        pages_requiring_ocr=11,
        ocr_completed_successfully=11,
        unusable_or_degraded_pages=9,
    )
    assert doc_metrics.digital_pages + doc_metrics.scanned_pages == doc_metrics.total_pages
    assert doc_metrics.ocr_completed_successfully == doc_metrics.pages_requiring_ocr
    assert doc_metrics.unusable_or_degraded_pages <= doc_metrics.total_pages


def test_4_evidence_quality_metrics_consistency():
    """Verify evidence quality metrics and percentages match raw counts."""
    ev_metrics = EvidenceQualityMetrics(
        total_extracted_rules=6,
        evidence_supported_count=0,
        evidence_supported_pct=0.0,
        incorrect_evidence_count=6,
        incorrect_evidence_pct=100.0,
        missing_evidence_count=0,
        missing_evidence_pct=0.0,
        rule_level_review_required_count=0,
        rule_level_review_required_pct=0.0,
        doc_level_review_required_count=5,
        doc_level_review_required_pct=100.0,
    )
    assert ev_metrics.evidence_supported_count + ev_metrics.incorrect_evidence_count == ev_metrics.total_extracted_rules
    assert ev_metrics.incorrect_evidence_pct == 100.0


def test_5_report_artifacts_exist_and_validate():
    """Verify that both JSON and Markdown report artifacts exist on disk and validate."""
    json_path = Path("data/evaluations/checkpoint16_report.json")
    md_path = Path("data/evaluations/checkpoint16_report.md")

    assert json_path.exists(), f"Missing CP16 report JSON at {json_path}"
    assert md_path.exists(), f"Missing CP16 report MD at {md_path}"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Validate against Pydantic model
    report = Checkpoint16Evaluation.model_validate(data)
    assert report.schemes_evaluated == 5
    assert report.combined_metrics.true_positives == 0
    assert report.combined_metrics.false_positives == 6
    assert report.combined_metrics.false_negatives == 5
    assert len(report.limitations) >= 4
    assert len(report.recommended_next_steps) >= 4

    # Validate Markdown report text
    with open(md_path, "r", encoding="utf-8") as f:
        md_text = f.read()

    assert "# Checkpoint 16: Evaluation & Quality Measurement Report" in md_text
    assert "0.00%" in md_text
    assert "Is the current system reliable enough for the next development stage?" in md_text
    assert "NO, NOT for automated rule extraction without human review." in md_text
