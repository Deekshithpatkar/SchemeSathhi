"""
Comprehensive Test Suite for Checkpoint 12: Rule Comparison.
Covers all 18 required comparison scenarios:
1. Identical rule sets
2. Added eligibility rule
3. Removed eligibility rule
4. Modified income threshold
5. Modified age threshold
6. Modified landholding threshold
7. Added exclusion
8. Removed exclusion
9. Unchanged rule with different wording
10. Administrative text change
11. Amendment/document-status text
12. Multiple simultaneous changes
13. Ambiguous rule
14. Missing evidence
15. Duplicate/rephrased rules
16. More restrictive change
17. Less restrictive change
18. No eligibility rules in either version
"""

import pytest
import json
from pathlib import Path
from typing import Dict, Any, Optional

from app.schemas import RuleItem, SchemeEvidence, SchemeExtraction
from app.rule_comparison_schemas import (
    RuleComparison,
    RuleComparisonResult,
    RuleComparisonMetadata,
)
from app.rule_comparison import (
    compare_rules,
    normalize_rule_text,
    detect_rule_category,
    extract_numeric_threshold,
    determine_threshold_impact,
    deduplicate_rules,
)
from app.llm_client import LLMClient


class MockLLMClient(LLMClient):
    """Mock LLM client returning predetermined JSON payloads for controlled testing."""
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


def make_evidence(text: str, page: int = 1) -> SchemeEvidence:
    """Helper to generate physical evidence for tests."""
    return SchemeEvidence(
        page_number=page,
        source_text=text,
        ocr_confidence=98.5
    )


# ==============================================================================
# TEST 1: Identical Rule Sets
# ==============================================================================
def test_1_identical_rule_sets():
    rule = RuleItem(
        rule="Annual family income must not exceed Rs. 2.5 lakh",
        type="eligibility",
        category="income",
        evidence=make_evidence("Annual family income must not exceed Rs. 2.5 lakh"),
    )
    old_data = {"eligibility_rules": [rule], "exclusion_rules": []}
    new_data = {"eligibility_rules": [rule], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.rule_changes) == 1
    assert len(res.unchanged_rules) == 1
    assert len(res.added_rules) == 0
    assert len(res.removed_rules) == 0
    assert len(res.modified_rules) == 0
    assert res.unchanged_rules[0].change_type == "unchanged"
    assert res.unchanged_rules[0].impact == "no_eligibility_impact"
    assert res.eligibility_relevance == "none"


# ==============================================================================
# TEST 2: Added Eligibility Rule
# ==============================================================================
def test_2_added_eligibility_rule():
    new_rule = RuleItem(
        rule="Applicant must own less than 5 hectares of land",
        type="eligibility",
        category="landholding",
        evidence=make_evidence("Applicant must own less than 5 hectares of land"),
    )
    old_data = {"eligibility_rules": [], "exclusion_rules": []}
    new_data = {"eligibility_rules": [new_rule], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.added_rules) == 1
    assert res.added_rules[0].change_type == "added"
    assert res.added_rules[0].category == "landholding"
    assert res.added_rules[0].impact == "eligibility_more_restrictive"
    assert res.eligibility_relevance == "clearly_relevant"


# ==============================================================================
# TEST 3: Removed Eligibility Rule
# ==============================================================================
def test_3_removed_eligibility_rule():
    old_rule = RuleItem(
        rule="Applicant must be a resident of Karnataka",
        type="eligibility",
        category="residency",
        evidence=make_evidence("Applicant must be a resident of Karnataka"),
    )
    old_data = {"eligibility_rules": [old_rule], "exclusion_rules": []}
    new_data = {"eligibility_rules": [], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.removed_rules) == 1
    assert res.removed_rules[0].change_type == "removed"
    assert res.removed_rules[0].category == "residency"
    assert res.removed_rules[0].impact == "eligibility_less_restrictive"
    assert res.eligibility_relevance == "clearly_relevant"


# ==============================================================================
# TEST 4: Modified Income Threshold
# ==============================================================================
def test_4_modified_income_threshold():
    old_rule = RuleItem(
        rule="Annual family income must not exceed Rs. 2.5 lakh",
        type="eligibility",
        category="income",
        evidence=make_evidence("Annual family income must not exceed Rs. 2.5 lakh"),
    )
    new_rule = RuleItem(
        rule="Annual household income shall not exceed Rs. 3,00,000",
        type="eligibility",
        category="income",
        evidence=make_evidence("Annual household income shall not exceed Rs. 3,00,000"),
    )
    old_data = {"eligibility_rules": [old_rule], "exclusion_rules": []}
    new_data = {"eligibility_rules": [new_rule], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.modified_rules) == 1
    mod = res.modified_rules[0]
    assert mod.change_type == "modified"
    assert mod.category == "income"
    assert mod.impact == "eligibility_less_restrictive"
    assert res.eligibility_relevance == "clearly_relevant"


# ==============================================================================
# TEST 5: Modified Age Threshold
# ==============================================================================
def test_5_modified_age_threshold():
    old_rule = RuleItem(
        rule="Applicant must be at least 18 years old",
        type="eligibility",
        category="age",
        evidence=make_evidence("Applicant must be at least 18 years old"),
    )
    new_rule = RuleItem(
        rule="Applicant must be at least 21 years old",
        type="eligibility",
        category="age",
        evidence=make_evidence("Applicant must be at least 21 years old"),
    )
    old_data = {"eligibility_rules": [old_rule], "exclusion_rules": []}
    new_data = {"eligibility_rules": [new_rule], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.modified_rules) == 1
    mod = res.modified_rules[0]
    assert mod.change_type == "modified"
    assert mod.category == "age"
    # Raising minimum age from 18 to 21 makes it harder to qualify -> more restrictive
    assert mod.impact == "eligibility_more_restrictive"
    assert res.eligibility_relevance == "clearly_relevant"


# ==============================================================================
# TEST 6: Modified Landholding Threshold
# ==============================================================================
def test_6_modified_landholding_threshold():
    old_rule = RuleItem(
        rule="Applicant must own less than 2 hectares of land",
        type="eligibility",
        category="landholding",
        evidence=make_evidence("Applicant must own less than 2 hectares of land"),
    )
    new_rule = RuleItem(
        rule="Applicant must own less than 5 hectares of land",
        type="eligibility",
        category="landholding",
        evidence=make_evidence("Applicant must own less than 5 hectares of land"),
    )
    old_data = {"eligibility_rules": [old_rule], "exclusion_rules": []}
    new_data = {"eligibility_rules": [new_rule], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.modified_rules) == 1
    mod = res.modified_rules[0]
    assert mod.change_type == "modified"
    assert mod.category == "landholding"
    # Increasing land limit ceiling allows more farmers to qualify -> less restrictive
    assert mod.impact == "eligibility_less_restrictive"
    assert res.eligibility_relevance == "clearly_relevant"


# ==============================================================================
# TEST 7: Added Exclusion
# ==============================================================================
def test_7_added_exclusion():
    old_ex = RuleItem(
        rule="Government employees are not eligible",
        type="exclusion",
        category="government_employee",
        evidence=make_evidence("Government employees are not eligible"),
    )
    new_ex = RuleItem(
        rule="Institutional landholders are not eligible",
        type="exclusion",
        category="institutional_landholder",
        evidence=make_evidence("Institutional landholders are not eligible"),
    )
    old_data = {"eligibility_rules": [], "exclusion_rules": [old_ex]}
    new_data = {"eligibility_rules": [], "exclusion_rules": [old_ex, new_ex]}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.added_rules) == 1
    assert len(res.unchanged_rules) == 1
    assert res.added_rules[0].change_type == "added"
    assert res.added_rules[0].category == "institutional_landholder"
    assert res.added_rules[0].impact == "exclusion_added"
    assert res.eligibility_relevance == "clearly_relevant"


# ==============================================================================
# TEST 8: Removed Exclusion
# ==============================================================================
def test_8_removed_exclusion():
    old_ex = RuleItem(
        rule="Government employees are not eligible",
        type="exclusion",
        category="government_employee",
        evidence=make_evidence("Government employees are not eligible"),
    )
    old_data = {"eligibility_rules": [], "exclusion_rules": [old_ex]}
    new_data = {"eligibility_rules": [], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.removed_rules) == 1
    assert res.removed_rules[0].change_type == "removed"
    assert res.removed_rules[0].category == "government_employee"
    assert res.removed_rules[0].impact == "exclusion_removed"
    assert res.eligibility_relevance == "clearly_relevant"


# ==============================================================================
# TEST 9: Unchanged Rule with Different Wording
# ==============================================================================
def test_9_unchanged_rule_with_different_wording():
    old_rule = RuleItem(
        rule="Applicant must be a Karnataka resident",
        type="eligibility",
        category="residency",
        evidence=make_evidence("Applicant must be a Karnataka resident"),
    )
    new_rule = RuleItem(
        rule="Applicant should be a resident of Karnataka",
        type="eligibility",
        category="residency",
        evidence=make_evidence("Applicant should be a resident of Karnataka"),
    )
    old_data = {"eligibility_rules": [old_rule], "exclusion_rules": []}
    new_data = {"eligibility_rules": [new_rule], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.unchanged_rules) == 1
    assert len(res.modified_rules) == 0
    assert len(res.added_rules) == 0
    assert res.unchanged_rules[0].impact == "no_eligibility_impact"
    assert res.eligibility_relevance == "none"


# ==============================================================================
# TEST 10: Administrative Text Change
# ==============================================================================
def test_10_administrative_text_change():
    old_rule = RuleItem(
        rule="Applications shall be submitted to the Taluk office.",
        type="eligibility",
        category="other",
        evidence=make_evidence("Applications shall be submitted to the Taluk office."),
    )
    new_rule = RuleItem(
        rule="Applications shall be submitted through the online portal.",
        type="eligibility",
        category="other",
        evidence=make_evidence("Applications shall be submitted through the online portal."),
    )
    old_data = {"eligibility_rules": [old_rule], "exclusion_rules": []}
    new_data = {"eligibility_rules": [new_rule], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.rule_changes) == 1
    item = res.rule_changes[0]
    assert item.impact == "no_eligibility_impact"
    assert item.review_required is True
    assert any("administrative" in r.lower() for r in item.review_reasons)


# ==============================================================================
# TEST 11: Amendment / Document-Status Text
# ==============================================================================
def test_11_amendment_document_status_text():
    old_rule = RuleItem(
        rule="There is no change in this notification for the current year.",
        type="eligibility",
        category="other",
        evidence=make_evidence("There is no change in this notification for the current year."),
    )
    new_rule = RuleItem(
        rule="There is no change in this notification.",
        type="eligibility",
        category="other",
        evidence=make_evidence("There is no change in this notification."),
    )
    old_data = {"eligibility_rules": [old_rule], "exclusion_rules": []}
    new_data = {"eligibility_rules": [new_rule], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.rule_changes) == 1
    assert res.rule_changes[0].impact == "no_eligibility_impact"
    assert res.rule_changes[0].review_required is True


# ==============================================================================
# TEST 12: Multiple Simultaneous Changes
# ==============================================================================
def test_12_multiple_simultaneous_changes():
    old_el = RuleItem(
        rule="Annual income must not exceed Rs. 2.5 lakh",
        type="eligibility",
        category="income",
        evidence=make_evidence("Annual income must not exceed Rs. 2.5 lakh"),
    )
    old_ex = RuleItem(
        rule="Government employees are not eligible",
        type="exclusion",
        category="government_employee",
        evidence=make_evidence("Government employees are not eligible"),
    )
    new_el = RuleItem(
        rule="Annual income must not exceed Rs. 3 lakh",
        type="eligibility",
        category="income",
        evidence=make_evidence("Annual income must not exceed Rs. 3 lakh"),
    )
    new_ex1 = RuleItem(
        rule="Government employees are not eligible",
        type="exclusion",
        category="government_employee",
        evidence=make_evidence("Government employees are not eligible"),
    )
    new_ex2 = RuleItem(
        rule="Institutional landholders are not eligible",
        type="exclusion",
        category="institutional_landholder",
        evidence=make_evidence("Institutional landholders are not eligible"),
    )

    old_data = {"eligibility_rules": [old_el], "exclusion_rules": [old_ex]}
    new_data = {"eligibility_rules": [new_el], "exclusion_rules": [new_ex1, new_ex2]}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.modified_rules) == 1
    assert len(res.added_rules) == 1
    assert len(res.unchanged_rules) == 1
    assert res.comparison_metadata.total_changes == 2
    assert res.eligibility_relevance == "clearly_relevant"


# ==============================================================================
# TEST 13: Ambiguous Rule
# ==============================================================================
def test_13_ambiguous_rule():
    old_rule = RuleItem(
        rule="Beneficiary should meet the criteria specified by the district authority",
        type="eligibility",
        category="other",
        evidence=make_evidence("Beneficiary should meet the criteria specified by the district authority"),
    )
    new_rule = RuleItem(
        rule="Beneficiary should satisfy the special conditions decided by the committee",
        type="eligibility",
        category="other",
        evidence=make_evidence("Beneficiary should satisfy the special conditions decided by the committee"),
    )

    mock_llm = MockLLMClient(responses=[
        {
            "is_related": True,
            "change_type": "modified",
            "category": "other",
            "impact": "uncertain",
            "explanation": "Criteria wording changed ambiguously without objective threshold."
        }
    ])

    old_data = {"eligibility_rules": [old_rule], "exclusion_rules": []}
    new_data = {"eligibility_rules": [new_rule], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, llm_client=mock_llm, save_output=False)

    assert len(res.modified_rules) == 1
    mod = res.modified_rules[0]
    assert mod.impact == "uncertain"
    assert mod.review_required is True
    assert res.eligibility_relevance == "uncertain"


# ==============================================================================
# TEST 14: Missing Evidence
# ==============================================================================
def test_14_missing_evidence():
    old_rule = RuleItem(
        rule="Annual income must not exceed Rs. 2.5 lakh",
        type="eligibility",
        category="income",
        evidence=None,  # Missing evidence
    )
    new_rule = RuleItem(
        rule="Annual income must not exceed Rs. 3 lakh",
        type="eligibility",
        category="income",
        evidence=None,  # Missing evidence
    )
    old_data = {"eligibility_rules": [old_rule], "exclusion_rules": []}
    new_data = {"eligibility_rules": [new_rule], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.modified_rules) == 1
    mod = res.modified_rules[0]
    assert mod.review_required is True
    assert any("evidence" in r.lower() for r in mod.review_reasons)
    assert res.review_required is True


# ==============================================================================
# TEST 15: Duplicate / Rephrased Rules
# ==============================================================================
def test_15_duplicate_rephrased_rules():
    r1 = RuleItem(
        rule="Applicant must be a resident of Karnataka",
        type="eligibility",
        category="residency",
        evidence=make_evidence("Applicant must be a resident of Karnataka"),
    )
    r2 = RuleItem(
        rule="Applicant must be a Karnataka resident",
        type="eligibility",
        category="residency",
        evidence=make_evidence("Applicant must be a Karnataka resident"),
    )
    # Both old and new contain repeated duplicate phrasing
    old_data = {"eligibility_rules": [r1, r2], "exclusion_rules": []}
    new_data = {"eligibility_rules": [r1], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    # Deduplication should reduce old to 1 rule, matching new perfectly
    assert len(res.rule_changes) == 1
    assert len(res.unchanged_rules) == 1
    assert len(res.added_rules) == 0
    assert len(res.removed_rules) == 0


# ==============================================================================
# TEST 16: More Restrictive Change
# ==============================================================================
def test_16_more_restrictive_change():
    old_rule = RuleItem(
        rule="Annual income must not exceed Rs. 3 lakh",
        type="eligibility",
        category="income",
        evidence=make_evidence("Annual income must not exceed Rs. 3 lakh"),
    )
    new_rule = RuleItem(
        rule="Annual income must not exceed Rs. 2 lakh",
        type="eligibility",
        category="income",
        evidence=make_evidence("Annual income must not exceed Rs. 2 lakh"),
    )
    old_data = {"eligibility_rules": [old_rule], "exclusion_rules": []}
    new_data = {"eligibility_rules": [new_rule], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.modified_rules) == 1
    mod = res.modified_rules[0]
    assert mod.change_type == "modified"
    assert mod.category == "income"
    assert mod.impact == "eligibility_more_restrictive"
    assert res.eligibility_relevance == "clearly_relevant"


# ==============================================================================
# TEST 17: Less Restrictive Change
# ==============================================================================
def test_17_less_restrictive_change():
    old_rule = RuleItem(
        rule="Applicant must be at least 21 years old",
        type="eligibility",
        category="age",
        evidence=make_evidence("Applicant must be at least 21 years old"),
    )
    new_rule = RuleItem(
        rule="Applicant must be at least 18 years old",
        type="eligibility",
        category="age",
        evidence=make_evidence("Applicant must be at least 18 years old"),
    )
    old_data = {"eligibility_rules": [old_rule], "exclusion_rules": []}
    new_data = {"eligibility_rules": [new_rule], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.modified_rules) == 1
    mod = res.modified_rules[0]
    assert mod.change_type == "modified"
    assert mod.category == "age"
    # Lowering minimum age from 21 to 18 expands eligibility -> less restrictive
    assert mod.impact == "eligibility_less_restrictive"
    assert res.eligibility_relevance == "clearly_relevant"


# ==============================================================================
# TEST 18: No Eligibility Rules in Either Version
# ==============================================================================
def test_18_no_eligibility_rules_in_either_version():
    old_data = {"eligibility_rules": [], "exclusion_rules": []}
    new_data = {"eligibility_rules": [], "exclusion_rules": []}

    res = compare_rules(old_data, new_data, save_output=False)

    assert len(res.rule_changes) == 0
    assert len(res.added_rules) == 0
    assert len(res.removed_rules) == 0
    assert len(res.modified_rules) == 0
    assert len(res.unchanged_rules) == 0
    assert res.eligibility_relevance == "none"
    assert "0 candidate eligibility" in res.summary
    assert res.comparison_metadata.deterministic_match is True
