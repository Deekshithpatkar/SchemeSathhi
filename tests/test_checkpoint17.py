"""
Checkpoint 17 Test Suite: Citizen Eligibility Evaluation Engine.

Covers all 24 test requirements from Section 17:
1. basic eligibility match
2. eligibility failure
3. exclusion match
4. unknown income
5. unknown land ownership
6. review-required rule
7. contradicted rule
8. insufficient evidence
9. beneficiary-limit handling
10. household information missing
11. multiple eligibility rules
12. multiple exclusions
13. active version selection
14. archived version ignored by default
15. historical version evaluation
16. zero-rule scheme
17. external knowledge rejection
18. evidence propagation
19. page-number propagation
20. source URL propagation
21. multi-scheme evaluation
22. deterministic decision without LLM
23. LLM normalization followed by deterministic validation
24. no assumptions for missing values
"""

import pytest
from app.schemas import RuleItem, SchemeEvidence
from app.citizen_profile import CitizenProfile, HouseholdMember, normalize_citizen_input
from app.eligibility_schemas import DecisionStatus, RuleEvaluationStatus
from app.eligibility_engine import (
    evaluate_rule,
    evaluate_scheme_eligibility,
    evaluate_citizen,
    evaluate_citizen_against_schemes,
)


# Helper: construct sample SchemeEvidence
def make_evidence(text: str = "Evidence text", kan: str = "ಕನ್ನಡ ಸಾಕ್ಷಿ", page: int = 1, url: str = "https://karnataka.gov.in/go.pdf") -> SchemeEvidence:
    return SchemeEvidence(
        page_number=page,
        source_text=text,
        original_kannada_evidence=kan,
        english_interpretation=text,
        source_url=url,
        ocr_confidence=90.0,
    )


# ==============================================================================
# 1. Basic eligibility match
# ==============================================================================
def test_01_basic_eligibility_match():
    rule = RuleItem(
        rule="The woman who is head of the family listed in the ration card is eligible.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        review_required=False,
        evidence=make_evidence(page=1),
    )
    citizen = CitizenProfile(
        gender="female",
        is_woman_head_of_household=True,
        household_head=True,
        listed_as_head_in_ration_card=True,
        ration_card_type="BPL",
    )
    res = evaluate_scheme_eligibility(citizen, [rule], scheme_name="Gruha Lakshmi")
    assert res.decision == DecisionStatus.ELIGIBLE
    assert len(res.eligibility_results) == 1
    assert res.eligibility_results[0].status == RuleEvaluationStatus.MATCH


# ==============================================================================
# 2. Eligibility failure
# ==============================================================================
def test_02_eligibility_failure():
    rule = RuleItem(
        rule="The woman who is head of the family listed in the ration card is eligible.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        review_required=False,
        evidence=make_evidence(page=1),
    )
    # Male applicant fails woman head criterion
    citizen = CitizenProfile(
        gender="male",
        is_woman_head_of_household=False,
        household_head=True,
        listed_as_head_in_ration_card=False,
    )
    res = evaluate_scheme_eligibility(citizen, [rule], scheme_name="Gruha Lakshmi")
    assert res.decision == DecisionStatus.NOT_ELIGIBLE
    assert res.eligibility_results[0].status == RuleEvaluationStatus.NO_MATCH


# ==============================================================================
# 3. Exclusion match
# ==============================================================================
def test_03_exclusion_match():
    elig_rule = RuleItem(
        rule="Candidate is a resident of Karnataka.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        review_required=False,
        evidence=make_evidence(page=1),
    )
    excl_rule = RuleItem(
        rule="Students who have failed or are repeating a semester/academic year are not eligible.",
        type="exclusion",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        review_required=False,
        evidence=make_evidence(page=3),
    )
    citizen = CitizenProfile(
        state="Karnataka",
        is_karnataka_resident=True,
        failed_semester=True,
        repeating_year=False,
    )
    res = evaluate_scheme_eligibility(citizen, [elig_rule, excl_rule], scheme_name="CM Raitha Vidyanidhi")
    assert res.decision == DecisionStatus.NOT_ELIGIBLE
    assert any(e.status == RuleEvaluationStatus.MATCH for e in res.exclusion_results)


# ==============================================================================
# 4. Unknown income
# ==============================================================================
def test_04_unknown_income():
    rule = RuleItem(
        rule="Annual family income must not exceed ₹2,50,000.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        review_required=False,
        evidence=make_evidence(page=2),
    )
    citizen = CitizenProfile(annual_income=None, income=None)
    res = evaluate_scheme_eligibility(citizen, [rule], scheme_name="Scholarship Scheme")
    assert res.decision == DecisionStatus.NEEDS_REVIEW
    assert res.eligibility_results[0].status == RuleEvaluationStatus.UNKNOWN
    assert any("income" in m.lower() for m in res.missing_information)


# ==============================================================================
# 5. Unknown land ownership
# ==============================================================================
def test_05_unknown_land_ownership():
    rule = RuleItem(
        rule="Applicant must own agricultural land.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        review_required=False,
        evidence=make_evidence(page=2),
    )
    citizen = CitizenProfile(owns_agricultural_land=None, landholding_acres=None)
    res = evaluate_scheme_eligibility(citizen, [rule], scheme_name="Farmer Welfare Scheme")
    assert res.decision == DecisionStatus.NEEDS_REVIEW
    assert res.eligibility_results[0].status == RuleEvaluationStatus.UNKNOWN
    assert any("land" in m.lower() for m in res.missing_information)


# ==============================================================================
# 6. Review-required rule
# ==============================================================================
def test_06_review_required_rule():
    rule = RuleItem(
        rule="Individuals who are taxpayers (tax payers) are disqualified from availing the scheme.",
        type="exclusion",
        rule_scope="candidate",
        evidence_consistency_status="REVIEW_REQUIRED",
        review_required=True,
        semantic_validation_reason="Scope Generalization: Rule asserts general income tax disqualification but evidence specifically states GST returns.",
        evidence=make_evidence(page=2),
    )
    elig_rule = RuleItem(
        rule="Woman head of family is eligible.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        review_required=False,
        evidence=make_evidence(page=1),
    )
    citizen = CitizenProfile(
        gender="female",
        is_woman_head_of_household=True,
        household_head=True,
        listed_as_head_in_ration_card=True,
        income_tax_payer=True,
    )
    res = evaluate_scheme_eligibility(citizen, [elig_rule, rule], scheme_name="Gruha Lakshmi")
    # Must NOT use the questionable exclusion rule to disqualify the citizen; triggers NEEDS_REVIEW
    assert res.decision == DecisionStatus.NEEDS_REVIEW
    assert any("review" in r.lower() for r in res.review_reasons)


# ==============================================================================
# 7. Contradicted rule
# ==============================================================================
def test_07_contradicted_rule():
    # CM Raitha landowner/landless contradiction
    contra_rule = RuleItem(
        rule="Farmers' children are eligible for the scholarship if both their parents are landless farmers.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="CONTRADICTED",
        review_required=True,
        semantic_validation_reason="Semantic Inversion detected: Rule claims 'landless' but Kannada evidence specifies 'ಜಮೀನಿನ ಒಡೆಯ' (land owner).",
        evidence=make_evidence(page=3),
    )
    citizen = CitizenProfile(owns_agricultural_land=True)
    res = evaluate_scheme_eligibility(citizen, [contra_rule], scheme_name="CM Raitha Vidyanidhi")
    assert res.decision == DecisionStatus.NEEDS_REVIEW
    # Quarantined rule must not produce definitive decision
    assert res.decision != DecisionStatus.ELIGIBLE
    assert res.decision != DecisionStatus.NOT_ELIGIBLE


# ==============================================================================
# 8. Insufficient evidence
# ==============================================================================
def test_08_insufficient_evidence():
    rule = RuleItem(
        rule="Special incentive for applicants.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="INSUFFICIENT",
        review_required=True,
        evidence=make_evidence(text="short", kan="short"),
    )
    citizen = CitizenProfile()
    res = evaluate_scheme_eligibility(citizen, [rule], scheme_name="Incentive Scheme")
    assert res.decision == DecisionStatus.NEEDS_REVIEW


# ==============================================================================
# 9. Beneficiary-limit handling
# ==============================================================================
def test_09_beneficiary_limit_handling():
    elig_rule = RuleItem(
        rule="The woman who is head of the family listed in the ration card is eligible.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        review_required=False,
        evidence=make_evidence(page=1),
    )
    limit_rule = RuleItem(
        rule="Only one woman per household is eligible for the scheme.",
        type="eligibility",
        rule_scope="beneficiary_limit",
        evidence_consistency_status="SUPPORTED",
        review_required=False,
        evidence=make_evidence(page=2),
    )
    # Household already has another woman who claimed the benefit
    citizen = CitizenProfile(
        gender="female",
        is_woman_head_of_household=True,
        household_head=True,
        listed_as_head_in_ration_card=True,
        household_members=[
            HouseholdMember(member_id="M1", relationship="self", gender="female"),
            HouseholdMember(member_id="M2", relationship="sister", gender="female", already_received_benefit=True),
        ],
    )
    res = evaluate_scheme_eligibility(citizen, [elig_rule, limit_rule], scheme_name="Gruha Lakshmi")
    assert res.decision == DecisionStatus.NOT_ELIGIBLE
    assert any("limit" in r.reason.lower() for r in res.household_results)


# ==============================================================================
# 10. Household information missing
# ==============================================================================
def test_10_household_information_missing():
    elig_rule = RuleItem(
        rule="The woman who is head of the family listed in the ration card is eligible.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        review_required=False,
        evidence=make_evidence(page=1),
    )
    limit_rule = RuleItem(
        rule="Only one woman per household is eligible for the scheme.",
        type="eligibility",
        rule_scope="beneficiary_limit",
        evidence_consistency_status="SUPPORTED",
        review_required=False,
        evidence=make_evidence(page=2),
    )
    citizen = CitizenProfile(
        gender="female",
        is_woman_head_of_household=True,
        household_head=True,
        listed_as_head_in_ration_card=True,
        household_members=None,  # Missing household members!
    )
    res = evaluate_scheme_eligibility(citizen, [elig_rule, limit_rule], scheme_name="Gruha Lakshmi")
    assert res.decision == DecisionStatus.NEEDS_REVIEW
    assert any("household" in m.lower() for m in res.missing_information)


# ==============================================================================
# 11. Multiple eligibility rules
# ==============================================================================
def test_11_multiple_eligibility_rules():
    r1 = RuleItem(
        rule="Applicant must be a resident of Karnataka.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        evidence=make_evidence(),
    )
    r2 = RuleItem(
        rule="Annual family income must not exceed ₹2,50,000.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        evidence=make_evidence(),
    )
    # Case A: Both pass
    c_pass = CitizenProfile(state="Karnataka", annual_income=150000)
    assert evaluate_scheme_eligibility(c_pass, [r1, r2], "Scheme").decision == DecisionStatus.ELIGIBLE

    # Case B: One fails
    c_fail = CitizenProfile(state="Karnataka", annual_income=350000)
    assert evaluate_scheme_eligibility(c_fail, [r1, r2], "Scheme").decision == DecisionStatus.NOT_ELIGIBLE

    # Case C: One unknown
    c_unk = CitizenProfile(state="Karnataka", annual_income=None)
    assert evaluate_scheme_eligibility(c_unk, [r1, r2], "Scheme").decision == DecisionStatus.NEEDS_REVIEW


# ==============================================================================
# 12. Multiple exclusions
# ==============================================================================
def test_12_multiple_exclusions():
    elig = RuleItem(
        rule="Applicant is a resident of Karnataka.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        evidence=make_evidence(),
    )
    e1 = RuleItem(
        rule="Students who have failed or are repeating a semester/academic year are not eligible.",
        type="exclusion",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        evidence=make_evidence(),
    )
    e2 = RuleItem(
        rule="Students who have already completed a higher education course are not eligible.",
        type="exclusion",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        evidence=make_evidence(),
    )
    # Neither triggered -> ELIGIBLE
    c_clean = CitizenProfile(
        state="Karnataka",
        failed_semester=False,
        repeating_year=False,
        already_completed_equivalent_or_higher_course=False,
    )
    assert evaluate_scheme_eligibility(c_clean, [elig, e1, e2], "CM Raitha").decision == DecisionStatus.ELIGIBLE

    # Second exclusion triggered -> NOT_ELIGIBLE
    c_dup = CitizenProfile(
        state="Karnataka",
        failed_semester=False,
        repeating_year=False,
        already_completed_equivalent_or_higher_course=True,
    )
    assert evaluate_scheme_eligibility(c_dup, [elig, e1, e2], "CM Raitha").decision == DecisionStatus.NOT_ELIGIBLE


# ==============================================================================
# 13. Active version selection
# ==============================================================================
def test_13_active_version_selection():
    citizen = CitizenProfile(gender="female", is_woman_head_of_household=True, listed_as_head_in_ration_card=True)
    res = evaluate_citizen(citizen, scheme_key="gruha-lakshmi")
    assert res.version_status == "ACTIVE"


# ==============================================================================
# 14. Archived version ignored by default
# ==============================================================================
def test_14_archived_version_ignored_by_default(monkeypatch):
    from app import eligibility_engine

    def mock_load(scheme_key, version_label=None):
        return [], "Test Scheme", "2021-v1", "ARCHIVED"

    monkeypatch.setattr(eligibility_engine, "load_scheme_rules", mock_load)
    citizen = CitizenProfile()
    res = evaluate_citizen(citizen, "test-scheme")
    assert res.decision == DecisionStatus.NEEDS_REVIEW
    assert "ARCHIVED" in res.summary


# ==============================================================================
# 15. Historical version evaluation
# ==============================================================================
def test_15_historical_version_evaluation(monkeypatch):
    from app import eligibility_engine

    rule = RuleItem(
        rule="Resident of Karnataka.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        evidence=make_evidence(),
    )

    def mock_load(scheme_key, version_label=None):
        if version_label == "2023-historical":
            return [rule], "Past Scheme", "2023-historical", "ARCHIVED"
        return [], "Past Scheme", "2024-active", "ACTIVE"

    monkeypatch.setattr(eligibility_engine, "load_scheme_rules", mock_load)
    citizen = CitizenProfile(state="Karnataka")
    res = evaluate_citizen(citizen, "test-scheme", version_label="2023-historical")
    assert res.decision == DecisionStatus.ELIGIBLE
    assert res.version_label == "2023-historical"


# ==============================================================================
# 16. Zero-rule scheme
# ==============================================================================
def test_16_zero_rule_scheme():
    # Secondary Agriculture contains 0 candidate rules
    citizen = CitizenProfile(state="Karnataka", annual_income=100000)
    res = evaluate_citizen(citizen, scheme_key="secondary-agriculture")
    assert res.decision == DecisionStatus.NEEDS_REVIEW
    assert "0" in res.summary or "No trusted candidate eligibility rules" in res.summary


# ==============================================================================
# 17. External knowledge rejection
# ==============================================================================
def test_17_external_knowledge_rejection():
    # PM-KISAN Karnataka Top-Up must NOT import external national 2-hectare rule
    citizen = CitizenProfile(owns_agricultural_land=True, landholding_acres=5.0)
    res = evaluate_citizen(citizen, scheme_key="pm-kisan-karnataka")
    assert res.decision == DecisionStatus.NEEDS_REVIEW
    # Zero candidate rules -> NEEDS_REVIEW, no external rule used to accept or reject
    assert len(res.eligibility_results) == 0


# ==============================================================================
# 18. Evidence propagation
# ==============================================================================
def test_18_evidence_propagation():
    ev_text = "ಕುಟುಂಬದ ಯಜಮಾನಿ ಮಹಿಳೆಯು ಅರ್ಹ ಫಲಾನುಭವಿ"
    rule = RuleItem(
        rule="Woman head of family is eligible.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        evidence=make_evidence(text=ev_text, kan=ev_text, page=1),
    )
    citizen = CitizenProfile(gender="female", is_woman_head_of_household=True, listed_as_head_in_ration_card=True)
    res = evaluate_scheme_eligibility(citizen, [rule], "Scheme")
    assert len(res.evidence) >= 1
    assert res.evidence[0]["original_kannada_evidence"] == ev_text


# ==============================================================================
# 19. Page-number propagation
# ==============================================================================
def test_19_page_number_propagation():
    rule = RuleItem(
        rule="Students who failed are not eligible.",
        type="exclusion",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        evidence=make_evidence(page=4),
    )
    citizen = CitizenProfile(failed_semester=True)
    res = evaluate_scheme_eligibility(citizen, [rule], "Scheme")
    assert res.exclusion_results[0].page_number == 4
    assert res.evidence[0]["page_number"] == 4


# ==============================================================================
# 20. Source URL propagation
# ==============================================================================
def test_20_source_url_propagation():
    url = "https://karnataka.gov.in/orders/gruha_lakshmi.pdf"
    rule = RuleItem(
        rule="Resident of Karnataka.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        evidence=make_evidence(url=url),
    )
    citizen = CitizenProfile(state="Karnataka")
    res = evaluate_scheme_eligibility(citizen, [rule], "Scheme")
    assert res.eligibility_results[0].source_url == url
    assert res.evidence[0]["source_url"] == url


# ==============================================================================
# 21. Multi-scheme evaluation
# ==============================================================================
def test_21_multi_scheme_evaluation():
    citizen = CitizenProfile(
        gender="female",
        is_woman_head_of_household=True,
        listed_as_head_in_ration_card=True,
        state="Karnataka",
        household_members=[HouseholdMember(relationship="self", gender="female")],
    )
    results = evaluate_citizen_against_schemes(citizen, ["gruha-lakshmi", "secondary-agriculture"])
    assert "gruha-lakshmi" in results
    assert "secondary-agriculture" in results
    assert results["gruha-lakshmi"].decision in (DecisionStatus.ELIGIBLE, DecisionStatus.NEEDS_REVIEW)
    assert results["secondary-agriculture"].decision == DecisionStatus.NEEDS_REVIEW


# ==============================================================================
# 22. Deterministic decision without LLM
# ==============================================================================
def test_22_deterministic_decision_without_llm():
    # Calling evaluate_rule or evaluate_scheme_eligibility directly operates purely on Python logic
    rule = RuleItem(
        rule="Annual family income must not exceed ₹2,00,000.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        evidence=make_evidence(),
    )
    c1 = CitizenProfile(annual_income=180000)
    c2 = CitizenProfile(annual_income=220000)

    # 100% deterministic repeat evaluations
    for _ in range(5):
        assert evaluate_rule(rule, c1).status == RuleEvaluationStatus.MATCH
        assert evaluate_rule(rule, c2).status == RuleEvaluationStatus.NO_MATCH


# ==============================================================================
# 23. LLM normalization followed by deterministic validation
# ==============================================================================
def test_23_llm_normalization_followed_by_deterministic_validation():
    # User input "I earn around 20k a month"
    profile = normalize_citizen_input("I earn around 20k a month and live in Karnataka")
    assert profile.income == 20000.0
    assert profile.annual_income == 240000.0
    assert profile.state == "Karnataka"

    # Evaluated deterministically
    rule = RuleItem(
        rule="Annual income must not exceed ₹2,50,000.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        evidence=make_evidence(),
    )
    res = evaluate_rule(rule, profile)
    assert res.status == RuleEvaluationStatus.MATCH
    assert res.matched is True


# ==============================================================================
# 24. No assumptions for missing values
# ==============================================================================
def test_24_no_assumptions_for_missing_values():
    # Empty profile: all fields None
    blank_citizen = CitizenProfile()
    assert blank_citizen.income is None
    assert blank_citizen.annual_income is None
    assert blank_citizen.owns_agricultural_land is None
    assert blank_citizen.gender is None
    assert blank_citizen.failed_semester is None

    rule_land = RuleItem(
        rule="Applicant must own agricultural land.",
        type="eligibility",
        rule_scope="candidate",
        evidence_consistency_status="SUPPORTED",
        evidence=make_evidence(),
    )
    res = evaluate_rule(rule_land, blank_citizen)
    # Must NOT assume False -> must return UNKNOWN
    assert res.status == RuleEvaluationStatus.UNKNOWN
    assert res.matched is None
