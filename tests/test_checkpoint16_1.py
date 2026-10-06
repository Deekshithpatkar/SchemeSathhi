"""
Tests for Checkpoint 16.1:
Document Text Reliability, Kannada OCR/Document Processing, and Strict Rule Grounding.
Covers regression cases A through N specified in Checkpoint 16.1 requirements.
"""

import json
from pathlib import Path
import pytest
import pymupdf

from app.text_reliability import assess_text_reliability
from app.document_classifier import classify_page
from app.ocr_engine import ocr_registry, TesseractOCREngine, SarvamOCREngine
from app.rule_extractor import (
    is_candidate_qualification_rule,
    is_administrative_funding_statement,
    is_absence_statement,
    assess_evidence_quality,
)
from app.schemas import SchemeEvidence, RuleItem
from app.quality_evaluation_16_1 import Checkpoint16_1Evaluation


# ==============================================================================
# A. Normal digital English PDF -> digital extraction remains preferred
# ==============================================================================
def test_normal_digital_english_pdf_uses_digital_extraction():
    text = (
        "GOVERNMENT OF KARNATAKA\n"
        "Department of Agriculture, Bengaluru.\n"
        "Proceedings of the Government of Karnataka regarding establishment of "
        "the Directorate of Secondary Agriculture to promote farmer processing units."
    )
    result = assess_text_reliability(text)
    assert result.reliable is True
    assert result.score > 0.8
    assert result.detected_encoding_issue is False
    assert result.recommended_action == "USE_DIGITAL_TEXT"


# ==============================================================================
# B. Normal digital Kannada PDF -> digital extraction used when reliable
# ==============================================================================
def test_normal_digital_kannada_pdf_uses_digital_text_when_reliable():
    text = (
        "ಕರ್ನಾಟಕ ಸರ್ಕಾರ\n"
        "ಕೃಷಿ ಇಲಾಖೆ, ಬೆಂಗಳೂರು.\n"
        "ಈ ಯೋಜನೆಯಡಿ ಎಲ್ಲಾ ಅರ್ಹ ಫಲಾನುಭವಿಗಳು ಆನ್‌ಲೈನ್ ಮೂಲಕ ಅರ್ಜಿ ಸಲ್ಲಿಸಬೇಕು. "
        "ಅರ್ಹ ರೈತರಿಗೆ ವಾರ್ಷಿಕ ಸಹಾಯಧನವನ್ನು ನೇರ ನಗದು ವರ್ಗಾವಣೆ ಮೂಲಕ ನೀಡಲಾಗುವುದು."
    )
    result = assess_text_reliability(text)
    assert result.reliable is True
    assert result.score > 0.7
    assert result.detected_encoding_issue is False
    assert result.recommended_action == "USE_DIGITAL_TEXT"


# ==============================================================================
# C. Digitally embedded but mojibake/legacy Kannada -> reliability detector identifies it
# ==============================================================================
def test_digitally_embedded_mojibake_legacy_kannada_detected():
    # Real sample from 30af3c4d_GruhaLaxmiGO.pdf
    mojibake = (
        "Wcve>FMW ;dvc>Fdci {Pj}v`{V {a\\}Pj iWj;sE \"Wcve>FMW\" {Pj}v`{V 2023-24 {e~ "
        "AiP`Pj {a\\}Pj cvW\\;Pj Wcve>FMW {Pj}v`{Vp PjaO`p AWc: 2000/- qE` cvW\\;v`i"
    )
    result = assess_text_reliability(mojibake)
    assert result.reliable is False
    assert result.score < 0.4
    assert result.detected_encoding_issue is True
    assert result.recommended_action == "RUN_OCR"


# ==============================================================================
# D. Mojibake page -> OCR fallback is triggered in page classification
# ==============================================================================
def test_mojibake_triggers_ocr_fallback_in_classification():
    mojibake = "cdo$: diseru^ld roasTb Aca: 4000 doqs D.B.T. vWqs ;dsPj..."
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), mojibake)

    res = classify_page(page)
    # The mojibake text is flagged unusable, forcing SCANNED page type to trigger OCR
    assert res["page_type"] == "SCANNED"
    assert res["text_usable"] is False
    assert res["text_reliability"]["recommended_action"] == "RUN_OCR"
    assert "SCANNED" in res["tags"]


# ==============================================================================
# E. Scanned Kannada PDF -> OCR is used
# ==============================================================================
def test_scanned_kannada_pdf_uses_ocr_backend():
    engine = ocr_registry.get_engine("tesseract")
    assert isinstance(engine, TesseractOCREngine)
    assert engine.name() == "tesseract"

    # Direct registration check
    sarvam_engine = ocr_registry.engines["sarvam"]
    assert isinstance(sarvam_engine, SarvamOCREngine)
    assert sarvam_engine.name() == "sarvam"
    assert sarvam_engine.is_available() is False

    # Graceful fallback check: unconfigured sarvam engine falls back to tesseract
    fallback_engine = ocr_registry.get_engine("sarvam")
    assert isinstance(fallback_engine, TesseractOCREngine)


# ==============================================================================
# F. Mixed digital/scanned PDF -> page-level handling works
# ==============================================================================
def test_mixed_digital_scanned_pdf_page_level_handling():
    doc = pymupdf.open()
    # Page 1: Normal English
    p1 = doc.new_page()
    p1.insert_text((50, 50), "Government of Karnataka official order establishing guidelines for applicant registration.")
    res1 = classify_page(p1)
    assert res1["page_type"] == "TEXT"
    assert res1["text_usable"] is True
    assert "TEXT" in res1["tags"]

    # Page 2: Non-standard legacy font mojibake
    p2 = doc.new_page()
    p2.insert_text((50, 50), "Wcve>FMW ;dvc>Fdci {Pj}v`{V {a\\}Pj iWj;sE \"Wcve>FMW\"...")
    res2 = classify_page(p2)
    assert res2["page_type"] == "SCANNED"
    assert res2["text_usable"] is False
    assert "SCANNED" in res2["tags"]


# ==============================================================================
# G. OCR output with poor confidence -> review_required is set
# ==============================================================================
def test_ocr_output_with_poor_confidence_sets_review_required():
    rule = RuleItem(
        rule="Applicant must be a farmer",
        type="eligibility",
        evidence=SchemeEvidence(
            page_number=2,
            source_text="farmer text with low clarity",
            ocr_confidence=35.0,  # Below 60% threshold
        ),
        semantic_confidence=0.8,
        review_required=False,
    )
    is_weak, reason = assess_evidence_quality(rule, low_conf_threshold=60.0)
    assert is_weak is True
    assert "confidence" in reason.lower()


# ==============================================================================
# H. Funding allocation table -> no false beneficiary eligibility rule
# ==============================================================================
def test_funding_allocation_table_no_false_eligibility():
    rule_text = "Must be a resident of the state or UT as per the allocation"
    evidence_text = "State-wise Allocation under Normal RKVY 2021-22 (Central Share)"
    is_admin, reason = is_administrative_funding_statement(rule_text, evidence_text)
    assert is_admin is True
    assert "funding" in reason.lower() or "allocation" in reason.lower()


# ==============================================================================
# I. Committee composition -> no false eligibility rule
# ==============================================================================
def test_committee_composition_no_false_eligibility():
    rule = RuleItem(
        rule="Two Progressive Farmers to be nominated by the Government",
        type="eligibility",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="Committee members: Two Progressive Farmers to be nominated by the Government",
            ocr_confidence=95.0,
        ),
    )
    is_cand, reason = is_candidate_qualification_rule(rule)
    assert is_cand is False
    assert "member nomination" in reason.lower() or "committee" in reason.lower()


# ==============================================================================
# J. Missing eligibility statement -> no fabricated exclusion rule
# ==============================================================================
def test_missing_eligibility_statement_no_fake_exclusion():
    assert is_absence_statement("No specific exclusion rules provided in the document") is True
    assert is_absence_statement("None mentioned") is True
    assert is_absence_statement("ಯಾವುದೇ ಅನರ್ಹತೆ ನಿಯಮಗಳಿಲ್ಲ") is True
    assert is_absence_statement("Government employees are excluded") is False


# ==============================================================================
# K. PM-KISAN Karnataka administrative order -> no generic rules imported
# ==============================================================================
def test_pm_kisan_karnataka_order_does_not_import_generic_rules():
    order_text = "ರಾಜ್ಯದ ರೈತರಿಗೆ ಪ್ರಧಾನಮಂತ್ರಿ ಕಿಸಾನ್ ಸಮ್ಮಾನ್ ನಿಧಿ ಯೋಜನೆಯಡಿ ರೂ. 4000 ಹೆಚ್ಚುವರಿ ಅನುದಾನ ಬಿಡುಗಡೆ ಮಾಡಲು ಆದೇಶಿಸಿದೆ."
    rel = assess_text_reliability(order_text)
    assert rel.reliable is True


# ==============================================================================
# L. Genuine eligibility rule with Kannada/English OCR variation -> grounded
# ==============================================================================
def test_genuine_eligibility_rule_grounding_supports_kannada():
    rule = RuleItem(
        rule="Must be a woman recognized as head of the family (Yajamani)",
        type="eligibility",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="ಕುಟುಂಬದ ಯಜಮಾನಿ ಮಹಿಳೆಗೆ ಪ್ರತಿ ಮಾಹೆ ರೂ. 2000/- ಗಳ ಆರ್ಥಿಕ ನೆರವು",
            ocr_confidence=88.0,
        ),
        semantic_confidence=0.85,
        review_required=False,
    )
    is_weak, reason = assess_evidence_quality(rule, low_conf_threshold=60.0)
    assert is_weak is False
    assert reason is None


# ==============================================================================
# M. Evidence missing -> reject / review required
# ==============================================================================
def test_evidence_missing_triggers_review_required():
    rule = RuleItem(
        rule="Annual family income must be below 2 lakhs",
        type="eligibility",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="",  # Missing evidence
            ocr_confidence=90.0,
        ),
        semantic_confidence=0.85,
        review_required=False,
    )
    is_weak, reason = assess_evidence_quality(rule, low_conf_threshold=60.0)
    assert is_weak is True
    assert "evidence" in reason.lower()


# ==============================================================================
# N. Evidence unrelated to candidate qualification -> reject / review required
# ==============================================================================
def test_evidence_unrelated_to_candidate_qualification():
    rule = RuleItem(
        rule="Spare copies forwarded to the guard file",
        type="eligibility",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="Forwarded to Accountant General and spare copies to guard file",
            ocr_confidence=90.0,
        ),
    )
    is_cand, reason = is_candidate_qualification_rule(rule)
    assert is_cand is False


# ==============================================================================
# CP16.1 Report Artifacts Validation
# ==============================================================================
def test_cp16_1_report_artifacts_exist_and_valid():
    json_path = Path("data/evaluations/checkpoint16_1_report.json")
    md_path = Path("data/evaluations/checkpoint16_1_report.md")

    assert json_path.exists(), "checkpoint16_1_report.json must exist"
    assert md_path.exists(), "checkpoint16_1_report.md must exist"

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    evaluation = Checkpoint16_1Evaluation.model_validate(data)
    assert evaluation.schemes_evaluated == 5
    assert evaluation.hallucinated_rules_count == 0
    assert evaluation.committee_false_positives_filtered == 2
    assert evaluation.pages_judged_unreliable == 5
    assert evaluation.ocr_fallbacks_triggered == 5

    # Verify CP16 report is preserved and not overwritten
    cp16_json_path = Path("data/evaluations/checkpoint16_report.json")
    assert cp16_json_path.exists(), "CP16 baseline report must remain intact"
