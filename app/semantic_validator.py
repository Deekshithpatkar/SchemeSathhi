"""
Checkpoint 16.3: Rule Semantic Validation & Evidence Consistency Engine.

Validates whether an extracted English scheme rule is strictly and accurately
supported by its original Kannada source evidence:
- Detects semantic contradictions (e.g., land owner vs landless, polarity inversions).
- Detects numeric threshold and AND/OR logic mismatches.
- Detects scope mismatches (personal candidate vs household/beneficiary limit).
- Assigns evidence_consistency_status: SUPPORTED, CONTRADICTED, INSUFFICIENT, REVIEW_REQUIRED.
- Ensures the original Kannada evidence remains authoritative over the English interpretation.
"""

import re
from typing import Tuple, Optional, Dict, Any, List
from app.schemas import RuleItem, SchemeEvidence


# Contradiction and polarity patterns
CONTRADICTION_PATTERNS = [
    # 1. Landowner vs Landless inversion (Mandatory check)
    {
        "id": "landowner_vs_landless",
        "description": "Rule asserts landless when evidence specifies landowner, or vice versa",
        "english_markers": ["landless", "without land", "no land", "landless farmer"],
        "kannada_conflicts": ["ಜಮೀನಿನ ಒಡೆಯ", "ಒಡೆಯ", "ಜಮೀನು ಹೊಂದಿ", "ಭೂಮಾಲೀಕ", "ಹಿಡುವಳಿದಾರ", "ಹಿಡುವಳಿ ಹೊಂದಿ", "ಕೃಷಿ ಭೂಮಿ ಹೊಂದಿ"],
    },
    {
        "id": "landless_vs_landowner",
        "description": "Rule asserts landowner when evidence specifies landless",
        "english_markers": ["landowner", "land owner", "owns land", "owning land"],
        "kannada_conflicts": ["ಭೂಹೀನ", "ಜಮೀನು ರಹಿತ", "ಭೂ ರಹಿತ"],
    },
    # 2. Polarity inversions (Eligible vs Disqualified)
    {
        "id": "eligibility_polarity_inversion",
        "description": "Eligibility rule asserted but evidence specifies exclusion/disqualification",
        "type": "eligibility",
        "english_markers": ["eligible", "qualifies", "entitled", "benefit is given"],
        "kannada_conflicts": ["ಅನರ್ಹ", "ಅರ್ಹರಾಗಿರುವುದಿಲ್ಲ", "ಅನ್ವಯಿಸುವುದಿಲ್ಲ", "ಅರ್ಹವಲ್ಲ", "ಪಡೆಯಲು ಸಾಧ್ಯವಿಲ್ಲ"],
    },
    {
        "id": "exclusion_polarity_inversion",
        "description": "Exclusion rule asserted but evidence specifies eligibility",
        "type": "exclusion",
        "english_markers": ["excluded", "disqualified", "ineligible", "not eligible"],
        "kannada_conflicts": ["ಅರ್ಹರು", "ಅರ್ಹರಾಗಿರುತ್ತಾರೆ", "ಅರ್ಹ ಫಲಾನುಭವಿ", "ಪಡೆಯಲು ಅರ್ಹ"],
    },
    # 3. Beneficiary Subject inversion
    {
        "id": "husband_vs_woman_head",
        "description": "Rule asserts benefit granted to husband when evidence specifies woman head of family",
        "english_markers": ["husband is eligible", "husband receives", "male head"],
        "kannada_conflicts": ["ಕುಟುಂಬದ ಯಜಮಾನಿ ಮಹಿಳೆ", "ಮಹಿಳೆಗೆ ಮಾತ್ರ"],
    },
    {
        "id": "farmer_vs_child",
        "description": "Rule asserts farmer receives student benefit instead of farmer's child",
        "english_markers": ["farmer receives scholarship", "farmers qualify for scholarship"],
        "kannada_conflicts": ["ರೈತರ ಮಕ್ಕಳು", "ರೈತರ ಮಕ್ಕಳಿಗೆ"],
    },
]

# Household / Beneficiary limit patterns
HOUSEHOLD_LIMIT_PATTERNS = [
    "ಒಂದೇ ಕುಟುಂಬದಲ್ಲಿ", "ಒಂದು ಕುಟುಂಬದಲ್ಲಿ", "ಒಂದು ಮಹಿಳೆಗೆ ಮಾತ್ರ",
    "ಒಬ್ಬರಿಗೆ ಮಾತ್ರ", "ಕುಟುಂಬಕ್ಕೆ ಒಂದು", "ಗರಿಷ್ಠ ಒಂದು",
    "one woman per household", "one per family", "only one per household",
    "single beneficiary per family", "one person per household", "household limit"
]


def classify_rule_scope(rule_text: str, evidence_text: str) -> str:
    """
    Classifies the rule scope:
    - candidate: individual qualification predicate (e.g. resident, student, age, income)
    - household: condition affecting household (e.g. household income)
    - beneficiary_limit: quota/cap constraint across a group (e.g. only one woman per household)
    - administrative: procedural instruction
    - unknown: unclassified
    """
    combined = f"{rule_text.lower()} {evidence_text.lower()}"

    for pat in HOUSEHOLD_LIMIT_PATTERNS:
        if pat in combined:
            return "beneficiary_limit"

    if any(k in combined for k in ["family income", "household income", "ಕುಟುಂಬದ ಆದಾಯ"]):
        return "household"

    if any(k in combined for k in ["ಕಚೇರಿ", "ಅರ್ಜಿ ಸಲ್ಲಿಸಲು", "documents required", "portal", "application"]):
        return "administrative"

    return "candidate"


def extract_numbers(text: str) -> List[int]:
    """Extracts numeric digits from text to compare thresholds."""
    # Matches digit sequences, ignoring punctuation
    clean = re.sub(r"[,./-]", "", text)
    nums = re.findall(r"\b\d+\b", clean)
    return [int(n) for n in nums if len(n) <= 8]


def validate_semantic_evidence_consistency(rule: RuleItem) -> Tuple[str, str, float]:
    """
    Validates the semantic consistency between rule.rule (English)
    and rule.evidence.original_kannada_evidence (or source_text).

    Returns:
    (evidence_consistency_status, validation_reason, confidence)
    Status is one of: SUPPORTED, CONTRADICTED, INSUFFICIENT, REVIEW_REQUIRED.
    """
    if not rule.evidence or not rule.evidence.source_text:
        return (
            "INSUFFICIENT",
            "Rule has no supporting physical evidence text to validate against.",
            1.0,
        )

    kannada_ev = (
        rule.evidence.original_kannada_evidence or rule.evidence.source_text or ""
    ).strip()
    english_rule = (rule.rule or "").strip().lower()
    kannada_lower = kannada_ev.lower()
    kannada_clean = re.sub(r"[`'\"=_~^]+", "", kannada_lower)
    kannada_clean = re.sub(r"\s+", " ", kannada_clean)

    # 1. Check for garbled / insufficient evidence
    if len(kannada_ev) < 10:
        return (
            "INSUFFICIENT",
            f"Evidence text is too brief ({len(kannada_ev)} chars) to verify claim.",
            0.9,
        )

    from app.text_reliability import assess_text_reliability
    reliability = assess_text_reliability(kannada_ev, min_words=2)
    if reliability.detected_encoding_issue or not reliability.reliable:
        return (
            "REVIEW_REQUIRED",
            "Supporting evidence appears degraded or garbled by OCR/encoding noise.",
            0.85,
        )

    # 2. Check Contradiction Rules
    for check in CONTRADICTION_PATTERNS:
        # Check rule type restriction if any
        if "type" in check and check["type"] != rule.type:
            continue

        matched_marker = next((m for m in check["english_markers"] if m in english_rule), None)
        if matched_marker:
            for conflict_k in check["kannada_conflicts"]:
                conflict_clean = re.sub(r"[`'\"=_~^]+", "", conflict_k.lower()).strip()
                if conflict_k.lower() in kannada_lower or (conflict_clean and conflict_clean in kannada_clean):
                    # Specific check: landless vs landowner
                    if check["id"] == "landowner_vs_landless":
                        # If rule says "landless" but evidence has "ಜಮೀನಿನ ಒಡೆಯ" (land owner)
                        return (
                            "CONTRADICTED",
                            (
                                f"Semantic Inversion detected: Rule claims '{matched_marker}' "
                                f"but Kannada evidence specifies '{conflict_k}' (land owner)."
                            ),
                            1.0,
                        )
                    elif check["id"] == "eligibility_polarity_inversion":
                        return (
                            "CONTRADICTED",
                            (
                                f"Polarity Inversion: Rule states eligibility but evidence "
                                f"contains disqualification term '{conflict_k}'."
                            ),
                            0.95,
                        )
                    elif check["id"] == "exclusion_polarity_inversion":
                        has_exclusion_k = any(neg in kannada_lower for neg in [
                            "ಅರ್ಹರಾಗಿರುವುದಿಲ್ಲ", "ಅನ್ವಯಿಸುವುದಿಲ್ಲ", "ಅನರ್ಹ", "ಅರ್ಹವಾಗುವುದಿಲ್ಲ",
                            "ಅರ್ಹರಲ್ಲ", "ಸಾಧ್ಯವಿಲ್ಲ", "ಅರ್ಹವಲ್ಲ"
                        ])
                        if has_exclusion_k:
                            continue
                        return (
                            "CONTRADICTED",
                            (
                                f"Polarity Inversion: Rule states exclusion but evidence "
                                f"contains eligibility term '{conflict_k}'."
                            ),
                            0.95,
                        )
                    elif check["id"] in ("husband_vs_woman_head", "farmer_vs_child"):
                        return (
                            "CONTRADICTED",
                            (
                                f"Subject Inversion: Rule claims benefit for '{matched_marker}' "
                                f"contradicting evidence '{conflict_k}'."
                            ),
                            0.95,
                        )

    # 3. Check Logic: AND vs OR mismatch
    # If English says "both parents must be" but Kannada says "ಅಥವಾ" (or)
    if "both" in english_rule and ("ಅಥವಾ" in kannada_lower or "ಯಾವುದಾದರೂ" in kannada_lower):
        if "ಇಬ್ಬರೂ" not in kannada_lower:
            return (
                "CONTRADICTED",
                "Logical Mismatch: Rule specifies strict 'both' (AND) condition, but evidence uses 'ಅಥವಾ' (OR).",
                0.90,
            )

    # 4. Check Numeric Threshold Inversion
    rule_nums = extract_numbers(english_rule)
    ev_nums = extract_numbers(kannada_ev)
    if rule_nums and ev_nums:
        # If rule specifies a primary monetary or age amount that differs completely from evidence
        # E.g. Rs. 5000 in rule when evidence only states 2000
        major_rule_nums = [n for n in rule_nums if n >= 50 and n not in (2021, 2022, 2023, 2024, 2025, 2026)]
        major_ev_nums = [n for n in ev_nums if n >= 50 and n not in (2021, 2022, 2023, 2024, 2025, 2026)]
        if major_rule_nums and major_ev_nums:
            if not any(r_n in major_ev_nums for r_n in major_rule_nums):
                return (
                    "CONTRADICTED",
                    f"Numeric Mismatch: Rule threshold ({major_rule_nums}) conflicts with evidence numbers ({major_ev_nums}).",
                    0.90,
                )

    # 5. Over-broadening check (e.g. Taxpayer scope)
    # If rule claims general 'taxpayers' but evidence specifically only says GST return filers
    if "taxpayer" in english_rule or "income tax" in english_rule:
        if "ಆದಾಯ ತೆರಿಗೆ" not in kannada_lower and ("ಜಿಎಸ್‌ಟಿ" in kannada_lower or "gst" in kannada_lower):
            return (
                "REVIEW_REQUIRED",
                "Scope Generalization: Rule asserts general income tax disqualification but evidence specifically states GST returns.",
                0.85,
            )

    # 6. Check ungrounded English claims: does evidence have any semantic correspondence?
    # Key concept tokens in rule should correspond to semantic markers in evidence
    concept_map = {
        "student": ["ವಿದ್ಯಾರ್ಥಿ", "ವಿದ್ಯಾರ್ಥಿನಿ", "ಶಿಕ್ಷಣ", "ಕೋರ್ಸ್", "ಪದವಿ", "ಶಾಲೆ", "ಕಾಲೇಜು"],
        "scholarship": ["ವಿದ್ಯಾರ್ಥಿವೇತನ", "ಶಿಷ್ಯವೇತನ"],
        "fail": ["ಅನುತ್ತೀರ್ಣ", "ಫೇಲ್"],
        "repeat": ["ಪುನರಾವರ್ತನೆ", "ಪುನಃ"],
        "woman": ["ಮಹಿಳೆ", "ಯಜಮಾನಿ", "ಸ್ತ್ರೀ"],
        "head": ["ಯಜಮಾನಿ", "ಮುಖಂಡ"],
        "ration": ["ಪಡಿತರ", "ಚೀಟಿ", "ಬಿಪಿಎಲ್", "ಎಪಿಎಲ್", "ಅಂತ್ಯೋದಯ"],
        "farmer": ["ರೈತ", "ಕೃಷಿಕ", "ಹಿಡುವಳಿ"],
    }
    missing_critical = []
    for eng_concept, kan_keywords in concept_map.items():
        if eng_concept in english_rule:
            if not any(k in kannada_lower for k in kan_keywords):
                missing_critical.append(eng_concept)

    if len(missing_critical) >= 2:
        return (
            "REVIEW_REQUIRED",
            f"Unsupported Claim: English rule asserts concepts ({missing_critical}) not grounded in Kannada evidence text.",
            0.80,
        )

    # 7. Supported: Evidence aligns with the extracted rule
    return (
        "SUPPORTED",
        "Rule is accurately grounded in and entailed by authoritative Kannada evidence.",
        0.95,
    )


def audit_rule_semantic_consistency(rule: RuleItem) -> RuleItem:
    """
    Runs the semantic validation stage on a RuleItem:
    - Sets rule.rule_scope (candidate vs beneficiary_limit).
    - Sets rule.evidence_consistency_status and semantic_validation_reason.
    - Synchronizes fields on rule.evidence.
    - If status is CONTRADICTED, INSUFFICIENT, or REVIEW_REQUIRED, sets review_required=True.
    """
    ev_text = (
        (rule.evidence.original_kannada_evidence or rule.evidence.source_text or "")
        if rule.evidence
        else ""
    )

    # 1. Classify rule scope
    rule.rule_scope = classify_rule_scope(rule.rule, ev_text)

    # 2. Run semantic evidence validation
    status, reason, confidence = validate_semantic_evidence_consistency(rule)

    rule.evidence_consistency_status = status
    rule.semantic_validation_reason = reason

    if rule.evidence:
        rule.evidence.evidence_consistency_status = status
        rule.evidence.semantic_validation_reason = reason
        rule.evidence.semantic_validation_confidence = confidence

    # 3. If contradicted, insufficient, or review_required, mark rule for review
    if status in ("CONTRADICTED", "INSUFFICIENT", "REVIEW_REQUIRED"):
        rule.review_required = True
        if reason and reason not in rule.review_reasons:
            rule.review_reasons.append(reason)

    # 4. If scope is a beneficiary_limit (e.g. one woman per household), flag for policy clarity
    if rule.rule_scope == "beneficiary_limit" and "Beneficiary/Household limit constraint" not in rule.review_reasons:
        rule.review_reasons.append("Beneficiary/Household limit constraint rather than personal qualification predicate.")

    return rule
