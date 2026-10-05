"""
Checkpoint 12: Rule Comparison Module.
Compares two CP10 structured rule extraction outputs and determines:
"Between the old and new extracted rule sets, did the actual candidate eligibility or exclusion rules change?"

Strictly focused on candidate qualification and disqualification rules:
- Added, removed, modified, or unchanged rules
- Category classification (income, age, landholding, residency, etc.)
- Direction of impact (more restrictive, less restrictive, exclusion added/removed, no impact, uncertain)
- Grounded evidence and confidence metrics
- Filtering of administrative and document-status text
"""

import re
import json
from pathlib import Path
from typing import Dict, Any, Union, Optional, List, Tuple
from datetime import datetime, timezone

from app.config import RULE_COMPARISONS_DIR, setup_logger, LLM_MODEL
from app.schemas import RuleItem, SchemeEvidence, SchemeExtraction
from app.rule_comparison_schemas import (
    RuleComparison,
    RuleComparisonResult,
    RuleComparisonMetadata,
)
from app.llm_client import LLMClient

logger = setup_logger("rule_comparison")

# Administrative / Document Status keywords that are NOT candidate eligibility rules
ADMIN_OR_STATUS_KEYWORDS = [
    "submitted to", "submit to", "submitted through", "submit through", "taluk office", "office of", "karyalaya",
    "assistant director", "forwarded to", "dispatch", "preservation",
    "keep the document", "guard file", "spare copies", "internal memo",
    "there is no change in this notification", "no change in notification",
    "amended notification", "order remains in force", "notification status",
    "online portal", "portal", "applications shall be", "application shall be",
    "mode of application", "submission of application",
    "ಬದಲಾವಣೆ ಇರುವುದಿಲ್ಲ", "ಉಳಿದಂತೆ ಸದರಿ", "ಅಧಿಸೂಚನೆ", "ತಿದ್ದುಪಡಿ", "ಕಛೇರಿಗೆ", "ಕಚೇರಿಗೆ",
    "ಕಳುಹಿಸಲಾಗುವುದು", "ರವಾನಿಸಲಾಗಿದೆ", "ಸಂರಕ್ಷಿಸಲು", "ರಕ್ಷಾ ಕಡತ"
]


def normalize_rule_text(text: str) -> str:
    """
    Normalizes rule text for robust deterministic comparison:
    - Lowercase and strip
    - Collapse extra whitespace
    - Normalize common phrasing equivalences without altering meaningful numbers/thresholds
    """
    if not text:
        return ""
    t = text.lower().strip()
    # Normalize punctuation spacing
    t = re.sub(r"[\.,;:!\?`'\"]", " ", t)
    t = " ".join(t.split())

    # Common phrasing replacements
    replacements = [
        ("shall not exceed", "must not exceed"),
        ("should not exceed", "must not exceed"),
        ("cannot exceed", "must not exceed"),
        ("shall be", "must be"),
        ("should be", "must be"),
        ("is excluded", "not eligible"),
        ("are excluded", "not eligible"),
        ("are not eligible", "not eligible"),
        ("karnataka resident", "resident of karnataka"),
        ("permanent resident of karnataka", "resident of karnataka"),
        ("belong to karnataka", "resident of karnataka"),
        ("₹", "rs "),
        ("rupees", "rs"),
        ("lakhs", "lakh"),
        ("hectares", "hectare"),
        ("acres", "acre"),
        ("years of age", "years"),
        ("years old", "years"),
    ]
    for old_phrase, new_phrase in replacements:
        t = t.replace(old_phrase, new_phrase)

    return " ".join(t.split())


def detect_rule_category(rule: RuleItem) -> str:
    """
    Identifies the underlying candidate eligibility attribute category:
    income, age, landholding, residency, farmer_category, occupation,
    government_employee, beneficiary_category, caste_category, gender,
    institutional_landholder, family_status, disability, employment_status, other.
    """
    valid_cats = {
        "income", "age", "landholding", "residency", "farmer_category", "occupation",
        "government_employee", "beneficiary_category", "caste_category", "gender",
        "institutional_landholder", "family_status", "disability", "employment_status"
    }
    raw_cat = str(rule.category or "").lower().strip()
    if raw_cat in valid_cats:
        return raw_cat

    rule_str = f"{rule.rule} {rule.category or ''} {rule.evidence.source_text if rule.evidence else ''}".lower()

    if "institutional" in rule_str or "ಸಾಂಸ್ಥಿಕ" in rule_str:
        return "institutional_landholder"
    if any(k in rule_str for k in ("government employee", "government servant", "psu employee", "constitutional post", "pension", "ಸರ್ಕಾರಿ ನೌಕರ", "ಪಿಂಚಣಿ")):
        return "government_employee"
    if re.search(r"\b(age|aged|years?\s+old|minimum\s+age|maximum\s+age)\b|ವಯಸ್ಸು|ವರ್ಷ", rule_str):
        return "age"
    if re.search(r"\b(income|annual\s+income|salary|lakh|lac|rupees|rs|tax|taxpayer)\b|[₹]|ಆದಾಯ|ತೆರಿಗೆ", rule_str):
        return "income"
    if any(k in rule_str for k in ("land", "landholding", "hectare", "acre", "ha", "gunta", "cultivable", "dry land", "wet land", "ceiling", "ಭೂಮಿ", "ಜಮೀನು", "ಹೆಕ್ಟೇರ್", "ಎಕರೆ")):
        return "landholding"
    if any(k in rule_str for k in ("resident", "residency", "domicile", "karnataka", "resided", "ನಿವಾಸಿ", "ವಾಸವಾಗಿರುವ")):
        return "residency"
    if any(k in rule_str for k in ("small farmer", "marginal farmer", "cultivator", "tenant farmer", "farmer", "ರೈತ", "ಕೃಷಿಕ")):
        return "farmer_category"
    if any(k in rule_str for k in ("caste", "sc", "st", "obc", "category", "general category", "minority", "ಪರಿಶಿಷ್ಟ", "ಹಿಂದುಳಿದ")):
        return "caste_category"
    if any(k in rule_str for k in ("woman", "women", "female", "male", "gender", "ಮಹಿಳೆ")):
        return "gender"
    if any(k in rule_str for k in ("family", "household", "spouse", "minor children", "ಕುಟುಂಬ")):
        return "family_status"
    if any(k in rule_str for k in ("disabled", "disability", "handicapped", "ಅಂಗವಿಕಲ")):
        return "disability"
    if any(k in rule_str for k in ("unemployed", "employed", "employment")):
        return "employment_status"
    if any(k in rule_str for k in ("doctor", "engineer", "lawyer", "chartered accountant", "architect")):
        return "occupation"

    return "other"


def is_administrative_or_status_text(text: str) -> bool:
    """Detects whether a statement is an administrative, office, or amendment note."""
    t = text.lower()
    return any(k in t for k in ADMIN_OR_STATUS_KEYWORDS)


def extract_numeric_threshold(text: str, category: str) -> Optional[float]:
    """
    Extracts key numerical threshold values (in standard units) for comparison:
    - income: rupees (e.g. 2.5 lakh -> 250000.0, 3,00,000 -> 300000.0)
    - age: years (e.g. 18 -> 18.0, 21 -> 21.0)
    - landholding: hectares (e.g. 2.0 Ha -> 2.0, 5 Ha -> 5.0)
    """
    t = text.lower().replace(",", "")

    if category == "income":
        # Check lakh format e.g. 2.5 lakh, 3 lakh
        lakh_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:lakh|lac)", t)
        if lakh_m:
            return float(lakh_m.group(1)) * 100000.0
        # Check raw number e.g. 250000, 300000
        num_m = re.search(r"(?:rs|₹)?\s*(\d{5,7})", t)
        if num_m:
            return float(num_m.group(1))

    elif category == "age":
        age_m = re.search(r"(\d{1,2})\s*(?:years|वर्ष|ವಯಸ್ಸು)", t)
        if age_m:
            return float(age_m.group(1))
        # Between X and Y
        between_m = re.search(r"between\s*(\d{1,2})\s*and\s*(\d{1,2})", t)
        if between_m:
            return float(between_m.group(1))

    elif category == "landholding":
        ha_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:hectare|ha|ಹೆಕ್ಟೇರ್)", t)
        if ha_m:
            return float(ha_m.group(1))
        acre_m = re.search(r"(\d+(?:\.\d+)?)\s*(?:acre|ಎಕರೆ)", t)
        if acre_m:
            # Convert acre to hectare (1 acre ~ 0.404686 Ha)
            return float(acre_m.group(1)) * 0.404686

    return None


def determine_threshold_impact(
    category: str,
    old_val: Optional[float],
    new_val: Optional[float],
) -> str:
    """
    Determines whether a threshold modification makes eligibility more or less restrictive.
    """
    if old_val is None or new_val is None:
        return "uncertain"

    if category == "income":
        # Ceiling: higher income limit -> more people qualify -> less restrictive
        if new_val > old_val:
            return "eligibility_less_restrictive"
        elif new_val < old_val:
            return "eligibility_more_restrictive"
        return "no_eligibility_impact"

    elif category == "landholding":
        # Ceiling: higher land limit -> more farmers qualify -> less restrictive
        if new_val > old_val:
            return "eligibility_less_restrictive"
        elif new_val < old_val:
            return "eligibility_more_restrictive"
        return "no_eligibility_impact"

    elif category == "age":
        # Minimum age: raising minimum age from 18 to 21 makes it more restrictive
        if new_val > old_val:
            return "eligibility_more_restrictive"
        elif new_val < old_val:
            return "eligibility_less_restrictive"
        return "no_eligibility_impact"

    return "uncertain"


def load_rules_data(doc_input: Union[str, Path, Dict[str, Any], SchemeExtraction]) -> Tuple[str, List[RuleItem], List[RuleItem]]:
    """
    Normalizes rule set input into:
    (document_name, eligibility_rules, exclusion_rules)
    """
    if isinstance(doc_input, SchemeExtraction):
        meta = doc_input.extraction_metadata
        doc_name = meta.source_document if meta else (doc_input.scheme_name or "in_memory_doc")
        return doc_name, doc_input.eligibility_rules, doc_input.exclusion_rules

    if isinstance(doc_input, (str, Path)):
        p = Path(doc_input)
        if not p.exists():
            raise FileNotFoundError(f"Rule extraction file not found: {p}")
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        doc_name = data.get("extraction_metadata", {}).get("source_document", p.name)
        extraction = SchemeExtraction.model_validate(data)
        return doc_name, extraction.eligibility_rules, extraction.exclusion_rules

    if isinstance(doc_input, dict):
        doc_name = doc_input.get("extraction_metadata", {}).get("source_document") or doc_input.get("document_name", "in_memory_rules")
        extraction = SchemeExtraction.model_validate(doc_input)
        return doc_name, extraction.eligibility_rules, extraction.exclusion_rules

    raise TypeError("doc_input must be a file path, dictionary, or SchemeExtraction instance")


def deduplicate_rules(rules: List[RuleItem]) -> List[RuleItem]:
    """
    Removes semantic duplicate rules (e.g. same rule expressed in Kannada and English).
    """
    unique_rules = []
    seen_keys = set()

    for r in rules:
        norm = normalize_rule_text(r.rule)
        cat = detect_rule_category(r)
        key = (r.type, cat, norm)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        unique_rules.append(r)

    return unique_rules


def deterministic_compare_rules(
    old_doc_name: str,
    new_doc_name: str,
    old_el: List[RuleItem],
    old_ex: List[RuleItem],
    new_el: List[RuleItem],
    new_ex: List[RuleItem],
) -> Tuple[List[RuleComparison], List[RuleItem], List[RuleItem]]:
    """
    Deterministic Python comparison of old and new rule sets.
    Matches identical rules, normalized phrasing, and threshold modifications.
    Returns (matched_comparisons, remaining_unmatched_old, remaining_unmatched_new).
    """
    comparisons: List[RuleComparison] = []
    matched_new_indices = set()
    unmatched_old: List[RuleItem] = []

    # Flatten old and new rules
    all_old = deduplicate_rules(old_el + old_ex)
    all_new = deduplicate_rules(new_el + new_ex)

    for o_rule in all_old:
        o_norm = normalize_rule_text(o_rule.rule)
        o_cat = detect_rule_category(o_rule)
        o_type = o_rule.type or "eligibility"
        o_is_admin = is_administrative_or_status_text(o_rule.rule)

        match_found = False

        for n_idx, n_rule in enumerate(all_new):
            if n_idx in matched_new_indices:
                continue

            n_norm = normalize_rule_text(n_rule.rule)
            n_cat = detect_rule_category(n_rule)
            n_type = n_rule.type or "eligibility"
            n_is_admin = is_administrative_or_status_text(n_rule.rule)

            # Case A: Identical or Normalized Identical
            if (o_type == n_type) and (o_norm == n_norm or (o_cat == n_cat and o_cat != "other" and o_norm == n_norm)):
                matched_new_indices.add(n_idx)
                match_found = True
                comparisons.append(RuleComparison(
                    old_rule=o_rule,
                    new_rule=n_rule,
                    change_type="unchanged",
                    category=o_cat,
                    impact="no_eligibility_impact",
                    evidence=n_rule.evidence or o_rule.evidence,
                    confidence=0.95,
                    review_required=False,
                    review_reasons=[],
                ))
                break

            # Case B: Administrative or Document Status Text
            if (o_is_admin and n_is_admin) or ((o_is_admin or n_is_admin) and o_cat == "other" and n_cat == "other"):
                matched_new_indices.add(n_idx)
                match_found = True
                comparisons.append(RuleComparison(
                    old_rule=o_rule,
                    new_rule=n_rule,
                    change_type="modified" if o_norm != n_norm else "unchanged",
                    category="other",
                    impact="no_eligibility_impact",
                    evidence=n_rule.evidence or o_rule.evidence,
                    confidence=0.90,
                    review_required=True,
                    review_reasons=["Administrative or document status text ignored as non-eligibility rule."],
                ))
                break

            # Case C: Same Category and Type, but Modified Threshold (Income, Age, Landholding)
            if (o_type == n_type) and (o_cat == n_cat) and (o_cat in ("income", "age", "landholding")):
                o_val = extract_numeric_threshold(o_rule.rule, o_cat)
                n_val = extract_numeric_threshold(n_rule.rule, n_cat)

                if o_val is not None and n_val is not None:
                    matched_new_indices.add(n_idx)
                    match_found = True
                    if o_val == n_val:
                        # Values identical, just wording difference
                        comparisons.append(RuleComparison(
                            old_rule=o_rule,
                            new_rule=n_rule,
                            change_type="unchanged",
                            category=o_cat,
                            impact="no_eligibility_impact",
                            evidence=n_rule.evidence or o_rule.evidence,
                            confidence=0.95,
                            review_required=False,
                            review_reasons=[],
                        ))
                    else:
                        impact = determine_threshold_impact(o_cat, o_val, n_val)
                        comparisons.append(RuleComparison(
                            old_rule=o_rule,
                            new_rule=n_rule,
                            change_type="modified",
                            category=o_cat,
                            impact=impact,
                            evidence=n_rule.evidence or o_rule.evidence,
                            confidence=0.95,
                            review_required=(impact == "uncertain"),
                            review_reasons=["Threshold modified"] if impact != "uncertain" else ["Direction of threshold impact uncertain"],
                        ))
                    break

            # Case D: Same Category (e.g. residency, government_employee), phrasing reworded without threshold change
            if (o_type == n_type) and (o_cat == n_cat) and (o_cat in ("residency", "government_employee", "farmer_category", "institutional_landholder")):
                # Check if new residency has added condition (e.g. 5 years)
                if o_cat == "residency" and ("5 years" in n_norm or "year" in n_norm) and ("year" not in o_norm):
                    matched_new_indices.add(n_idx)
                    match_found = True
                    comparisons.append(RuleComparison(
                        old_rule=o_rule,
                        new_rule=n_rule,
                        change_type="modified",
                        category="residency",
                        impact="eligibility_more_restrictive",
                        evidence=n_rule.evidence or o_rule.evidence,
                        confidence=0.95,
                        review_required=False,
                        review_reasons=["Additional residency duration condition added."],
                    ))
                    break
                else:
                    # Semantic equivalent rephrasing
                    matched_new_indices.add(n_idx)
                    match_found = True
                    comparisons.append(RuleComparison(
                        old_rule=o_rule,
                        new_rule=n_rule,
                        change_type="unchanged",
                        category=o_cat,
                        impact="no_eligibility_impact",
                        evidence=n_rule.evidence or o_rule.evidence,
                        confidence=0.90,
                        review_required=False,
                        review_reasons=[],
                    ))
                    break

        if not match_found:
            unmatched_old.append(o_rule)

    unmatched_new = [r for idx, r in enumerate(all_new) if idx not in matched_new_indices]
    return comparisons, unmatched_old, unmatched_new


def semantic_compare_unmatched(
    unmatched_old: List[RuleItem],
    unmatched_new: List[RuleItem],
    llm_client: Optional[LLMClient] = None,
    model: Optional[str] = None,
) -> List[RuleComparison]:
    """
    Level 2 Semantic LLM comparison for remaining unmatched candidate rules.
    If no LLM is available or pairs don't match, treats them as added/removed rules.
    """
    results: List[RuleComparison] = []

    # If either list is empty, handle pure additions and removals deterministically
    if not unmatched_old:
        for nr in unmatched_new:
            cat = detect_rule_category(nr)
            r_type = nr.type or "eligibility"
            impact = "exclusion_added" if r_type == "exclusion" else "eligibility_more_restrictive"

            # Check if administrative
            if is_administrative_or_status_text(nr.rule):
                impact = "no_eligibility_impact"

            results.append(RuleComparison(
                old_rule=None,
                new_rule=nr,
                change_type="added",
                category=cat,
                impact=impact,
                evidence=nr.evidence,
                confidence=0.90,
                review_required=(nr.evidence is None),
                review_reasons=["Missing evidence"] if nr.evidence is None else [],
            ))
        return results

    if not unmatched_new:
        for or_ in unmatched_old:
            cat = detect_rule_category(or_)
            r_type = or_.type or "eligibility"
            impact = "exclusion_removed" if r_type == "exclusion" else "eligibility_less_restrictive"

            if is_administrative_or_status_text(or_.rule):
                impact = "no_eligibility_impact"

            results.append(RuleComparison(
                old_rule=or_,
                new_rule=None,
                change_type="removed",
                category=cat,
                impact=impact,
                evidence=or_.evidence,
                confidence=0.90,
                review_required=(or_.evidence is None),
                review_reasons=["Missing evidence"] if or_.evidence is None else [],
            ))
        return results

    # Both have unmatched rules: Evaluate pairs with LLM or fallback
    active_model = model or LLM_MODEL
    client = llm_client or LLMClient(model=active_model)

    matched_new_idx = set()
    for o_rule in unmatched_old:
        o_cat = detect_rule_category(o_rule)
        o_matched = False

        for n_idx, n_rule in enumerate(unmatched_new):
            if n_idx in matched_new_idx:
                continue
            n_cat = detect_rule_category(n_rule)

            # Send single rule pair to LLM for semantic verification
            prompt = f"""Compare these two government scheme rules:
OLD RULE: "{o_rule.rule}" (Category: {o_cat}, Type: {o_rule.type})
NEW RULE: "{n_rule.rule}" (Category: {n_cat}, Type: {n_rule.type})

Determine:
1. Are they the same rule, a modification of the same rule, or completely unrelated?
2. If same rule or modification, what is the category and impact on candidate eligibility?

Return valid JSON:
{{
  "is_related": true/false,
  "change_type": "unchanged / modified / added / removed",
  "category": "{o_cat}",
  "impact": "eligibility_more_restrictive / eligibility_less_restrictive / exclusion_added / exclusion_removed / no_eligibility_impact / uncertain",
  "explanation": "..."
}}
"""
            try:
                raw_json = client.generate_json(
                    prompt=prompt,
                    system_prompt="You are an expert rule comparison analyst for government schemes.",
                    temperature=0.0,
                    max_retries=1
                )
                if raw_json.get("is_related"):
                    matched_new_idx.add(n_idx)
                    o_matched = True
                    c_type = raw_json.get("change_type", "modified")
                    imp = raw_json.get("impact", "uncertain")
                    results.append(RuleComparison(
                        old_rule=o_rule,
                        new_rule=n_rule,
                        change_type=c_type,
                        category=raw_json.get("category", o_cat),
                        impact=imp,
                        evidence=n_rule.evidence or o_rule.evidence,
                        confidence=0.85,
                        review_required=(imp == "uncertain" or not n_rule.evidence),
                        review_reasons=[raw_json.get("explanation", "LLM semantic match")],
                    ))
                    break
            except Exception as e:
                logger.warning(f"LLM pair comparison error: {e}. Falling back to addition/removal.")

        if not o_matched:
            # Treated as removed
            r_type = o_rule.type or "eligibility"
            imp = "exclusion_removed" if r_type == "exclusion" else "eligibility_less_restrictive"
            results.append(RuleComparison(
                old_rule=o_rule,
                new_rule=None,
                change_type="removed",
                category=o_cat,
                impact=imp,
                evidence=o_rule.evidence,
                confidence=0.90,
                review_required=(o_rule.evidence is None),
                review_reasons=["Missing evidence"] if o_rule.evidence is None else [],
            ))

    # Remaining new rules treated as added
    for n_idx, n_rule in enumerate(unmatched_new):
        if n_idx not in matched_new_idx:
            cat = detect_rule_category(n_rule)
            r_type = n_rule.type or "eligibility"
            imp = "exclusion_added" if r_type == "exclusion" else "eligibility_more_restrictive"
            results.append(RuleComparison(
                old_rule=None,
                new_rule=n_rule,
                change_type="added",
                category=cat,
                impact=imp,
                evidence=n_rule.evidence,
                confidence=0.90,
                review_required=(n_rule.evidence is None),
                review_reasons=["Missing evidence"] if n_rule.evidence is None else [],
            ))

    return results


def compare_rules(
    old_rules_input: Union[str, Path, Dict[str, Any], SchemeExtraction],
    new_rules_input: Union[str, Path, Dict[str, Any], SchemeExtraction],
    llm_client: Optional[LLMClient] = None,
    model: Optional[str] = None,
    save_output: bool = True,
    output_dir: Optional[Path] = None,
) -> RuleComparisonResult:
    """
    Master Checkpoint 12 Entry Point.
    Compares old and new CP10 structured rule extraction outputs.
    Answers: 'Between the old and new extracted rule sets, did the actual candidate eligibility or exclusion rules change?'
    """
    old_doc, old_el, old_ex = load_rules_data(old_rules_input)
    new_doc, new_el, new_ex = load_rules_data(new_rules_input)

    logger.info(f"Starting Rule Comparison: Old='{old_doc}' vs New='{new_doc}'")

    total_old = len(old_el) + len(old_ex)
    total_new = len(new_el) + len(new_ex)

    # 1. Edge Case: Both rule sets are empty (e.g. PM-KISAN guidelines document)
    if total_old == 0 and total_new == 0:
        logger.info("Both rule sets have 0 candidate eligibility and exclusion rules.")
        res = RuleComparisonResult(
            old_document=old_doc,
            new_document=new_doc,
            rule_changes=[],
            added_rules=[],
            removed_rules=[],
            modified_rules=[],
            unchanged_rules=[],
            eligibility_relevance="none",
            summary="Both document versions contain 0 candidate eligibility or exclusion rules. No eligibility rule changes exist.",
            review_required=False,
            review_reasons=[],
            comparison_metadata=RuleComparisonMetadata(
                pipeline_version="1.0_rule_comparison",
                deterministic_match=True,
                total_old_rules=0,
                total_new_rules=0,
                total_changes=0,
            ),
        )
        if save_output:
            _save_result(res, output_dir)
        return res

    # 2. Level 1: Deterministic Rule Comparison
    det_comps, unmatched_old, unmatched_new = deterministic_compare_rules(
        old_doc, new_doc, old_el, old_ex, new_el, new_ex
    )

    # 3. Level 2: Semantic comparison for remaining unmatched rules (if any)
    if unmatched_old or unmatched_new:
        logger.info(f"Unmatched rules exist (Old: {len(unmatched_old)}, New: {len(unmatched_new)}). Running semantic comparison...")
        sem_comps = semantic_compare_unmatched(unmatched_old, unmatched_new, llm_client=llm_client, model=model)
        all_comps = det_comps + sem_comps
    else:
        all_comps = det_comps

    # 4. Group by change type
    added = [c for c in all_comps if c.change_type == "added"]
    removed = [c for c in all_comps if c.change_type == "removed"]
    modified = [c for c in all_comps if c.change_type == "modified"]
    unchanged = [c for c in all_comps if c.change_type == "unchanged"]

    # 5. Quality Control: Missing evidence & review reasons
    all_review_reasons = []
    has_uncertain = False
    for c in all_comps:
        if c.change_type in ("added", "removed", "modified") and c.impact != "no_eligibility_impact":
            if not c.evidence or not c.evidence.source_text:
                c.review_required = True
                c.review_reasons.append("Missing physical grounding evidence for candidate rule change.")
        if c.impact == "uncertain":
            has_uncertain = True
            c.review_required = True
        all_review_reasons.extend(c.review_reasons)

    unique_review_reasons = list(dict.fromkeys(all_review_reasons))
    review_required = len(unique_review_reasons) > 0 or has_uncertain

    # 6. Overall Eligibility Relevance
    has_substantive_impact = any(
        c.impact in (
            "eligibility_more_restrictive",
            "eligibility_less_restrictive",
            "exclusion_added",
            "exclusion_removed"
        )
        for c in (added + removed + modified)
    )

    if has_substantive_impact:
        eligibility_relevance = "clearly_relevant"
    elif has_uncertain:
        eligibility_relevance = "uncertain"
    elif any(c.change_type == "modified" for c in modified):
        eligibility_relevance = "potentially_relevant"
    else:
        eligibility_relevance = "none"

    # 7. Summary construction
    summary_parts = []
    if added:
        summary_parts.append(f"{len(added)} rule(s) added")
    if removed:
        summary_parts.append(f"{len(removed)} rule(s) removed")
    if modified:
        summary_parts.append(f"{len(modified)} rule(s) modified")
    if unchanged:
        summary_parts.append(f"{len(unchanged)} rule(s) unchanged")

    change_desc = ", ".join(summary_parts) if summary_parts else "No changes detected"
    summary = f"Rule comparison completed: {change_desc}. Overall eligibility relevance: '{eligibility_relevance}'."

    total_changes = len(added) + len(removed) + len(modified)

    result = RuleComparisonResult(
        old_document=old_doc,
        new_document=new_doc,
        rule_changes=all_comps,
        added_rules=added,
        removed_rules=removed,
        modified_rules=modified,
        unchanged_rules=unchanged,
        eligibility_relevance=eligibility_relevance,
        summary=summary,
        review_required=review_required,
        review_reasons=unique_review_reasons,
        comparison_metadata=RuleComparisonMetadata(
            pipeline_version="1.0_rule_comparison",
            deterministic_match=(not unmatched_old and not unmatched_new),
            total_old_rules=total_old,
            total_new_rules=total_new,
            total_changes=total_changes,
        ),
    )

    if save_output:
        _save_result(result, output_dir)

    return result


def _save_result(result: RuleComparisonResult, output_dir: Optional[Path] = None) -> Path:
    """Saves RuleComparisonResult to data/rule_comparisons/."""
    target_dir = output_dir or RULE_COMPARISONS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    old_stem = Path(result.old_document).stem
    new_stem = Path(result.new_document).stem
    out_path = target_dir / f"{old_stem}_vs_{new_stem}_rule_comparison.json"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(result.model_dump_json(indent=2))
    logger.info(f"Saved rule comparison result to: {out_path}")
    return out_path
