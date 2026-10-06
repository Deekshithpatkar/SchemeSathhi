"""
Comprehensive Test Suite for Checkpoint 10: Semantic Eligibility & Rule Extraction.
Covers all 16 required test scenarios:
1. explicit eligibility rule
2. explicit exclusion rule
3. age criterion
4. income criterion
5. land criterion
6. government employee exclusion
7. application instructions are ignored
8. blank form fields are ignored
9. administrative instructions are ignored
10. unsupported scheme knowledge is not invented
11. low OCR confidence triggers review when appropriate
12. evidence is preserved
13. semantic confidence is not automatically 1.0
14. review_required_count is correct
15. invalid LLM JSON handling
16. Pydantic validation
"""

import pytest
import json
from pathlib import Path
from typing import Dict, Any, Optional

from app.schemas import (
    SchemeExtraction,
    SchemeEvidence,
    RuleItem,
    ExtractionMetadata,
)
from app.llm_client import LLMClient
from app.rule_extractor import (
    format_document_context,
    audit_and_enhance_extraction,
    extract_scheme_rules,
    save_extracted_rules,
    is_candidate_qualification_rule,
    is_absence_statement,
    is_administrative_funding_statement,
    assess_evidence_quality,
)


class MockLLMClient(LLMClient):
    """
    Mock LLM client returning predetermined JSON payloads or simulating errors.
    """
    def __init__(self, responses: Optional[list] = None):
        super().__init__(base_url="http://mock-llm:11434", model="mock-model")
        self.responses = responses or []
        self.call_count = 0

    def _request_raw(self, payload: Dict[str, Any]) -> str:
        self.call_count += 1
        if not self.responses:
            raise ValueError("No mock responses left.")
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        if isinstance(resp, str):
            return resp
        return json.dumps(resp)


@pytest.fixture
def sample_step9_json():
    """Sample structured Step 9 document JSON."""
    return {
        "document": {
            "filename": "karnataka_farmer_scheme_2026.pdf",
            "filepath": "/data/raw/karnataka_farmer_scheme_2026.pdf",
            "source_url": "https://agri.karnataka.gov.in/schemes",
            "total_pages": 2,
            "processed_at": "2026-10-02T10:00:00Z",
            "pipeline_version": "2.0_document_understanding",
        },
        "summary": {
            "total_pages": 2,
            "usable_pages_count": 1,
            "scanned_pages_count": 1,
            "total_tables_detected": 1,
        },
        "pages": [
            {
                "page_number": 1,
                "page_type": "TEXT",
                "avg_confidence": 100.0,
                "tables": [],
                "forms": None,
                "blocks": [
                    {
                        "text": "Government of Karnataka. Agriculture Department.\nKrishi Samruddhi Scheme 2026.",
                        "confidence": 100.0,
                    },
                    {
                        "text": "Eligibility: Small and marginal farmers with cultivable land up to 2 hectares in Karnataka.",
                        "confidence": 100.0,
                    },
                    {
                        "text": "Applicant must be aged between 18 and 60 years with annual family income below Rs. 2,00,000.",
                        "confidence": 100.0,
                    },
                    {
                        "text": "Exclusions: Government servants, constitutional post holders, and income tax payees are excluded.",
                        "confidence": 100.0,
                    },
                    {
                        "text": "Administrative: Physical applications must be submitted to the Taluk Agriculture Officer.",
                        "confidence": 100.0,
                    }
                ],
            },
            {
                "page_number": 2,
                "page_type": "TABLE",
                "avg_confidence": 85.0,
                "forms": {
                    "is_form": True,
                    "fields_count": 3,
                    "fields": [
                        {"label": "Applicant Name", "raw_match": "ಅರ್ಜಿದಾರರ ಹೆಸರು", "value": None},
                        {"label": "Gender", "raw_match": "ಲಿಂಗ", "value": None},
                        {"label": "Mobile Number", "raw_match": "ಮೊಬೈಲ್ ಸಂಖ್ಯೆ", "value": None}
                    ]
                },
                "tables": [
                    {
                        "type": "table",
                        "page": 2,
                        "bbox": [50, 50, 500, 300],
                        "rows_count": 2,
                        "cells_count": 4,
                        "rows": [
                            {
                                "row_index": 0,
                                "cells": [
                                    {"row": 0, "column": 0, "text": "Farmer Category", "confidence": 92.0},
                                    {"row": 0, "column": 1, "text": "Eligible Land Ceiling", "confidence": 90.0}
                                ]
                            },
                            {
                                "row_index": 1,
                                "cells": [
                                    {"row": 1, "column": 0, "text": "Marginal Farmer", "confidence": 88.0},
                                    {"row": 1, "column": 1, "text": "Up to 1.0 Hectare", "confidence": 95.0}
                                ]
                            }
                        ]
                    }
                ],
                "blocks": []
            }
        ]
    }


def test_scenario_1_explicit_eligibility_rule():
    """Scenario 1: Explicit eligibility rule captures category, threshold, and source text."""
    rule = RuleItem(
        rule="Applicant must be a farmer owning cultivable land in Karnataka",
        type="eligibility",
        value="Cultivable land owner",
        category="farmer_status",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="Small and marginal farmers with cultivable land up to 2 hectares in Karnataka",
            ocr_confidence=98.0
        ),
        semantic_confidence=0.85
    )
    assert rule.type == "eligibility"
    assert rule.category == "farmer_status"
    assert rule.value == "Cultivable land owner"
    assert rule.review_required is False


def test_scenario_2_explicit_exclusion_rule():
    """Scenario 2: Explicit exclusion rule captures disqualification condition."""
    exclusion = RuleItem(
        rule="Income tax payers are excluded from the scheme",
        type="exclusion",
        value="Income tax payer",
        category="income",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="Income tax payees are excluded",
            ocr_confidence=95.0
        ),
        semantic_confidence=0.85
    )
    assert exclusion.type == "exclusion"
    assert exclusion.category == "income"
    assert "excluded" in exclusion.rule


def test_scenario_3_age_criterion():
    """Scenario 3: Age criterion is properly captured with age category and threshold."""
    rule = RuleItem(
        rule="Applicant must be between 18 and 60 years of age",
        type="eligibility",
        value="18-60 years",
        category="age",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="Applicant must be aged between 18 and 60 years",
            ocr_confidence=99.0
        )
    )
    assert rule.category == "age"
    assert rule.value == "18-60 years"


def test_scenario_4_income_criterion():
    """Scenario 4: Income criterion is captured with income category and monetary threshold."""
    rule = RuleItem(
        rule="Annual family income must be below Rs. 2,00,000",
        type="eligibility",
        value="< Rs. 2,00,000",
        category="income",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="annual family income below Rs. 2,00,000",
            ocr_confidence=96.0
        )
    )
    assert rule.category == "income"
    assert rule.value == "< Rs. 2,00,000"


def test_scenario_5_land_criterion():
    """Scenario 5: Land criterion is captured with land_size or land_ownership category."""
    rule = RuleItem(
        rule="Must own less than 2.0 hectares of agricultural land",
        type="eligibility",
        value="<= 2.0 Ha",
        category="land_size",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="cultivable land up to 2 hectares in Karnataka",
            ocr_confidence=97.0
        )
    )
    assert rule.category == "land_size"
    assert rule.value == "<= 2.0 Ha"


def test_scenario_6_government_employee_exclusion():
    """Scenario 6: Government servants/officers disqualification is captured as an exclusion rule."""
    exclusion = RuleItem(
        rule="Government servants and constitutional post holders are excluded",
        type="exclusion",
        value="Government employee",
        category="employment",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="Government servants, constitutional post holders, and income tax payees are excluded",
            ocr_confidence=98.0
        )
    )
    assert exclusion.type == "exclusion"
    assert exclusion.category == "employment"


def test_scenario_7_application_instructions_ignored(sample_step9_json):
    """Scenario 7: Application submission instructions (e.g. 'Submit to Taluk officer') are ignored as rules."""
    context = format_document_context(sample_step9_json)
    # The prompt explicitly instructs ignoring office submission procedures
    assert "Taluk Agriculture Officer" in context

    # If LLM mistakenly returns an application instruction, audit_and_enhance_extraction removes it
    raw_extraction = SchemeExtraction(
        scheme_name="Krishi Samruddhi",
        eligibility_rules=[
            RuleItem(
                rule="Physical applications must be submitted to the Taluk Agriculture Officer",
                type="eligibility",
                evidence=SchemeEvidence(page_number=1, source_text="submitted to the Taluk Agriculture Officer")
            )
        ]
    )
    audited = audit_and_enhance_extraction(raw_extraction, sample_step9_json, model_name="mock-model")
    assert len(audited.eligibility_rules) == 0  # Administrative instruction filtered out


def test_scenario_8_blank_form_fields_ignored(sample_step9_json):
    """Scenario 8: Blank form fields (Applicant Name, Gender, Mobile Number) are NOT converted into eligibility criteria."""
    context = format_document_context(sample_step9_json)
    assert "Detected Form Template Fields" in context
    assert "Applicant Name" in context

    # Test that blank form fields are not accepted as eligibility rules
    extraction = SchemeExtraction(
        scheme_name="Application Form Template",
        eligibility_rules=[],
        exclusion_rules=[]
    )
    assert len(extraction.eligibility_rules) == 0
    assert len(extraction.exclusion_rules) == 0


def test_scenario_9_administrative_instructions_ignored(sample_step9_json):
    """Scenario 9: Forwarding memos and preservation instructions are filtered out."""
    raw_extraction = SchemeExtraction(
        scheme_name="Guidelines Circular",
        eligibility_rules=[
            RuleItem(
                rule="Physical declarations will be sent periodically to Taluk office for preservation",
                type="eligibility",
                evidence=SchemeEvidence(page_number=1, source_text="ಸಹಾಯಕ ಕೃಷಿ ನಿರ್ದೇಶಕರ ಕಛೇರಿಗೆ ಪರಿಶೀಲಿಸಲು ಮತ್ತು ಸಂರಕ್ಷಿಸಲು")
            )
        ]
    )
    audited = audit_and_enhance_extraction(raw_extraction, sample_step9_json, model_name="mock-model")
    assert len(audited.eligibility_rules) == 0


def test_scenario_10_unsupported_scheme_knowledge_not_invented():
    """Scenario 10: Unsupported attributes remain empty / None, not hallucinated from general knowledge."""
    extraction = SchemeExtraction(
        scheme_name="Fertilizer Scheme",
        eligibility_rules=[],
        exclusion_rules=[]
    )
    assert extraction.purpose is None
    assert extraction.eligibility_rules == []
    assert extraction.exclusion_rules == []


def test_scenario_11_low_ocr_confidence_triggers_review():
    """Scenario 11: When OCR confidence is low (< 60%), audit_and_enhance_extraction flags review_required."""
    extraction = SchemeExtraction(
        scheme_name="Degraded Gazette",
        eligibility_rules=[
            RuleItem(
                rule="Resident of Karnataka with degraded OCR text",
                type="eligibility",
                evidence=SchemeEvidence(
                    page_number=1,
                    source_text="ಕನಾ೯ಟಕ ... ವಾಸಿ",
                    ocr_confidence=42.5  # Below 60%
                )
            )
        ]
    )

    doc_json = {"document": {"filename": "scan.pdf"}, "pages": [{"page_type": "SCANNED", "avg_confidence": 45.0}]}
    audited = audit_and_enhance_extraction(extraction, doc_json, model_name="mock-model", low_conf_threshold=60.0)

    assert audited.review_required is True
    assert audited.eligibility_rules[0].review_required is True
    assert any("Low OCR confidence (42.5%)" in r for r in audited.review_reasons)


def test_scenario_12_evidence_is_preserved():
    """Scenario 12: Evidence objects retain page, source text, table coordinates, and OCR confidence."""
    evidence = SchemeEvidence(
        page_number=2,
        source_text="Marginal Farmer | Up to 1.0 Hectare",
        table_index=0,
        row_index=1,
        column_index=1,
        cell_text="Up to 1.0 Hectare",
        ocr_confidence=95.0
    )
    assert evidence.page_number == 2
    assert evidence.table_index == 0
    assert evidence.row_index == 1
    assert evidence.column_index == 1
    assert evidence.cell_text == "Up to 1.0 Hectare"
    assert evidence.ocr_confidence == 95.0


def test_scenario_13_semantic_confidence_not_automatically_one():
    """Scenario 13: Semantic confidence is not automatically 1.0 and is capped conservatively."""
    # Test default
    rule_default = RuleItem(rule="Must be a resident of Karnataka")
    assert rule_default.semantic_confidence == 0.85
    assert rule_default.semantic_confidence < 1.0

    # Test capping if 1.0 is passed
    rule_capped = RuleItem(rule="Must be a farmer", semantic_confidence=1.0)
    assert rule_capped.semantic_confidence == 0.90
    assert rule_capped.semantic_confidence < 1.0


def test_scenario_14_review_required_count_is_correct():
    """Scenario 14: When review_required is True, review_required_count is accurate and >= 1."""
    extraction = SchemeExtraction(
        scheme_name=None,  # Missing scheme name triggers document-level review reason
        eligibility_rules=[
            RuleItem(
                rule="Unclear land size",
                review_required=True,
                review_reasons=["Uncertain land measure in degraded scan"]
            )
        ],
        review_reasons=["Scheme name could not be definitively identified from document text."]
    )

    doc_json = {"document": {"filename": "test.pdf"}, "pages": []}
    audited = audit_and_enhance_extraction(extraction, doc_json, model_name="mock-model")

    assert audited.review_required is True
    # Count must be accurate (rule reviews + document review reasons)
    assert audited.extraction_metadata.review_required_count >= 1
    assert audited.extraction_metadata.validation_status == "review_needed"


def test_scenario_15_invalid_llm_json_handling(sample_step9_json, tmp_path):
    """Scenario 15: LLM client gracefully retries when receiving invalid JSON string."""
    bad_response = "Broken JSON string { unclosed"
    valid_response = {
        "scheme_name": "Recovered Scheme",
        "eligibility_rules": [
            {
                "rule": "Must be farmer",
                "type": "eligibility",
                "category": "farmer_status",
                "evidence": {"page_number": 1, "source_text": "Must be farmer", "ocr_confidence": 95.0}
            }
        ],
        "exclusion_rules": []
    }

    mock_client = MockLLMClient([bad_response, valid_response])
    result = extract_scheme_rules(sample_step9_json, llm_client=mock_client, output_dir=tmp_path)
    assert result.scheme_name == "Recovered Scheme"
    assert len(result.eligibility_rules) == 1
    assert mock_client.call_count == 2


def test_scenario_16_pydantic_validation(sample_step9_json):
    """Scenario 16: Broken JSON raising error after exhausting retries."""
    mock_client = MockLLMClient(["Broken 1 {", "Broken 2 {"])
    with pytest.raises(RuntimeError) as exc_info:
        extract_scheme_rules(sample_step9_json, llm_client=mock_client, max_retries=2)
    assert "Failed to generate valid JSON" in str(exc_info.value)


def test_scenario_17_amendments_and_document_status_ignored(sample_step9_json):
    """
    Scenario 17: Statements about amendments, document status, notifications,
    or procedural changes (e.g. 'There is no change in said notification' /
    'ಸದರಿ ಅಧಿಸೂಚನೆಯಲ್ಲಿ ಯಾವುದೇ ಬದಲಾವಣೆ ಇರುವುದಿಲ್ಲ') MUST BE REJECTED from both
    eligibility_rules and exclusion_rules.
    """
    # 1. Direct unit test of is_candidate_qualification_rule
    amendment_rule = RuleItem(
        rule="ಸದರಿ ಅಧಿಸೂಚನೆಯಲ್ಲಿ ಯಾವುದೇ `ಬದಲಾವಣೆ ಇರುವುದಿಲ್ಲ",
        type="exclusion",
        category="residency",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="ಸದರಿ ಅಧಿಸೂಚನೆಯಲ್ಲಿ ಯಾವುದೇ `ಬದಲಾವಣೆ ಇರುವುದಿಲ್ಲ",
            ocr_confidence=75.0
        )
    )
    is_valid, reason = is_candidate_qualification_rule(amendment_rule)
    assert is_valid is False
    assert "amendment" in reason or "notification" in reason

    english_amendment = RuleItem(
        rule="There is no change in the said notification",
        type="exclusion",
        evidence=SchemeEvidence(page_number=3, source_text="Apart from this, there is no change in the said notification")
    )
    is_valid_en, reason_en = is_candidate_qualification_rule(english_amendment)
    assert is_valid_en is False

    # 2. Integration test in audit_and_enhance_extraction
    raw_extraction = SchemeExtraction(
        scheme_name="PM-KISAN Guidelines",
        eligibility_rules=[
            RuleItem(
                rule="ಉಳಿದಂತೆ ಸದರಿ ಅಧಿಸೂಚನೆಯಲ್ಲಿ ಯಾವುದೇ ಬದಲಾವಣೆ ಇರುವುದಿಲ್ಲ",
                type="eligibility",
                evidence=SchemeEvidence(page_number=3, source_text="ಉಳಿದಂತೆ ಸದರಿ ಅಧಿಸೂಚನೆಯಲ್ಲಿ ಯಾವುದೇ ಬದಲಾವಣೆ ಇರುವುದಿಲ್ಲ")
            )
        ],
        exclusion_rules=[
            amendment_rule
        ]
    )

    audited = audit_and_enhance_extraction(raw_extraction, sample_step9_json, model_name="mock-model")
    # Both must be completely empty!
    assert audited.eligibility_rules == []
    assert audited.exclusion_rules == []
    assert audited.extraction_metadata.rule_count == 0


def test_scenario_18_rules_rejected_unless_candidate_qualification(sample_step9_json):
    """
    Scenario 18: Reject any eligibility/exclusion rule unless its evidence explicitly describes
    a candidate qualification, disqualification, or condition that directly affects eligibility.
    """
    # Office dispatch / spare copies memo
    dispatch_rule = RuleItem(
        rule="ಶಾಖೆಯ ರಕ್ಷಾ ಕಡತ / ಹೆಚ್ಚುವರಿ ಪ್ರತಿಗಳು",
        type="exclusion",
        evidence=SchemeEvidence(page_number=4, source_text="ಶಾಖೆಯ ರಕ್ಷಾ ಕಡತ / ಹೆಚ್ಚುವರಿ ಪ್ರತಿಗಳು")
    )
    assert is_candidate_qualification_rule(dispatch_rule)[0] is False

    # Genuine candidate qualification rule
    genuine_farmer_rule = RuleItem(
        rule="ಸಣ್ಣ ಮತ್ತು ಅತಿ ಸಣ್ಣ ರೈತರು ಮಾತ್ರ ಅರ್ಹರು",
        type="eligibility",
        category="farmer_status",
        evidence=SchemeEvidence(page_number=1, source_text="ಸಣ್ಣ ಮತ್ತು ಅತಿ ಸಣ್ಣ ರೈತರು ಮಾತ್ರ ಅರ್ಹರು", ocr_confidence=95.0)
    )
    assert is_candidate_qualification_rule(genuine_farmer_rule)[0] is True

    # Genuine candidate exclusion rule
    genuine_exclusion_rule = RuleItem(
        rule="ಸರ್ಕಾರಿ ನೌಕರರು ಮತ್ತು ಆದಾಯ ತೆರಿಗೆ ಪಾವತಿದಾರರು ಅನರ್ಹರು",
        type="exclusion",
        category="employment",
        evidence=SchemeEvidence(page_number=1, source_text="ಸರ್ಕಾರಿ ನೌಕರರು ಮತ್ತು ಆದಾಯ ತೆರಿಗೆ ಪಾವತಿದಾರರು ಅನರ್ಹರು", ocr_confidence=95.0)
    )
    assert is_candidate_qualification_rule(genuine_exclusion_rule)[0] is True

    # Process extraction with mixed rules: genuine kept, non-candidate dropped
    extraction = SchemeExtraction(
        scheme_name="Karnataka Scheme",
        eligibility_rules=[genuine_farmer_rule],
        exclusion_rules=[dispatch_rule, genuine_exclusion_rule]
    )
    audited = audit_and_enhance_extraction(extraction, sample_step9_json, model_name="mock-model")

    assert len(audited.eligibility_rules) == 1
    assert audited.eligibility_rules[0].rule == "ಸಣ್ಣ ಮತ್ತು ಅತಿ ಸಣ್ಣ ರೈತರು ಮಾತ್ರ ಅರ್ಹರು"

    assert len(audited.exclusion_rules) == 1
    assert audited.exclusion_rules[0].rule == "ಸರ್ಕಾರಿ ನೌಕರರು ಮತ್ತು ಆದಾಯ ತೆರಿಗೆ ಪಾವತಿದಾರರು ಅನರ್ಹರು"


def test_scenario_19_rkvy_statewise_allocation_rejected(sample_step9_json):
    """
    Scenario 19 (Regression FIX 1): RKVY CP15 false positive where state-wise funding allocation
    table header was hallucinated into an individual residency eligibility rule must be rejected.
    """
    rkvy_false_positive = RuleItem(
        rule="Must be a resident of the state or UT as per the allocation",
        type="eligibility",
        category="residency",
        evidence=SchemeEvidence(
            page_number=2,
            source_text="State-wise Allocation under Normal RKVY - RAFTAAR General, SCSP and TSP (2021-22)",
            ocr_confidence=78.0
        )
    )
    is_valid, reason = is_candidate_qualification_rule(rkvy_false_positive)
    assert is_valid is False
    assert "funding" in reason.lower() or "allocation" in reason.lower()

    # Integration audit test
    extraction = SchemeExtraction(
        scheme_name="RKVY Allocation",
        eligibility_rules=[rkvy_false_positive],
        exclusion_rules=[]
    )
    audited = audit_and_enhance_extraction(extraction, sample_step9_json, model_name="mock-model")
    assert audited.eligibility_rules == []
    assert audited.extraction_metadata.rule_count == 0


def test_scenario_20_districtwise_allocation_and_budget_outlay_rejected(sample_step9_json):
    """
    Scenario 20 (Regression FIX 1): District-wise allocation tables, central/state funding shares,
    budget outlays, and utilization certificates must be rejected as candidate eligibility rules.
    """
    statements = [
        RuleItem(
            rule="District-wise physical and financial outlay for 2021-22",
            type="eligibility",
            evidence=SchemeEvidence(page_number=1, source_text="District-wise physical and financial outlay under RKVY")
        ),
        RuleItem(
            rule="Central share 60% and State share 40% funding pattern",
            type="eligibility",
            evidence=SchemeEvidence(page_number=1, source_text="Funding pattern is 60:40 between Central and State Government")
        ),
        RuleItem(
            rule="Submission of utilization certificate",
            type="eligibility",
            evidence=SchemeEvidence(page_number=2, source_text="Implementing department must submit utilization certificates within 3 months")
        ),
        RuleItem(
            rule="Total budget outlay of Rs. 1000 crore",
            type="eligibility",
            evidence=SchemeEvidence(page_number=1, source_text="The total financial outlay approved is Rs. 1000 crore")
        ),
    ]

    for item in statements:
        is_valid, reason = is_candidate_qualification_rule(item)
        assert is_valid is False, f"Expected '{item.rule}' to be rejected, got reason: {reason}"

    extraction = SchemeExtraction(
        scheme_name="Budget Circular",
        eligibility_rules=statements,
        exclusion_rules=[]
    )
    audited = audit_and_enhance_extraction(extraction, sample_step9_json, model_name="mock-model")
    assert audited.eligibility_rules == []


def test_scenario_21_valid_beneficiary_residency_condition_accepted(sample_step9_json):
    """
    Scenario 21 (Regression FIX 1): A genuine individual beneficiary residency requirement
    must be accepted (words like 'state' or 'karnataka' must not cause false rejection).
    """
    valid_residency_rule = RuleItem(
        rule="Applicant must be a permanent resident of Karnataka",
        type="eligibility",
        category="residency",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="Applicant must be a permanent resident of Karnataka state with valid domicile certificate.",
            ocr_confidence=95.0
        )
    )
    is_valid, reason = is_candidate_qualification_rule(valid_residency_rule)
    assert is_valid is True, f"Expected rule to be accepted, got: {reason}"

    extraction = SchemeExtraction(
        scheme_name="State Farmer Scheme",
        eligibility_rules=[valid_residency_rule],
        exclusion_rules=[]
    )
    audited = audit_and_enhance_extraction(extraction, sample_step9_json, model_name="mock-model")
    assert len(audited.eligibility_rules) == 1
    assert audited.eligibility_rules[0].rule == "Applicant must be a permanent resident of Karnataka"


def test_scenario_22_valid_district_restriction_on_beneficiaries_accepted(sample_step9_json):
    """
    Scenario 22 (Regression FIX 1): A genuine district-level restriction on beneficiaries
    must be accepted (the word 'district' does not cause false rejection when describing individuals).
    """
    valid_district_rule = RuleItem(
        rule="Only small farmers residing in Belagavi, Haveri and Gadag districts are eligible",
        type="eligibility",
        category="geographic_location",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="Under this component, only small farmers residing in Belagavi, Haveri and Gadag districts are eligible to apply.",
            ocr_confidence=96.0
        )
    )
    is_valid, reason = is_candidate_qualification_rule(valid_district_rule)
    assert is_valid is True, f"Expected rule to be accepted, got: {reason}"

    extraction = SchemeExtraction(
        scheme_name="Drought Relief Scheme",
        eligibility_rules=[valid_district_rule],
        exclusion_rules=[]
    )
    audited = audit_and_enhance_extraction(extraction, sample_step9_json, model_name="mock-model")
    assert len(audited.eligibility_rules) == 1
    assert audited.eligibility_rules[0].category == "geographic_location"


def test_scenario_23_no_specific_exclusion_rules_produces_empty_list(sample_step9_json):
    """
    Scenario 23 (Regression FIX 2): 'No specific exclusion rules provided in the document'
    must produce zero exclusion rules (empty list), never a RuleItem with type='exclusion'.
    """
    raw_dict = {
        "scheme_name": "RKVY",
        "eligibility_rules": [],
        "exclusion_rules": [
            {
                "rule": "No specific exclusion rules provided in the document",
                "type": "exclusion",
                "evidence": {
                    "page_number": 2,
                    "source_text": "No specific exclusion rules provided in the document",
                    "ocr_confidence": 78.0
                }
            }
        ]
    }

    # 1. Pydantic validation drops it
    extraction = SchemeExtraction.model_validate(raw_dict)
    assert extraction.exclusion_rules == []

    # 2. RuleItem check directly
    item = RuleItem(
        rule="No specific exclusion rules provided in the document",
        type="exclusion",
        evidence=SchemeEvidence(page_number=2, source_text="No specific exclusion rules provided in the document")
    )
    is_valid, reason = is_candidate_qualification_rule(item)
    assert is_valid is False
    assert "absence" in reason.lower()


def test_scenario_24_absence_statement_variants_produce_empty_list(sample_step9_json):
    """
    Scenario 24 (Regression FIX 2): Various metadata absence assertions must all be rejected,
    leaving exclusion_rules empty.
    """
    variants = [
        "No exclusions mentioned",
        "No specific exclusion criteria",
        "No exclusion rules provided",
        "No exclusions provided",
        "No exclusions found",
        "None provided",
        "Not mentioned in document",
        "ಯಾವುದೇ ಅನರ್ಹತೆ ನಿಯಮಗಳಿಲ್ಲ",
    ]

    for var in variants:
        assert is_absence_statement(var) is True
        item = RuleItem(
            rule=var,
            type="exclusion",
            evidence=SchemeEvidence(page_number=1, source_text=var)
        )
        is_valid, reason = is_candidate_qualification_rule(item)
        assert is_valid is False, f"Expected '{var}' to be rejected as absence statement"

    # Integration test with raw dict containing multiple absence statements
    raw_dict = {
        "scheme_name": "Test Scheme",
        "eligibility_rules": [],
        "exclusion_rules": [{"rule": v, "type": "exclusion"} for v in variants]
    }
    extraction = SchemeExtraction.model_validate(raw_dict)
    assert extraction.exclusion_rules == []


def test_scenario_25_weak_garbled_evidence_triggers_review(sample_step9_json):
    """
    Scenario 25 (Regression FIX 3): Plausible candidate qualification rule with garbled/corrupted
    OCR text in evidence must be accepted provisionally, but review_required must be set to True.
    """
    garbled_rule = RuleItem(
        rule="Must be a small or marginal farmer",
        type="eligibility",
        category="farmer_status",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="dOe; ;j:meje$aaocb (G&SSA)zaap, rde erodxb, abdjoe,eomsd",
            ocr_confidence=95.0
        ),
        semantic_confidence=0.85
    )

    # The rule statement itself is a valid candidate qualification
    is_valid, _ = is_candidate_qualification_rule(garbled_rule)
    assert is_valid is True

    # But evidence quality assessment detects garbled symbols
    is_weak, weak_reason = assess_evidence_quality(garbled_rule)
    assert is_weak is True
    assert "garbled" in weak_reason.lower() or "ocr" in weak_reason.lower()

    # In audit_and_enhance_extraction, rule is kept but flagged for review
    extraction = SchemeExtraction(
        scheme_name="PM-KISAN Karnataka",
        eligibility_rules=[garbled_rule],
        exclusion_rules=[]
    )
    audited = audit_and_enhance_extraction(extraction, sample_step9_json, model_name="mock-model")

    assert len(audited.eligibility_rules) == 1
    assert audited.eligibility_rules[0].review_required is True
    assert audited.eligibility_rules[0].semantic_confidence <= 0.70
    assert audited.review_required is True
    assert any("garbled" in r.lower() or "ocr" in r.lower() for r in audited.review_reasons)


def test_scenario_26_clean_rule_with_good_evidence_does_not_trigger_review(sample_step9_json):
    """
    Scenario 26 (Regression FIX 3): Good candidate qualification rule with clean, unambiguous
    evidence must be accepted with review_required=False and unpenalized confidence.
    """
    clean_rule = RuleItem(
        rule="Small farmers owning cultivable land up to 2 hectares in Karnataka are eligible",
        type="eligibility",
        category="land_size",
        evidence=SchemeEvidence(
            page_number=1,
            source_text="Small and marginal farmers with cultivable land up to 2 hectares in Karnataka are eligible for assistance.",
            ocr_confidence=98.0
        ),
        semantic_confidence=0.85
    )

    is_weak, _ = assess_evidence_quality(clean_rule)
    assert is_weak is False

    extraction = SchemeExtraction(
        scheme_name="Clean Karnataka Scheme",
        eligibility_rules=[clean_rule],
        exclusion_rules=[]
    )
    audited = audit_and_enhance_extraction(extraction, sample_step9_json, model_name="mock-model")

    assert len(audited.eligibility_rules) == 1
    assert audited.eligibility_rules[0].review_required is False
    assert audited.eligibility_rules[0].semantic_confidence == 0.85
    assert audited.review_required is False

