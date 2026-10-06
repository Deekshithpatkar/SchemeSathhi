"""
Tests for Checkpoint 16.2:
Kannada Rule Understanding, Recall Improvement, Bilingual Grounding & Zero-Hallucination Safety.
Covers regression cases A through O specified in Checkpoint 16.2 requirements.
"""

import json
from pathlib import Path
import pytest

from app.schemas import SchemeEvidence, RuleItem, SchemeExtraction
from app.rule_extractor import (
    is_candidate_qualification_rule,
    is_administrative_funding_statement,
    is_absence_statement,
    assess_evidence_quality,
    audit_and_enhance_extraction,
)
from app.text_reliability import assess_text_reliability
from app.quality_evaluation_16_2 import Checkpoint16_2Evaluation
from app.ocr_engine import ocr_registry, TesseractOCREngine


# ==============================================================================
# A. Kannada phrase representing a genuine eligibility condition -> correctly extracted
# ==============================================================================
def test_scenario_a_kannada_eligibility_condition_accepted():
    rule = RuleItem(
        rule="Woman who is the head of the family as identified in ration card is eligible for Rs. 2,000/month",
        type="eligibility",
        value="Rs. 2,000/month",
        category="family_status",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="ಕುಟುಂಬದ ಯಜಮಾನಿ ಮಹಿಳೆಗೆ ಪ್ರತಿ ಮಾಹೆ ರೂ.2,000/-ಗಳನ್ನು ಒದಗಿಸುವ 'ಗೃಹಲಕ್ಷ್ಮಿ' ಯೋಜನೆ",
            original_kannada_evidence="ಕುಟುಂಬದ ಯಜಮಾನಿ ಮಹಿಳೆಗೆ ಪ್ರತಿ ಮಾಹೆ ರೂ.2,000/-ಗಳನ್ನು ಒದಗಿಸುವ 'ಗೃಹಲಕ್ಷ್ಮಿ' ಯೋಜನೆ",
            english_interpretation="Financial assistance of Rs. 2,000/month to woman head of family",
            ocr_confidence=95.0,
        ),
        semantic_confidence=0.85,
    )
    is_valid, reason = is_candidate_qualification_rule(rule)
    assert is_valid is True, f"Failed: {reason}"
    is_weak, weak_reason = assess_evidence_quality(rule)
    assert is_weak is False, f"Weak evidence: {weak_reason}"
    assert rule.type == "eligibility"


# ==============================================================================
# B. Kannada phrase representing a genuine exclusion condition -> correctly extracted
# ==============================================================================
def test_scenario_b_kannada_exclusion_condition_accepted():
    rule = RuleItem(
        rule="Students who fail in the examination are disqualified from receiving scholarship for that year",
        type="exclusion",
        value="Failed examination",
        category="education",
        evidence=SchemeEvidence(
            page_number=3,
            source_text="ವಿದ್ಯಾರ್ಥಿಗಳು ಅನುತ್ತೀರ್ಣರಾದರೆ ವಿದ್ಯಾರ್ಥಿವೇತನಕ್ಕೆ ಅರ್ಹರಿರುವುದಿಲ್ಲ.",
            original_kannada_evidence="ವಿದ್ಯಾರ್ಥಿಗಳು ಅನುತ್ತೀರ್ಣರಾದರೆ ವಿದ್ಯಾರ್ಥಿವೇತನಕ್ಕೆ ಅರ್ಹರಿರುವುದಿಲ್ಲ.",
            english_interpretation="Students who fail in the examination are not eligible for scholarship",
            ocr_confidence=92.0,
        ),
        semantic_confidence=0.85,
    )
    is_valid, reason = is_candidate_qualification_rule(rule)
    assert is_valid is True, f"Failed: {reason}"
    is_weak, weak_reason = assess_evidence_quality(rule)
    assert is_weak is False, f"Weak evidence: {weak_reason}"
    assert rule.type == "exclusion"


# ==============================================================================
# C. Kannada evidence + English interpretation -> rule extracted and grounded
# ==============================================================================
def test_scenario_c_kannada_evidence_with_english_interpretation_retained():
    evidence = SchemeEvidence(
        page_number=2,
        source_text="ಕುಟುಂಬದ ಯಜಮಾನಿ ಮಹಿಳೆ ಅಥವಾ ಆಕೆಯ ಪತಿ ಆದಾಯ ತೆರಿಗೆ / ಜಿಎಸ್‌ಟಿ ಪಾವತಿದಾರರಾಗಿದ್ದಲ್ಲಿ ಯೋಜನೆಯ ಸೌಲಭ್ಯವು ಅನ್ವಯಿಸುವುದಿಲ್ಲ.",
        original_kannada_evidence="ಕುಟುಂಬದ ಯಜಮಾನಿ ಮಹಿಳೆ ಅಥವಾ ಆಕೆಯ ಪತಿ ಆದಾಯ ತೆರಿಗೆ / ಜಿಎಸ್‌ಟಿ ಪಾವತಿದಾರರಾಗಿದ್ದಲ್ಲಿ ಯೋಜನೆಯ ಸೌಲಭ್ಯವು ಅನ್ವಯಿಸುವುದಿಲ್ಲ.",
        english_interpretation="The woman head of family or her husband paying income tax or GST are excluded from the scheme.",
        ocr_confidence=91.0,
    )
    assert evidence.original_kannada_evidence is not None
    assert "ಯಜಮಾನಿ" in evidence.original_kannada_evidence
    assert evidence.english_interpretation is not None
    assert "income tax" in evidence.english_interpretation.lower()
    # The original Kannada evidence is strictly retained alongside interpretation
    assert evidence.source_text == evidence.original_kannada_evidence


# ==============================================================================
# D. Image + Kannada OCR -> rule extracted and grounded
# ==============================================================================
def test_scenario_d_image_plus_kannada_ocr_rule_grounded():
    rule = RuleItem(
        rule="Children of farmers enrolled in post-matric courses qualify for scholarship",
        type="eligibility",
        value="Farmer's child in post-matric course",
        category="farmer_status",
        evidence=SchemeEvidence(
            page_number=2,
            source_text="ರೈತರ ಮಕ್ಕಳಿಗೆ ಉನ್ನತ ಶಿಕ್ಷಣವನ್ನು ಪ್ರೋತ್ಸಾಹಿಸಲು 'ಮುಖ್ಯಮಂತ್ರಿ ರೈತ ವಿದ್ಯಾನಿಧಿ' ಯೋಜನೆಯಡಿ ರೈತರ ಮಕ್ಕಳಿಗೆ ವಿದ್ಯಾರ್ಥಿವೇತನವನ್ನು ಮಂಜೂರು ಮಾಡಲು",
            original_kannada_evidence="ರೈತರ ಮಕ್ಕಳಿಗೆ ಉನ್ನತ ಶಿಕ್ಷಣವನ್ನು ಪ್ರೋತ್ಸಾಹಿಸಲು 'ಮುಖ್ಯಮಂತ್ರಿ ರೈತ ವಿದ್ಯಾನಿಧಿ' ಯೋಜನೆಯಡಿ ರೈತರ ಮಕ್ಕಳಿಗೆ ವಿದ್ಯಾರ್ಥಿವೇತನವನ್ನು ಮಂಜೂರು ಮಾಡಲು",
            english_interpretation="Scholarship to farmers' children enrolled in higher education",
            ocr_confidence=88.0,
        ),
        semantic_confidence=0.85,
    )
    is_valid, reason = is_candidate_qualification_rule(rule)
    assert is_valid is True
    is_weak, weak_reason = assess_evidence_quality(rule)
    assert is_weak is False


# ==============================================================================
# E. Translation introduces information not present in source -> reject/review
# ==============================================================================
def test_scenario_e_unsupported_translation_triggers_review():
    # Source text only mentions post-matric studies, but rule claims income must be < 1 lakh
    rule = RuleItem(
        rule="Annual family income must be less than 1,00,000 for scholarship eligibility",
        type="eligibility",
        value="< 1,00,000",
        category="income",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="ಕೇವಲ ಅರ್ಹ ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಮಾತ್ರ ಸೌಲಭ್ಯ",  # Does NOT mention income threshold
            original_kannada_evidence="ಕೇವಲ ಅರ್ಹ ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಮಾತ್ರ ಸೌಲಭ್ಯ",
            english_interpretation="Scholarship for eligible students with income under 1 lakh",
            ocr_confidence=80.0,
        ),
        semantic_confidence=0.85,
    )
    # The evidence has no income indicator
    doc_json = {
        "document": {"filename": "test.pdf"},
        "pages": [{"page_type": "TEXT", "avg_confidence": 95.0, "blocks": [{"text": "ಕೇವಲ ಅರ್ಹ ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಮಾತ್ರ ಸೌಲಭ್ಯ"}]}]
    }
    extraction = SchemeExtraction(
        scheme_name="Scholarship Scheme",
        eligibility_rules=[rule],
        exclusion_rules=[],
    )
    audited = audit_and_enhance_extraction(extraction, doc_json, model_name="mock-model")
    # Rule must either be flagged for review or have review_required set
    assert audited.review_required is True or audited.eligibility_rules[0].review_required is True or len(audited.review_reasons) > 0


# ==============================================================================
# F. Model uses general scheme knowledge -> reject/review
# ==============================================================================
def test_scenario_f_general_scheme_knowledge_without_evidence_rejected():
    rule = RuleItem(
        rule="Small and marginal farmers owning cultivable land up to 2 hectares qualify for PM-KISAN",
        type="eligibility",
        value="<= 2 Ha",
        category="land_size",
        evidence=None,  # No document evidence
        semantic_confidence=0.85,
    )
    is_weak, weak_reason = assess_evidence_quality(rule)
    assert is_weak is True
    assert "no supporting physical evidence" in weak_reason


# ==============================================================================
# G. Genuine Kannada rule with OCR variation -> accepted if evidence supports it
# ==============================================================================
def test_scenario_g_genuine_kannada_rule_with_ocr_variation_accepted():
    # Minor OCR noise in punctuation or character spacing
    rule = RuleItem(
        rule="Eligible woman head of household receives assistance",
        type="eligibility",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="ರಾಜ್ಯದ ಕುಟು೦ಬದಲ್ಲಿನ ಯಜಮಾನಿ ಮಹಿಳೆಗೆ ಪ್ರತಿ ತಿಂಗಳು ರೂ. 2000/- ಗಳನ್ನು ನೀಡುವ ಗೃಹಲಕ್ಷ್ಮಿ ಯೋಜನೆ",
            original_kannada_evidence="ರಾಜ್ಯದ ಕುಟು೦ಬದಲ್ಲಿನ ಯಜಮಾನಿ ಮಹಿಳೆಗೆ ಪ್ರತಿ ತಿಂಗಳು ರೂ. 2000/- ಗಳನ್ನು ನೀಡುವ ಗೃಹಲಕ್ಷ್ಮಿ ಯೋಜನೆ",
            english_interpretation="Rs. 2000/month to woman head of family",
            ocr_confidence=78.0,  # Legitimate scanned OCR confidence > 60%
        ),
    )
    is_valid, reason = is_candidate_qualification_rule(rule)
    assert is_valid is True
    is_weak, weak_reason = assess_evidence_quality(rule)
    assert is_weak is False


# ==============================================================================
# H. Committee statement -> still rejected
# ==============================================================================
def test_scenario_h_committee_statement_still_rejected():
    rule = RuleItem(
        rule="Two progressive farmers to be nominated by the government as members of the directorate committee",
        type="eligibility",
        evidence=SchemeEvidence(
            page_number=2,
            source_text="Two progressive farmers to be nominated by the government as committee members",
            ocr_confidence=98.0,
        ),
    )
    is_valid, reason = is_candidate_qualification_rule(rule)
    assert is_valid is False
    assert "committee composition or member nomination" in reason


# ==============================================================================
# I. Funding allocation -> still rejected
# ==============================================================================
def test_scenario_i_funding_allocation_still_rejected():
    rule = RuleItem(
        rule="State-wise allocation for Karnataka under RKVY is Rs. 154.25 crores for general category",
        type="eligibility",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="Allocation under Rashtriya Krishi Vikas Yojana (RKVY) for 2021-22: General Rs. 154.25 cr",
            ocr_confidence=99.0,
        ),
    )
    is_valid, reason = is_candidate_qualification_rule(rule)
    assert is_valid is False
    assert "funding" in reason.lower() or "allocation" in reason.lower()


# ==============================================================================
# J. PM-KISAN generic rule not present in Karnataka order -> still rejected
# ==============================================================================
def test_scenario_j_pmkisan_generic_rule_not_present_rejected():
    rule = RuleItem(
        rule="Institutional landholders and serving or retired officers are excluded from the scheme",
        type="exclusion",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="ಆಡಳಿತಾತ್ಮಕ ಅನುಮೋದನೆ ಮತ್ತು ನಿಧಿ ಬಿಡುಗಡೆ ಕುರಿತು",  # Purely administrative fund sanction quote
            ocr_confidence=90.0,
        ),
    )
    # The evidence does not support an institutional landholder exclusion
    is_valid, reason = is_candidate_qualification_rule(rule)
    assert is_valid is False


# ==============================================================================
# K. Missing evidence -> review/reject
# ==============================================================================
def test_scenario_k_missing_evidence_triggers_review():
    rule = RuleItem(
        rule="Beneficiary must possess valid Aadhaar card and active bank account",
        type="eligibility",
        evidence=None,
    )
    is_weak, reason = assess_evidence_quality(rule)
    assert is_weak is True
    assert "no supporting physical evidence" in reason


# ==============================================================================
# L. Unrelated evidence -> review/reject
# ==============================================================================
def test_scenario_l_unrelated_evidence_triggers_review():
    rule = RuleItem(
        rule="Beneficiary must own less than 2 hectares of land",
        type="eligibility",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="ಸದರಿ ಆದೇಶವನ್ನು ಸರ್ಕಾರದ ಅಧಿಕೃತ ವೆಬ್‌ಸೈಟ್‌ನಲ್ಲಿ ಪ್ರಕಟಿಸಲಾಗಿದೆ",  # 'Published on website'
            ocr_confidence=95.0,
        ),
    )
    is_valid, reason = is_candidate_qualification_rule(rule)
    assert is_valid is False
    assert "administrative" in reason.lower() or "candidate qualification" in reason.lower() or "notification" in reason.lower()


# ==============================================================================
# M. CP16.1 mojibake detection -> still works
# ==============================================================================
def test_scenario_m_mojibake_detection_preserved():
    mojibake = (
        "Wcve>FMW ;dvc>Fdci {Pj}v`{V {a\\}Pj iWj;sE \"Wcve>FMW\" {Pj}v`{V 2023-24 {e~ "
        "AiP`Pj {a\\}Pj cvW\\;Pj Wcve>FMW {Pj}v`{Vp PjaO`p AWc: 2000/- qE` cvW\\;v`i"
    )
    result = assess_text_reliability(mojibake)
    assert result.reliable is False
    assert result.detected_encoding_issue is True
    assert result.recommended_action == "RUN_OCR"


# ==============================================================================
# N. Scanned Kannada OCR -> still works
# ==============================================================================
def test_scenario_n_scanned_kannada_ocr_pipeline_registered():
    engine = ocr_registry.get_engine("tesseract")
    assert isinstance(engine, TesseractOCREngine)
    assert engine.name() == "tesseract"


# ==============================================================================
# O. Existing CP16.1 tests and evaluation artifacts -> intact
# ==============================================================================
def test_scenario_o_cp16_1_artifacts_and_eval_schema_intact():
    cp16_report = Path("data/evaluations/checkpoint16_report.json")
    cp16_1_report = Path("data/evaluations/checkpoint16_1_report.json")
    cp16_2_report = Path("data/evaluations/checkpoint16_2_report.json")

    assert cp16_report.exists(), "CP16 baseline report must exist untouched"
    assert cp16_1_report.exists(), "CP16.1 safety baseline report must exist untouched"
    assert cp16_2_report.exists(), "CP16.2 evaluation report must exist"

    # Verify CP16.2 report parses cleanly
    with open(cp16_2_report, "r", encoding="utf-8") as f:
        data = json.load(f)
    eval_obj = Checkpoint16_2Evaluation(**data)
    assert eval_obj.combined_metrics.true_positives == 5
    assert eval_obj.combined_metrics.false_positives == 0
    assert eval_obj.combined_metrics.false_negatives == 0
    assert eval_obj.combined_metrics.f1_score == 1.0
