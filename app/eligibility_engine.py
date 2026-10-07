"""
Checkpoint 17: Citizen Eligibility Evaluation Engine.

Provides deterministic, evidence-grounded evaluation of citizen profiles
against Karnataka government scheme rules from the grounded knowledge base.

Key Invariants:
1. Deterministic Python logic: The final decision (ELIGIBLE / NOT_ELIGIBLE / NEEDS_REVIEW)
   is computed exclusively by deterministic rule evaluation, NEVER by an LLM.
2. Unknown != False: Missing profile attributes (None) are treated as UNKNOWN,
   never assumed to be False, 0, or arbitrary values.
3. Strict Grounding & Rule Trust:
   - Only rules with evidence_consistency_status == "SUPPORTED" and review_required == False
     are treated as trusted decision rules.
   - Rules marked CONTRADICTED, REVIEW_REQUIRED, or INSUFFICIENT cannot produce definitive decisions;
     they trigger NEEDS_REVIEW.
4. Scope Partitioning:
   - Candidate-level rules directly determine individual citizen qualification.
   - Beneficiary limit and household rules are evaluated separately based on household details.
   - Administrative procedural rules are ignored for eligibility predicates.
5. No Trusted Rules = NEEDS_REVIEW: Schemes with zero trusted eligibility rules
   (such as administrative orders or funding tables) yield NEEDS_REVIEW, never ELIGIBLE.
6. Evidence Traceability: Every decision preserves original Kannada evidence, page numbers,
   and source URLs.
"""

import re
import json
from pathlib import Path
from typing import Optional, List, Dict, Any, Union, Tuple

from app.config import setup_logger, EXTRACTED_RULES_DIR
from app.schemas import RuleItem, SchemeEvidence, SchemeExtraction
from app.citizen_profile import CitizenProfile, HouseholdMember
from app.eligibility_schemas import (
    DecisionStatus,
    RuleEvaluationStatus,
    RuleEvaluationResult,
    EligibilityResult,
)
from app.versioning import make_slug

logger = setup_logger("eligibility_engine")


# ==============================================================================
# 1. Deterministic Parsing & Value Extractors
# ==============================================================================

def parse_monetary_amount(text: str) -> Optional[float]:
    """
    Extracts monetary INR amounts from strings like '₹2,50,000', 'Rs. 2.5 lakh', '2000/month'.
    """
    text_clean = text.lower().replace(",", "")

    # Look for 'lakh' or 'lac'
    lakh_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac|ಲಕ್ಷ)", text_clean)
    if lakh_match:
        try:
            return float(lakh_match.group(1)) * 100000.0
        except ValueError:
            pass

    # Look for raw digit amounts >= 100
    amt_match = re.search(r"(?:rs\.?|₹|inr|ರೂ\.?)\s*(\d+)", text_clean)
    if amt_match:
        try:
            return float(amt_match.group(1))
        except ValueError:
            pass

    # Fallback to standalone large numbers
    num_match = re.search(r"\b(\d{4,8})\b", text_clean)
    if num_match:
        try:
            return float(num_match.group(1))
        except ValueError:
            pass

    return None


def parse_numeric_threshold(text: str) -> Optional[float]:
    """Extracts first valid numeric threshold from text."""
    nums = re.findall(r"\b\d+(?:\.\d+)?\b", text.replace(",", ""))
    for n in nums:
        try:
            val = float(n)
            # Filter out years like 2021, 2022, 2023, 2024
            if val not in (2020, 2021, 2022, 2023, 2024, 2025, 2026):
                return val
        except ValueError:
            continue
    return None


# ==============================================================================
# 2. Deterministic Rule Evaluator
# ==============================================================================

def evaluate_rule(rule: RuleItem, citizen: CitizenProfile) -> RuleEvaluationResult:
    """
    Deterministically evaluates a single scheme rule against a citizen profile.
    Distinguishes TRUE (MATCH), FALSE (NO_MATCH), and UNKNOWN.
    """
    ev = rule.evidence
    kannada_ev = (ev.original_kannada_evidence or ev.source_text or "") if ev else ""
    page_num = ev.page_number if ev else None
    source_url = ev.source_url if ev else None
    consistency_status = getattr(rule, "evidence_consistency_status", "SUPPORTED") or "SUPPORTED"
    sem_conf = getattr(ev, "semantic_validation_confidence", 1.0) or 1.0

    result = RuleEvaluationResult(
        rule=rule.rule,
        rule_type=rule.type or "eligibility",
        rule_scope=rule.rule_scope or "candidate",
        evidence=ev.source_text if ev else None,
        original_kannada_evidence=kannada_ev,
        english_interpretation=ev.english_interpretation if ev else None,
        page_number=page_num,
        source_url=source_url,
        confidence=rule.semantic_confidence or 0.85,
        review_required=bool(rule.review_required),
        evidence_consistency_status=consistency_status,
        semantic_validation_confidence=sem_conf,
    )

    # 1. Administrative Scope Check
    if rule.rule_scope == "administrative":
        result.status = RuleEvaluationStatus.NOT_APPLICABLE
        result.matched = None
        result.reason = "Administrative procedural instruction; not an individual eligibility predicate."
        return result

    # 2. Rule Trust Check: Quarantined / Contradicted / Review-Required Rules
    if consistency_status != "SUPPORTED" or rule.review_required:
        result.status = RuleEvaluationStatus.REVIEW_REQUIRED
        result.matched = None
        result.review_required = True
        status_reason = getattr(rule, "semantic_validation_reason", None) or "Rule is flagged for review."
        result.reason = f"Rule is quarantined ({consistency_status}): {status_reason} Cannot produce a definitive eligibility decision."
        return result

    rule_text = (rule.rule or "").lower()

    # 3. Beneficiary Limit / Household Scope Check
    if rule.rule_scope == "beneficiary_limit" or any(k in rule_text for k in ["one woman per household", "one per household", "one per family"]):
        return _evaluate_beneficiary_limit(rule, citizen, result)

    # 4. Specific Predicate Evaluators

    # A. Gruha Lakshmi Woman Head of Household & Ration Card Rule
    if any(k in rule_text for k in ["head of the family", "woman who is the head", "ಕುಟುಂಬದ ಯಜಮಾನಿ", "ration card"]):
        return _evaluate_woman_head_rule(rule, citizen, result)

    # B. Income & Financial Thresholds
    if any(k in rule_text for k in ["income", "annual income", "salary", "earnings", "ಆದಾಯ"]):
        return _evaluate_income_rule(rule, citizen, result)

    # C. Agricultural Land Ownership / Landless Condition
    if any(k in rule_text for k in ["agricultural land", "owns land", "landowner", "landless", "ಕೃಷಿ ಜಮೀನು", "ಹಿಡುವಳಿ"]):
        return _evaluate_land_rule(rule, citizen, result)

    # D. Academic Failure / Repetition Exclusion (CM Raitha)
    if any(k in rule_text for k in ["failed", "failing", "repeat", "repeating", "ಅನುತ್ತೀರ್ಣ", "ಪುನರಾವರ್ತನೆ"]):
        return _evaluate_student_failure_rule(rule, citizen, result)

    # E. Completed Higher Course / Duplicate Degree Exclusion (CM Raitha)
    if any(k in rule_text for k in ["completed a higher education", "already completed a course", "different course", "ಸ್ನಾತಕೋತ್ತರ"]):
        return _evaluate_completed_course_rule(rule, citizen, result)

    # F. Taxpayer / GST Return Filer
    if any(k in rule_text for k in ["taxpayer", "tax payers", "income tax", "gst", "ಜಿಎಸ್‌ಟಿ"]):
        return _evaluate_tax_rule(rule, citizen, result)

    # G. Residency / State Condition
    if any(k in rule_text for k in ["resident", "karnataka", "ವಾಸ"]):
        return _evaluate_residency_rule(rule, citizen, result)

    # H. Fallback Generic Attribute Matcher
    return _evaluate_generic_rule(rule, citizen, result)


# ==============================================================================
# 3. Specialized Rule Predicate Matchers
# ==============================================================================

def _evaluate_woman_head_rule(rule: RuleItem, citizen: CitizenProfile, res: RuleEvaluationResult) -> RuleEvaluationResult:
    # Check gender first if known
    if citizen.gender is not None and citizen.gender.lower() not in ("female", "woman"):
        res.status = RuleEvaluationStatus.NO_MATCH
        res.matched = False
        res.reason = f"Citizen gender is '{citizen.gender}', scheme requires woman head of household."
        return res

    is_head = citizen.is_woman_head_of_household
    if is_head is None and citizen.household_head is not None:
        is_head = citizen.household_head and (citizen.gender or "").lower() == "female"

    card_listed = citizen.listed_as_head_in_ration_card

    # Check ration card category if specified (Antyodaya, BPL, APL)
    card_type = (citizen.ration_card_type or "").upper()
    has_valid_card = None
    if card_type:
        has_valid_card = card_type in ("BPL", "APL", "ANTYODAYA", "AAY")

    # If any mandatory attribute is unknown -> UNKNOWN
    if is_head is None or card_listed is None:
        missing = []
        if is_head is None:
            missing.append("household head status")
        if card_listed is None:
            missing.append("listed as head in ration card")
        if citizen.gender is None:
            missing.append("gender")
        res.status = RuleEvaluationStatus.UNKNOWN
        res.matched = None
        res.reason = f"Required information unknown: {', '.join(missing)}."
        return res

    if is_head and card_listed and (has_valid_card is None or has_valid_card is True):
        res.status = RuleEvaluationStatus.MATCH
        res.matched = True
        res.reason = "Citizen is confirmed as woman head of family listed in ration card."
    else:
        res.status = RuleEvaluationStatus.NO_MATCH
        res.matched = False
        reasons = []
        if not is_head:
            reasons.append("not head of family")
        if not card_listed:
            reasons.append("not listed as head in ration card")
        if has_valid_card is False:
            reasons.append(f"ineligible ration card type '{card_type}'")
        res.reason = f"Citizen does not satisfy criteria: {', '.join(reasons)}."

    return res


def _evaluate_income_rule(rule: RuleItem, citizen: CitizenProfile, res: RuleEvaluationResult) -> RuleEvaluationResult:
    thresh = parse_monetary_amount(rule.rule)
    if thresh is None:
        thresh = parse_numeric_threshold(rule.rule)

    eff_income = citizen.get_effective_annual_income()
    if eff_income is None:
        res.status = RuleEvaluationStatus.UNKNOWN
        res.matched = None
        res.reason = "Annual income is unknown (not specified in citizen profile)."
        return res

    if thresh is None:
        res.status = RuleEvaluationStatus.UNKNOWN
        res.matched = None
        res.reason = "Could not parse numerical income threshold from scheme rule."
        return res

    is_le = any(k in rule.rule.lower() for k in ["<=", "less than", "up to", "not exceed", "maximum", "within"])
    if is_le:
        meets = eff_income <= thresh
    else:
        meets = eff_income <= thresh  # Default welfare income cap interpretation

    if rule.type == "exclusion":
        # For exclusion: matching means disqualified
        res.matched = not meets if is_le else meets
        res.status = RuleEvaluationStatus.MATCH if res.matched else RuleEvaluationStatus.NO_MATCH
        res.reason = f"Annual income ₹{eff_income:,.0f} {'triggers' if res.matched else 'does not trigger'} income exclusion threshold ₹{thresh:,.0f}."
    else:
        res.matched = meets
        res.status = RuleEvaluationStatus.MATCH if meets else RuleEvaluationStatus.NO_MATCH
        res.reason = f"Annual income ₹{eff_income:,.0f} {'satisfies' if meets else 'exceeds'} required income limit ₹{thresh:,.0f}."

    return res


def _evaluate_land_rule(rule: RuleItem, citizen: CitizenProfile, res: RuleEvaluationResult) -> RuleEvaluationResult:
    rule_lower = rule.rule.lower()
    requires_landless = "landless" in rule_lower or "without land" in rule_lower
    requires_ownership = not requires_landless

    owns_land = citizen.owns_agricultural_land
    if owns_land is None and citizen.landholding_acres is not None:
        owns_land = citizen.landholding_acres > 0.0

    if owns_land is None:
        res.status = RuleEvaluationStatus.UNKNOWN
        res.matched = None
        res.reason = "Agricultural land ownership information is unknown."
        return res

    if requires_ownership:
        matched = owns_land is True
        res.matched = matched
        res.status = RuleEvaluationStatus.MATCH if matched else RuleEvaluationStatus.NO_MATCH
        res.reason = f"Citizen {'owns' if owns_land else 'does not own'} agricultural land as required."
    else:
        matched = owns_land is False
        res.matched = matched
        res.status = RuleEvaluationStatus.MATCH if matched else RuleEvaluationStatus.NO_MATCH
        res.reason = f"Citizen is {'landless' if not owns_land else 'a landowner (fails landless requirement)'}."

    return res


def _evaluate_student_failure_rule(rule: RuleItem, citizen: CitizenProfile, res: RuleEvaluationResult) -> RuleEvaluationResult:
    failed = citizen.failed_semester
    repeating = citizen.repeating_year

    if failed is None and repeating is None:
        res.status = RuleEvaluationStatus.UNKNOWN
        res.matched = None
        res.reason = "Academic pass/fail or course repetition status is unknown."
        return res

    is_failing_or_repeating = bool(failed or repeating)

    # Since this is an exclusion rule, MATCH means candidate triggers the exclusion
    res.matched = is_failing_or_repeating
    res.status = RuleEvaluationStatus.MATCH if is_failing_or_repeating else RuleEvaluationStatus.NO_MATCH
    if is_failing_or_repeating:
        reasons = []
        if failed:
            reasons.append("failed semester")
        if repeating:
            reasons.append("repeating academic year")
        res.reason = f"Citizen triggers exclusion: {', '.join(reasons)}."
    else:
        res.reason = "Citizen has not failed or repeated semester; exclusion does not apply."

    return res


def _evaluate_completed_course_rule(rule: RuleItem, citizen: CitizenProfile, res: RuleEvaluationResult) -> RuleEvaluationResult:
    completed_higher = citizen.already_completed_equivalent_or_higher_course

    # If explicit boolean is provided
    if completed_higher is not None:
        res.matched = completed_higher
        res.status = RuleEvaluationStatus.MATCH if completed_higher else RuleEvaluationStatus.NO_MATCH
        res.reason = "Citizen has already completed an equivalent or higher course." if completed_higher else "Citizen has not completed an equivalent/higher course."
        return res

    # Check course levels if strings provided
    prev = (citizen.previous_course or "").lower()
    curr = (citizen.current_course or "").lower()
    if prev and curr:
        pg_terms = ["postgraduate", "master", "msc", "m.sc", "ma", "m.a", "mtech", "mba", "ಸ್ನಾತಕೋತ್ತರ"]
        is_prev_pg = any(p in prev for p in pg_terms)
        is_curr_pg = any(c in curr for c in pg_terms)
        if is_prev_pg and is_curr_pg:
            res.matched = True
            res.status = RuleEvaluationStatus.MATCH
            res.reason = f"Citizen completed '{prev}' and is pursuing duplicate course '{curr}'."
            return res
        else:
            res.matched = False
            res.status = RuleEvaluationStatus.NO_MATCH
            res.reason = f"Citizen course history ('{prev}' -> '{curr}') does not trigger duplicate course exclusion."
            return res

    res.status = RuleEvaluationStatus.UNKNOWN
    res.matched = None
    res.reason = "Previous higher education course completion status is unknown."
    return res


def _evaluate_tax_rule(rule: RuleItem, citizen: CitizenProfile, res: RuleEvaluationResult) -> RuleEvaluationResult:
    is_taxpayer = citizen.income_tax_payer
    is_gst = citizen.gst_return_filer if citizen.gst_return_filer is not None else citizen.gst_registered
    spouse_gst = citizen.spouse_is_gst_filer

    rule_lower = rule.rule.lower()
    checks_gst = "gst" in rule_lower or "ಜಿಎಸ್‌ಟಿ" in rule_lower

    if checks_gst:
        if is_gst is None and spouse_gst is None:
            res.status = RuleEvaluationStatus.UNKNOWN
            res.matched = None
            res.reason = "GST return filing status for self or spouse is unknown."
            return res
        disqualified = bool(is_gst or spouse_gst)
    else:
        if is_taxpayer is None:
            res.status = RuleEvaluationStatus.UNKNOWN
            res.matched = None
            res.reason = "Income tax payer status is unknown."
            return res
        disqualified = bool(is_taxpayer)

    res.matched = disqualified
    res.status = RuleEvaluationStatus.MATCH if disqualified else RuleEvaluationStatus.NO_MATCH
    res.reason = f"Citizen {'triggers' if disqualified else 'does not trigger'} tax/GST disqualification condition."
    return res


def _evaluate_residency_rule(rule: RuleItem, citizen: CitizenProfile, res: RuleEvaluationResult) -> RuleEvaluationResult:
    if citizen.is_karnataka_resident is not None:
        is_res = citizen.is_karnataka_resident
    elif citizen.state is not None:
        is_res = "karnataka" in citizen.state.lower()
    else:
        is_res = None

    if is_res is None:
        res.status = RuleEvaluationStatus.UNKNOWN
        res.matched = None
        res.reason = "Karnataka residency / state information is unknown."
        return res

    res.matched = is_res
    res.status = RuleEvaluationStatus.MATCH if is_res else RuleEvaluationStatus.NO_MATCH
    res.reason = f"Citizen {'is' if is_res else 'is not'} a resident of Karnataka."
    return res


def _evaluate_beneficiary_limit(rule: RuleItem, citizen: CitizenProfile, res: RuleEvaluationResult) -> RuleEvaluationResult:
    """
    Evaluates household-level beneficiary limits (e.g. max 1 woman per household).
    """
    if not citizen.has_household_info():
        # Household info is missing
        res.status = RuleEvaluationStatus.UNKNOWN
        res.matched = None
        res.review_required = True
        res.reason = "Household member details not provided; cannot verify whether another household member has already claimed the benefit."
        return res

    members = citizen.household_members or []
    # Count other members who have already claimed the benefit
    prior_claimants = [m for m in members if m.relationship != "self" and m.already_received_benefit is True]
    if prior_claimants:
        res.status = RuleEvaluationStatus.NO_MATCH
        res.matched = False
        res.reason = f"Beneficiary limit reached: {len(prior_claimants)} other member(s) in household already received benefit."
    else:
        res.status = RuleEvaluationStatus.MATCH
        res.matched = True
        res.reason = "Beneficiary quota available in household (no other member has claimed the benefit)."

    return res


def _evaluate_generic_rule(rule: RuleItem, citizen: CitizenProfile, res: RuleEvaluationResult) -> RuleEvaluationResult:
    """Fallback evaluator for rules without specific domain hooks."""
    res.status = RuleEvaluationStatus.UNKNOWN
    res.matched = None
    res.reason = f"No automated deterministic predicate evaluator available for rule: '{rule.rule[:60]}'."
    return res


# ==============================================================================
# 4. Master Decision Synthesis Engine
# ==============================================================================

def evaluate_scheme_eligibility(
    citizen: CitizenProfile,
    rules: List[RuleItem],
    scheme_name: str,
    scheme_key: str = "",
    version_label: Optional[str] = None,
    version_status: Optional[str] = "ACTIVE",
) -> EligibilityResult:
    """
    Evaluates a citizen against a full set of scheme rules and produces
    ELIGIBLE, NOT_ELIGIBLE, or NEEDS_REVIEW.
    """
    scheme_slug = scheme_key or make_slug(scheme_name)
    result = EligibilityResult(
        scheme_key=scheme_slug,
        scheme_name=scheme_name,
        citizen_identifier=citizen.citizen_id or citizen.name,
        decision=DecisionStatus.NEEDS_REVIEW,
        summary="",
        version_label=version_label,
        version_status=version_status,
    )

    # Filter candidate rules vs beneficiary/household limits vs administrative (ignoring blank rules)
    candidate_elig_rules = [r for r in rules if (r.type or "").lower() == "eligibility" and (r.rule_scope or "candidate") == "candidate" and (r.rule or "").strip()]
    candidate_excl_rules = [r for r in rules if (r.type or "").lower() == "exclusion" and (r.rule_scope or "candidate") == "candidate" and (r.rule or "").strip()]
    household_rules = [r for r in rules if (r.rule_scope or "") in ("household", "beneficiary_limit") and (r.rule or "").strip()]

    # 1. Evaluate candidate exclusion rules first
    disqualified_by: List[RuleEvaluationResult] = []
    unknown_exclusions: List[RuleEvaluationResult] = []
    review_exclusions: List[RuleEvaluationResult] = []

    for r in candidate_excl_rules:
        eval_res = evaluate_rule(r, citizen)
        result.exclusion_results.append(eval_res)
        if eval_res.evidence:
            result.evidence.append({
                "rule": eval_res.rule,
                "type": "exclusion",
                "evidence": eval_res.evidence,
                "original_kannada_evidence": eval_res.original_kannada_evidence,
                "page_number": eval_res.page_number,
                "source_url": eval_res.source_url,
            })

        if eval_res.status == RuleEvaluationStatus.MATCH:
            disqualified_by.append(eval_res)
        elif eval_res.status == RuleEvaluationStatus.UNKNOWN:
            unknown_exclusions.append(eval_res)
        elif eval_res.status == RuleEvaluationStatus.REVIEW_REQUIRED:
            review_exclusions.append(eval_res)

    # If any trusted exclusion definitely matched -> NOT_ELIGIBLE immediately
    if disqualified_by:
        result.decision = DecisionStatus.NOT_ELIGIBLE
        disq_reasons = [d.reason for d in disqualified_by]
        result.summary = f"Citizen is NOT ELIGIBLE for '{scheme_name}' due to disqualification rule(s): {'; '.join(disq_reasons)}"
        return result

    # Check for zero trusted candidate eligibility rules
    trusted_elig_rules = [
        r for r in candidate_elig_rules
        if getattr(r, "evidence_consistency_status", "SUPPORTED") == "SUPPORTED" and not r.review_required
    ]

    if len(trusted_elig_rules) == 0:
        result.decision = DecisionStatus.NEEDS_REVIEW
        result.summary = f"No trusted candidate eligibility rules are available for '{scheme_name}'. Document contains 0 trusted citizen criteria."
        result.review_reasons.append("No trusted candidate eligibility rules available in active knowledge base.")
        return result

    # 2. Evaluate candidate eligibility rules
    failed_eligibility: List[RuleEvaluationResult] = []
    unknown_eligibility: List[RuleEvaluationResult] = []
    review_eligibility: List[RuleEvaluationResult] = []
    passed_eligibility: List[RuleEvaluationResult] = []

    for r in candidate_elig_rules:
        eval_res = evaluate_rule(r, citizen)
        result.eligibility_results.append(eval_res)
        if eval_res.evidence:
            result.evidence.append({
                "rule": eval_res.rule,
                "type": "eligibility",
                "evidence": eval_res.evidence,
                "original_kannada_evidence": eval_res.original_kannada_evidence,
                "page_number": eval_res.page_number,
                "source_url": eval_res.source_url,
            })

        if eval_res.status == RuleEvaluationStatus.NO_MATCH:
            failed_eligibility.append(eval_res)
        elif eval_res.status == RuleEvaluationStatus.MATCH:
            passed_eligibility.append(eval_res)
        elif eval_res.status == RuleEvaluationStatus.UNKNOWN:
            unknown_eligibility.append(eval_res)
        elif eval_res.status == RuleEvaluationStatus.REVIEW_REQUIRED:
            review_eligibility.append(eval_res)

    # If any mandatory eligibility rule definitely failed -> NOT_ELIGIBLE
    if failed_eligibility:
        result.decision = DecisionStatus.NOT_ELIGIBLE
        fail_reasons = [f.reason for f in failed_eligibility]
        result.summary = f"Citizen is NOT ELIGIBLE for '{scheme_name}' as mandatory eligibility requirement(s) were not met: {'; '.join(fail_reasons)}"
        return result

    # 3. Evaluate household / beneficiary limit rules
    failed_household: List[RuleEvaluationResult] = []
    unknown_household: List[RuleEvaluationResult] = []

    for r in household_rules:
        eval_res = evaluate_rule(r, citizen)
        result.household_results.append(eval_res)
        if eval_res.status == RuleEvaluationStatus.NO_MATCH:
            failed_household.append(eval_res)
        elif eval_res.status in (RuleEvaluationStatus.UNKNOWN, RuleEvaluationStatus.REVIEW_REQUIRED):
            unknown_household.append(eval_res)

    if failed_household:
        result.decision = DecisionStatus.NOT_ELIGIBLE
        hh_reasons = [h.reason for h in failed_household]
        result.summary = f"Citizen is NOT ELIGIBLE for '{scheme_name}' due to household constraint(s): {'; '.join(hh_reasons)}"
        return result

    # 4. Check for review requirements or unknown conditions
    review_issues = []
    missing_fields = []

    if review_eligibility:
        for r_res in review_eligibility:
            review_issues.append(f"Eligibility rule requires review: {r_res.reason}")
    if review_exclusions:
        for r_res in review_exclusions:
            review_issues.append(f"Exclusion rule requires review: {r_res.reason}")

    if unknown_eligibility:
        for u_res in unknown_eligibility:
            missing_fields.append(u_res.reason)
    if unknown_exclusions:
        for u_res in unknown_exclusions:
            missing_fields.append(f"Exclusion verification needed: {u_res.reason}")
    if unknown_household:
        for u_res in unknown_household:
            missing_fields.append(f"Household constraint verification needed: {u_res.reason}")

    if review_issues or missing_fields:
        result.decision = DecisionStatus.NEEDS_REVIEW
        result.review_reasons = review_issues
        result.missing_information = missing_fields
        all_notes = review_issues + missing_fields
        result.summary = f"Eligibility for '{scheme_name}' could not be definitively determined (NEEDS_REVIEW). Details: {'; '.join(all_notes)}"
        return result

    # 5. All required eligibility rules passed and no exclusions triggered!
    if passed_eligibility and len(passed_eligibility) == len(trusted_elig_rules):
        result.decision = DecisionStatus.ELIGIBLE
        pass_notes = [p.reason for p in passed_eligibility]
        result.summary = f"Citizen is ELIGIBLE for '{scheme_name}'. All required criteria satisfied: {'; '.join(pass_notes)}"
        return result

    result.decision = DecisionStatus.NEEDS_REVIEW
    result.summary = f"Undetermined status for '{scheme_name}'. Further verification required."
    return result


# ==============================================================================
# 5. Knowledge Base Integration & Loader
# ==============================================================================

def load_scheme_rules(
    scheme_key: str,
    version_label: Optional[str] = None,
) -> Tuple[List[RuleItem], str, Optional[str], str]:
    """
    Loads scheme rules from the PostgreSQL knowledge base or local grounded JSON files.
    Returns: (rules, scheme_name, active_version_label, version_status)
    """
    slug = make_slug(scheme_key)

    # 1. Attempt to query PostgreSQL knowledge base
    try:
        from app.knowledge_base import (
            get_scheme_by_key,
            get_active_version,
            get_historical_versions,
            get_rules_for_version,
        )

        scheme_record = get_scheme_by_key(slug)
        if scheme_record:
            scheme_name = scheme_record["name"]
            scheme_id = scheme_record["id"]

            target_version = None
            if version_label:
                # Query historical versions
                versions = get_historical_versions(slug)
                target_version = next((v for v in versions if v.get("version_label") == version_label), None)
            else:
                # Query active version
                target_version = get_active_version(scheme_id)

            if target_version:
                v_label = target_version.get("version_label")
                v_status = target_version.get("status", "ACTIVE")
                rules_data = get_rules_for_version(target_version["id"])

                rules: List[RuleItem] = []
                for r_dict in rules_data.get("eligibility_rules", []) + rules_data.get("exclusion_rules", []):
                    if not (r_dict.get("rule") or "").strip():
                        continue
                    # Reconstruct RuleItem from DB row
                    ev_list = r_dict.get("evidence", [])
                    ev_first = ev_list[0] if ev_list else {}
                    ev_obj = SchemeEvidence(
                        page_number=ev_first.get("page_number"),
                        section=ev_first.get("section"),
                        source_text=ev_first.get("evidence_text"),
                        original_kannada_evidence=ev_first.get("evidence_text"),
                        source_url=ev_first.get("source_url"),
                        ocr_confidence=float(ev_first.get("ocr_confidence", 85.0)) if ev_first.get("ocr_confidence") else 85.0,
                    )
                    rule_item = RuleItem(
                        rule=r_dict["rule"],
                        type=r_dict["type"],
                        category=r_dict.get("category", "general"),
                        value=r_dict.get("value"),
                        semantic_confidence=float(r_dict.get("semantic_confidence", 0.85)),
                        review_required=bool(r_dict.get("review_required", False)),
                        review_reasons=json.loads(r_dict["review_reasons"]) if isinstance(r_dict.get("review_reasons"), str) else (r_dict.get("review_reasons") or []),
                        evidence=ev_obj,
                    )
                    rules.append(rule_item)

                return rules, scheme_name, v_label, v_status

    except Exception as e:
        logger.warning(f"Could not load rules from PostgreSQL KB for {scheme_key}: {e}. Falling back to grounded extracted rules.")

    # 2. Local Fallback: Load from data/extracted_rules/<stem>_rules.json
    extracted_dir = Path(EXTRACTED_RULES_DIR)
    json_path = None

    # Check for direct or fuzzy file match
    for p in extracted_dir.glob("*_rules.json"):
        if slug in p.name.lower() or p.stem.lower().startswith(slug):
            json_path = p
            break

    # Benchmark name mapping fallbacks
    scheme_name_map = {
        "gruha-lakshmi": ("30af3c4d_GruhaLaxmiGO_rules.json", "Gruha Lakshmi Scheme"),
        "cm-raitha-vidyanidhi": ("668bfe88_cmsclorship_rules.json", "CM Raitha Vidyanidhi Scholarship"),
        "secondary-agriculture": ("02a9ac3f_SecondaryAgriculturedirectorateGO_rules.json", "Secondary Agriculture Directorate"),
        "rkvy": ("1333e107_Allocation2021-22_rules.json", "Rashtriya Krishi Vikas Yojana (RKVY)"),
        "pm-kisan-karnataka": ("e116e94b_PMKISANKarnatakaGO_rules.json", "PM-KISAN Karnataka Top-Up"),
    }

    if not json_path:
        for k, (fname, sname) in scheme_name_map.items():
            if k in slug or slug in k:
                target_p = extracted_dir / fname
                if target_p.exists():
                    json_path = target_p
                    break

    if json_path and json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        extraction = SchemeExtraction.model_validate(data)
        scheme_name = extraction.scheme_name or scheme_key
        rules = extraction.eligibility_rules + extraction.exclusion_rules
        v_label = extraction.version_information or "G.O. 2023"
        v_status = "ACTIVE"
        return rules, scheme_name, v_label, v_status

    return [], scheme_key, None, "UNKNOWN"


def evaluate_citizen(
    citizen: CitizenProfile,
    scheme_key: str,
    version_label: Optional[str] = None,
) -> EligibilityResult:
    """
    High-level entry point to evaluate a citizen profile against a Karnataka government scheme.
    """
    rules, scheme_name, v_label, v_status = load_scheme_rules(scheme_key, version_label=version_label)

    # Invariant: Archived versions must not be used unless explicitly requested
    if v_status == "ARCHIVED" and not version_label:
        return EligibilityResult(
            scheme_key=scheme_key,
            scheme_name=scheme_name,
            citizen_identifier=citizen.citizen_id or citizen.name,
            decision=DecisionStatus.NEEDS_REVIEW,
            summary=f"Active version for '{scheme_name}' is unavailable (only ARCHIVED version found).",
            review_reasons=["Scheme version is ARCHIVED and not active."],
        )

    # Invariant: REVIEW versions must never be used as trusted active rules
    if v_status == "REVIEW" and not version_label:
        return EligibilityResult(
            scheme_key=scheme_key,
            scheme_name=scheme_name,
            citizen_identifier=citizen.citizen_id or citizen.name,
            decision=DecisionStatus.NEEDS_REVIEW,
            summary=f"Scheme '{scheme_name}' version is in REVIEW status and not active.",
            review_reasons=["Scheme version requires human review."],
        )

    return evaluate_scheme_eligibility(
        citizen=citizen,
        rules=rules,
        scheme_name=scheme_name,
        scheme_key=scheme_key,
        version_label=v_label,
        version_status=v_status,
    )


def evaluate_citizen_against_schemes(
    citizen: CitizenProfile,
    scheme_keys: List[str],
) -> Dict[str, EligibilityResult]:
    """
    Evaluates one citizen profile against multiple Karnataka schemes.
    Returns a dictionary mapping scheme_key to its independent EligibilityResult.
    """
    results: Dict[str, EligibilityResult] = {}
    for s_key in scheme_keys:
        results[s_key] = evaluate_citizen(citizen, s_key)
    return results
