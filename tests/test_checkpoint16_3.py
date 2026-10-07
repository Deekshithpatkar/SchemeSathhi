"""
Tests for Checkpoint 16.3:
Rule Semantic Validation & Evidence Consistency.

Covers all 16 focused validation and regression requirements:
1. CM Raitha landowner/landless contradiction.
2. Gruha Lakshmi household-limit classification.
3. Gruha Lakshmi GST/taxpayer scope generalization.
4. Eligibility polarity inversion.
5. Exclusion polarity inversion.
6. Numeric threshold mismatch.
7. AND/OR mismatch.
8. Subject mismatch.
9. Unsupported English claim.
10. Garbled Kannada evidence.
11. Secondary Agriculture true negative.
12. RKVY funding-table true negative.
13. PM-KISAN external-knowledge rejection.
14. Valid Gruha Lakshmi woman-head rule.
15. Valid CM Raitha failed/repeating-student exclusion.
16. Valid CM Raitha higher-education exclusion.
"""

import json
from pathlib import Path
import pytest

from app.schemas import RuleItem, SchemeEvidence, SchemeExtraction
from app.semantic_validator import (
    validate_semantic_evidence_consistency,
    audit_rule_semantic_consistency,
    classify_rule_scope,
)


EXTRACTED_RULES_DIR = Path("data/extracted_rules")


# ==============================================================================
# 1. CM Raitha landowner/landless contradiction
# ==============================================================================
def test_01_cm_raitha_landowner_vs_landless_contradiction():
    """
    Mandatory regression: English rule claims 'landless farmers' but Kannada
    evidence specifies 'ಜಮೀನಿನ ಒಡೆಯರಾಗಿದ್ದರೆ' (agricultural land owners).
    Must detect CONTRADICTED and quarantine with review_required=True.
    """
    ev = SchemeEvidence(
        page_number=3,
        source_text="೫ ರೈತರ ಮಕ್ಕಳ ತಂದೆ-ತಾಯಿ ಇಬ್ಬರೂ ಕಷಿ ಜಮೀನಿನ `ಒಡೆಯರಾಗಿದ್ದರೆ, ' = ಗ . ಯೋಜನೆಯಲ್ಲಿ ಒಂದು ಶಿಷ್ಯವೇತನಕ್ಕೆ ಮಾತ್ರ ರೈತರ ಮಕ್ಕಳು ಅರ್ಹರಾಗಿರುತ್ತಾ ರ.",
        original_kannada_evidence="೫ ರೈತರ ಮಕ್ಕಳ ತಂದೆ-ತಾಯಿ ಇಬ್ಬರೂ ಕಷಿ ಜಮೀನಿನ `ಒಡೆಯರಾಗಿದ್ದರೆ, ' = ಗ . ಯೋಜನೆಯಲ್ಲಿ ಒಂದು ಶಿಷ್ಯವೇತನಕ್ಕೆ ಮಾತ್ರ ರೈತರ ಮಕ್ಕಳು ಅರ್ಹರಾಗಿರುತ್ತಾ ರ.",
        english_interpretation="Farmers' children are eligible for the scholarship if both their parents are landless farmers.",
    )
    rule = RuleItem(
        rule="Farmers' children are eligible for the scholarship if both their parents are landless farmers.",
        type="eligibility",
        evidence=ev,
    )

    audited = audit_rule_semantic_consistency(rule)

    assert audited.evidence_consistency_status == "CONTRADICTED"
    assert audited.review_required is True
    assert "Semantic Inversion detected" in audited.semantic_validation_reason
    assert "landless" in audited.semantic_validation_reason
    assert "ಜಮೀನಿನ ಒಡೆಯ" in audited.semantic_validation_reason


# ==============================================================================
# 2. Gruha Lakshmi household-limit classification
# ==============================================================================
def test_02_gruha_lakshmi_household_limit_classification():
    """
    Gruha Lakshmi 'Only one woman per household is eligible' is a household/beneficiary limit,
    not an individual candidate qualification predicate.
    """
    ev = SchemeEvidence(
        page_number=2,
        source_text="ಒಂದೇ ಕುಟುಂಬದಲ್ಲಿ ಒಂದಕ್ಕಿಂತ ಹೆಚ್ಚು ಮಹಿಳೆಯರಿದ್ದಲ್ಲಿ, ಒಂದು ಮಹಿಳೆಗೆ ಮಾತ್ರ ಯೋಜನೆ ಅನ್ವಯಿಸತಕ್ಕದ್ದು",
        original_kannada_evidence="ಒಂದೇ ಕುಟುಂಬದಲ್ಲಿ ಒಂದಕ್ಕಿಂತ ಹೆಚ್ಚು ಮಹಿಳೆಯರಿದ್ದಲ್ಲಿ, ಒಂದು ಮಹಿಳೆಗೆ ಮಾತ್ರ ಯೋಜನೆ ಅನ್ವಯಿಸತಕ್ಕದ್ದು",
        english_interpretation="Only one woman per household is eligible for the scheme.",
    )
    rule = RuleItem(
        rule="Only one woman per household is eligible for the scheme.",
        type="eligibility",
        evidence=ev,
    )

    audited = audit_rule_semantic_consistency(rule)

    assert audited.rule_scope == "beneficiary_limit"
    # Classified as beneficiary_limit constraint rather than individual candidate predicate
    assert any("limit" in r.lower() for r in audited.review_reasons)


# ==============================================================================
# 3. Gruha Lakshmi GST/taxpayer scope generalization
# ==============================================================================
def test_03_gruha_lakshmi_gst_taxpayer_scope():
    """
    English interpretation states general 'taxpayers' but Kannada evidence specifically
    cites GST return filers ('ಜಿಎಸ್‌ಟಿ ರಿಟರ್ನ್ಸ್‌ ಸಲ್ಲಿಸುವವರಾಗಿದ್ದಲ್ಲಿ').
    Must flag as REVIEW_REQUIRED to prevent over-broadening.
    """
    ev = SchemeEvidence(
        page_number=2,
        source_text="ಕುಟುಂಬದ ಯಜಮಾನಿ ಅಥವಾ ಯಜಮಾನಿಯ ಪತಿ. ಜಿಎಸ್‌ಟಿ ರಿಟರ್ನ್ಸ್‌ - ಸಲ್ಲಿಸುವವರಾಗಿದ್ದಲ್ಲಿ",
        original_kannada_evidence="ಕುಟುಂಬದ ಯಜಮಾನಿ ಅಥವಾ ಯಜಮಾನಿಯ ಪತಿ. ಜಿಎಸ್‌ಟಿ ರಿಟರ್ನ್ಸ್‌ - ಸಲ್ಲಿಸುವವರಾಗಿದ್ದಲ್ಲಿ",
        english_interpretation="Individuals who are taxpayers (tax payers) are disqualified from availing the scheme.",
    )
    rule = RuleItem(
        rule="Individuals who are taxpayers (tax payers) are disqualified from availing the scheme.",
        type="exclusion",
        evidence=ev,
    )

    audited = audit_rule_semantic_consistency(rule)

    assert audited.evidence_consistency_status == "REVIEW_REQUIRED"
    assert audited.review_required is True
    assert "Scope Generalization" in audited.semantic_validation_reason


# ==============================================================================
# 4. Eligibility polarity inversion
# ==============================================================================
def test_04_eligibility_polarity_inversion():
    """
    Rule claims candidate is eligible, but evidence contains explicit disqualification term.
    Must mark CONTRADICTED.
    """
    ev = SchemeEvidence(
        page_number=1,
        source_text="ವಿದ್ಯಾರ್ಥಿಗಳು ಅನರ್ಹರಾಗಿರುತ್ತಾರೆ",
        original_kannada_evidence="ವಿದ್ಯಾರ್ಥಿಗಳು ಅನರ್ಹರಾಗಿರುತ್ತಾರೆ",
        english_interpretation="Candidate is eligible for the scholarship benefit.",
    )
    rule = RuleItem(
        rule="Candidate is eligible for the scholarship benefit.",
        type="eligibility",
        evidence=ev,
    )

    audited = audit_rule_semantic_consistency(rule)

    assert audited.evidence_consistency_status == "CONTRADICTED"
    assert audited.review_required is True
    assert "Polarity Inversion" in audited.semantic_validation_reason


# ==============================================================================
# 5. Exclusion polarity inversion
# ==============================================================================
def test_05_exclusion_polarity_inversion():
    """
    Rule claims candidate is excluded, but evidence explicitly states they are eligible.
    Must mark CONTRADICTED.
    """
    ev = SchemeEvidence(
        page_number=1,
        source_text="ಕುಟುಂಬದ ಯಜಮಾನಿ ಮಹಿಳೆಯು ಯೋಜನೆಗೆ ಪಡೆಯಲು ಅರ್ಹ ಫಲಾನುಭವಿ",
        original_kannada_evidence="ಕುಟುಂಬದ ಯಜಮಾನಿ ಮಹಿಳೆಯು ಯೋಜನೆಗೆ ಪಡೆಯಲು ಅರ್ಹ ಫಲಾನುಭವಿ",
        english_interpretation="The woman head of household is excluded from availing the scheme.",
    )
    rule = RuleItem(
        rule="The woman head of household is excluded from availing the scheme.",
        type="exclusion",
        evidence=ev,
    )

    audited = audit_rule_semantic_consistency(rule)

    assert audited.evidence_consistency_status == "CONTRADICTED"
    assert audited.review_required is True
    assert "Polarity Inversion" in audited.semantic_validation_reason


# ==============================================================================
# 6. Numeric threshold mismatch
# ==============================================================================
def test_06_numeric_threshold_mismatch():
    """
    English rule asserts Rs. 500000 income limit, but Kannada evidence specifies Rs. 200000.
    Must detect CONTRADICTED.
    """
    ev = SchemeEvidence(
        page_number=1,
        source_text="ವಾರ್ಷಿಕ ಆದಾಯ ಮಿತಿ ರೂ. 200000 ಕ್ಕಿಂತ ಹೆಚ್ಚಿರಬಾರದು",
        original_kannada_evidence="ವಾರ್ಷಿಕ ಆದಾಯ ಮಿತಿ ರೂ. 200000 ಕ್ಕಿಂತ ಹೆಚ್ಚಿರಬಾರದು",
        english_interpretation="Annual family income must not exceed Rs. 500000.",
    )
    rule = RuleItem(
        rule="Annual family income must not exceed Rs. 500000.",
        type="eligibility",
        evidence=ev,
    )

    audited = audit_rule_semantic_consistency(rule)

    assert audited.evidence_consistency_status == "CONTRADICTED"
    assert audited.review_required is True
    assert "Numeric Mismatch" in audited.semantic_validation_reason


# ==============================================================================
# 7. AND/OR mismatch
# ==============================================================================
def test_07_and_or_mismatch():
    """
    English rule asserts strict 'both' (AND) condition, but Kannada evidence specifies 'ಅಥವಾ' (OR).
    Must detect CONTRADICTED.
    """
    ev = SchemeEvidence(
        page_number=2,
        source_text="ತಂದೆ ಅಥವಾ ತಾಯಿ ಕೃಷಿ ಜಮೀನು ಹೊಂದಿರಬೇಕು",
        original_kannada_evidence="ತಂದೆ ಅಥವಾ ತಾಯಿ ಕೃಷಿ ಜಮೀನು ಹೊಂದಿರಬೇಕು",
        english_interpretation="Both father and mother must possess agriculture land.",
    )
    rule = RuleItem(
        rule="Both father and mother must possess agriculture land.",
        type="eligibility",
        evidence=ev,
    )

    audited = audit_rule_semantic_consistency(rule)

    assert audited.evidence_consistency_status == "CONTRADICTED"
    assert audited.review_required is True
    assert "Logical Mismatch" in audited.semantic_validation_reason


# ==============================================================================
# 8. Subject mismatch
# ==============================================================================
def test_08_subject_mismatch():
    """
    English rule asserts husband is eligible, but Kannada evidence specifies woman head of family only.
    Must detect CONTRADICTED.
    """
    ev = SchemeEvidence(
        page_number=1,
        source_text="ಕುಟುಂಬದ ಯಜಮಾನಿ ಮಹಿಳೆಗೆ ಮಾತ್ರ ಮಾಸಿಕ ಆರ್ಥಿಕ ನೆರವು",
        original_kannada_evidence="ಕುಟುಂಬದ ಯಜಮಾನಿ ಮಹಿಳೆಗೆ ಮಾತ್ರ ಮಾಸಿಕ ಆರ್ಥಿಕ ನೆರವು",
        english_interpretation="The husband is eligible to receive monthly financial assistance.",
    )
    rule = RuleItem(
        rule="The husband is eligible to receive monthly financial assistance.",
        type="eligibility",
        evidence=ev,
    )

    audited = audit_rule_semantic_consistency(rule)

    assert audited.evidence_consistency_status == "CONTRADICTED"
    assert audited.review_required is True
    assert "Subject Inversion" in audited.semantic_validation_reason


# ==============================================================================
# 9. Unsupported English claim
# ==============================================================================
def test_09_unsupported_english_claim():
    """
    English rule asserts concepts (e.g. student scholarship) completely absent from
    the evidence text (e.g. road construction funding).
    Must flag as REVIEW_REQUIRED.
    """
    ev = SchemeEvidence(
        page_number=1,
        source_text="ರಸ್ತೆ ನಿರ್ಮಾಣ ಕಾಮಗಾರಿ ಯೋಜನೆ ಅನುದಾನ ಬಿಡುಗಡೆ",
        original_kannada_evidence="ರಸ್ತೆ ನಿರ್ಮಾಣ ಕಾಮಗಾರಿ ಯೋಜನೆ ಅನುದಾನ ಬಿಡುಗಡೆ",
        english_interpretation="Student must receive scholarship for higher education.",
    )
    rule = RuleItem(
        rule="Student must receive scholarship for higher education.",
        type="eligibility",
        evidence=ev,
    )

    audited = audit_rule_semantic_consistency(rule)

    assert audited.evidence_consistency_status == "REVIEW_REQUIRED"
    assert audited.review_required is True
    assert "Unsupported Claim" in audited.semantic_validation_reason


# ==============================================================================
# 10. Garbled Kannada evidence
# ==============================================================================
def test_10_garbled_kannada_evidence():
    """
    Evidence text is mojibake/garbled noise.
    Must mark as REVIEW_REQUIRED or INSUFFICIENT.
    """
    ev = SchemeEvidence(
        page_number=1,
        source_text="Ã Â²Ã Â²Â¾Ã Â²Â°Ã Â³Â à²Ã Â²Â¾Ã Â³ à²¸Ã Â²Â°Ã Â²Â¬",
        original_kannada_evidence="Ã Â²Ã Â²Â¾Ã Â²Â°Ã Â³Â à²Ã Â²Â¾Ã Â³ à²¸Ã Â²Â°Ã Â²Â¬",
        english_interpretation="Students are eligible for post-matric assistance.",
    )
    rule = RuleItem(
        rule="Students are eligible for post-matric assistance.",
        type="eligibility",
        evidence=ev,
    )

    audited = audit_rule_semantic_consistency(rule)

    assert audited.evidence_consistency_status in ("REVIEW_REQUIRED", "INSUFFICIENT")
    assert audited.review_required is True


# ==============================================================================
# 11. Secondary Agriculture true negative
# ==============================================================================
def test_11_secondary_agriculture_true_negative():
    """
    Administrative directorate document must remain a True Negative (0 eligibility, 0 exclusion rules).
    """
    file_path = EXTRACTED_RULES_DIR / "02a9ac3f_SecondaryAgriculturedirectorateGO_rules.json"
    assert file_path.exists(), f"Missing extracted rules file: {file_path}"

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data.get("eligibility_rules", [])) == 0
    assert len(data.get("exclusion_rules", [])) == 0
    assert data.get("extraction_metadata", {}).get("rule_count", 0) == 0


# ==============================================================================
# 12. RKVY funding-table true negative
# ==============================================================================
def test_12_rkvy_funding_table_true_negative():
    """
    RKVY fund allocation circular must remain a True Negative (0 eligibility, 0 exclusion rules).
    Table allocations must not produce hallucinated citizen eligibility rules.
    """
    file_path = EXTRACTED_RULES_DIR / "1333e107_Allocation2021-22_rules.json"
    assert file_path.exists(), f"Missing extracted rules file: {file_path}"

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data.get("eligibility_rules", [])) == 0
    assert len(data.get("exclusion_rules", [])) == 0
    assert data.get("extraction_metadata", {}).get("rule_count", 0) == 0


# ==============================================================================
# 13. PM-KISAN external-knowledge rejection
# ==============================================================================
def test_13_pmkisan_external_knowledge_rejection():
    """
    PM-KISAN Karnataka Top-Up administrative order must not import external national rules
    (e.g. 2 hectares limit or institutional landholders) absent from this state document.
    """
    file_path = EXTRACTED_RULES_DIR / "e116e94b_PMKISANKarnatakaGO_rules.json"
    assert file_path.exists(), f"Missing extracted rules file: {file_path}"

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data.get("eligibility_rules", [])) == 0
    assert len(data.get("exclusion_rules", [])) == 0
    assert data.get("extraction_metadata", {}).get("rule_count", 0) == 0


# ==============================================================================
# 14. Valid Gruha Lakshmi woman-head rule
# ==============================================================================
def test_14_valid_gruha_lakshmi_woman_head_rule():
    """
    Genuine Gruha Lakshmi woman head condition grounded in Kannada ration card text.
    Must be SUPPORTED, candidate scope, and review_required=False.
    """
    ev = SchemeEvidence(
        page_number=1,
        source_text="ಆಹಾರ ಮತ್ತು ನಾಗರಿಕ ಸರಬರಾಜು ಇಲಾಖೆಯು ವಿತರಿಸುವ ಅಂತ್ಯೋದಯ, ಬಿಪಿಎಲ್ ಮತ್ತು ಎಪಿಎಲ್ ಪಡಿತರ ಚೀಟಿಗಳಲ್ಲಿ ಕುಟುಂಬದ ಯಜಮಾನಿ ಎಂದು ನಮೂದಿಸಿರುವ ಮಹಿಳೆಯು ಅರ್ಹ ಫಲಾನುಭವಿ",
        original_kannada_evidence="ಆಹಾರ ಮತ್ತು ನಾಗರಿಕ ಸರಬರಾಜು ಇಲಾಖೆಯು ವಿತರಿಸುವ ಅಂತ್ಯೋದಯ, ಬಿಪಿಎಲ್ ಮತ್ತು ಎಪಿಎಲ್ ಪಡಿತರ ಚೀಟಿಗಳಲ್ಲಿ ಕುಟುಂಬದ ಯಜಮಾನಿ ಎಂದು ನಮೂದಿಸಿರುವ ಮಹಿಳೆಯು ಅರ್ಹ ಫಲಾನುಭವಿ",
        english_interpretation="The woman who is listed as head of the family in the ration card is eligible.",
    )
    rule = RuleItem(
        rule="The woman who is listed as head of the family in the ration card is eligible.",
        type="eligibility",
        evidence=ev,
    )

    audited = audit_rule_semantic_consistency(rule)

    assert audited.evidence_consistency_status == "SUPPORTED"
    assert audited.rule_scope == "candidate"
    assert audited.review_required is False


# ==============================================================================
# 15. Valid CM Raitha failed/repeating-student exclusion
# ==============================================================================
def test_15_valid_cm_raitha_failed_repeating_student_exclusion():
    """
    Genuine CM Raitha Vidyanidhi student failure/repetition exclusion condition.
    Must be SUPPORTED, candidate scope, and review_required=False.
    """
    ev = SchemeEvidence(
        page_number=3,
        source_text="ಒಂದೇ ತರಗತಿಯಲ್ಲಿ ಅನುತ್ತೀರ್ಣರಾಗಿ ಅದೇ ತರಗತಿಯಲ್ಲಿ ಮುಂದುವರೆಯುವ ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಈ ಯೋಜನೆ ಅನ್ವಯಿಸುವುದಿಲ್ಲ.",
        original_kannada_evidence="ಒಂದೇ ತರಗತಿಯಲ್ಲಿ ಅನುತ್ತೀರ್ಣರಾಗಿ ಅದೇ ತರಗತಿಯಲ್ಲಿ ಮುಂದುವರೆಯುವ ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಈ ಯೋಜನೆ ಅನ್ವಯಿಸುವುದಿಲ್ಲ.",
        english_interpretation="Students who have failed a class and are continuing in the same class are not eligible.",
    )
    rule = RuleItem(
        rule="Students who have failed a class and are continuing in the same class are not eligible.",
        type="exclusion",
        evidence=ev,
    )

    audited = audit_rule_semantic_consistency(rule)

    assert audited.evidence_consistency_status == "SUPPORTED"
    assert audited.rule_scope == "candidate"
    assert audited.review_required is False


# ==============================================================================
# 16. Valid CM Raitha higher-education exclusion
# ==============================================================================
def test_16_valid_cm_raitha_higher_education_exclusion():
    """
    Genuine CM Raitha Vidyanidhi completed course / duplicate degree exclusion condition.
    Must be SUPPORTED, candidate scope, and review_required=False.
    """
    ev = SchemeEvidence(
        page_number=3,
        source_text="ಯಾವುದಾದರೂ ಒಂದು ಕೋರ್ಸ್ ಮುಗಿಸಿ ಅದೇ ಹಂತದ ಮತ್ತೊಂದು ಕೋರ್ಸ್ ವ್ಯಾಸಂಗ ಮಾಡುತ್ತಿರುವ ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಈ ಶಿಷ್ಯವೇತನ ಅನ್ವಯಿಸುವುದಿಲ್ಲ.",
        original_kannada_evidence="ಯಾವುದಾದರೂ ಒಂದು ಕೋರ್ಸ್ ಮುಗಿಸಿ ಅದೇ ಹಂತದ ಮತ್ತೊಂದು ಕೋರ್ಸ್ ವ್ಯಾಸಂಗ ಮಾಡುತ್ತಿರುವ ವಿದ್ಯಾರ್ಥಿಗಳಿಗೆ ಈ ಶಿಷ್ಯವೇತನ ಅನ್ವಯಿಸುವುದಿಲ್ಲ.",
        english_interpretation="Students who have already completed a course and are pursuing another equivalent or lower course are not eligible.",
    )
    rule = RuleItem(
        rule="Students who have already completed a course and are pursuing another equivalent or lower course are not eligible.",
        type="exclusion",
        evidence=ev,
    )

    audited = audit_rule_semantic_consistency(rule)

    assert audited.evidence_consistency_status == "SUPPORTED"
    assert audited.rule_scope == "candidate"
    assert audited.review_required is False
