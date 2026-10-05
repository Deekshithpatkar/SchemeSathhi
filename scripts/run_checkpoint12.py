"""
Checkpoint 12 Execution Script: Rule Comparison Pipeline.
Demonstrates structured comparison of CP10 extracted eligibility and exclusion rules:
1. Real Document Rule Self-Comparison: Real extracted rules from PM-KISAN Karnataka document.
2. Controlled Policy Test 1: Modified income threshold (Rs. 2.5L -> Rs. 3.0L).
3. Controlled Policy Test 2: Added exclusion (institutional landholders).
4. Controlled Policy Test 3: Procedural / Administrative wording difference.

All controlled modifications are strictly labeled as simulated test scenarios.
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import EXTRACTED_RULES_DIR, RULE_COMPARISONS_DIR
from app.schemas import RuleItem, SchemeEvidence
from app.rule_comparison import compare_rules


def main():
    print("=" * 75)
    print("CHECKPOINT 12: CANDIDATE ELIGIBILITY & EXCLUSION RULE COMPARISON")
    print("=" * 75)

    pmkisan_rules_path = EXTRACTED_RULES_DIR / "e75996bb_PM-KISANSchemeguidelinesfinal_rules.json"

    # =========================================================================
    # 1. Real Document Self-Comparison
    # =========================================================================
    print("\n[SCENARIO 1] Real Document Self-Comparison (Deterministic Level 1):")
    if pmkisan_rules_path.exists():
        print(f"Loading real CP10 extraction from: {pmkisan_rules_path.name}")
        comp_real = compare_rules(
            old_rules_input=pmkisan_rules_path,
            new_rules_input=pmkisan_rules_path,
            save_output=True,
            output_dir=RULE_COMPARISONS_DIR
        )
        print(f"  - Old Document:          {comp_real.old_document}")
        print(f"  - New Document:          {comp_real.new_document}")
        print(f"  - Total Rule Changes:    {len(comp_real.rule_changes)}")
        print(f"  - Eligibility Relevance: {comp_real.eligibility_relevance}")
        print(f"  - Review Required:       {comp_real.review_required}")
        print(f"  - Deterministic Match:   {comp_real.comparison_metadata.deterministic_match}")
        print(f"  - Summary:               {comp_real.summary}")
    else:
        print(f"[WARNING] File not found: {pmkisan_rules_path}")

    # =========================================================================
    # 2. Controlled Policy Test: Modified Income Threshold
    # =========================================================================
    print("\n[SCENARIO 2] Controlled Test - Income Threshold Policy Amendment:")
    print("  (Simulated test scenario: Income limit raised from Rs. 2.5 Lakh to Rs. 3.0 Lakh)")

    old_rules_scenario = {
        "scheme_name": "Farmer Support Scheme (Version 1)",
        "document_name": "farmer_guidelines_2024.pdf",
        "eligibility_rules": [
            {
                "rule": "Annual family income must not exceed Rs. 2.5 lakh",
                "type": "eligibility",
                "category": "income",
                "evidence": {
                    "page_number": 2,
                    "source_text": "Annual family income must not exceed Rs. 2.5 lakh",
                    "ocr_confidence": 99.0
                }
            }
        ],
        "exclusion_rules": [
            {
                "rule": "Government employees are not eligible",
                "type": "exclusion",
                "category": "government_employee",
                "evidence": {
                    "page_number": 3,
                    "source_text": "Government employees are not eligible",
                    "ocr_confidence": 98.0
                }
            }
        ]
    }

    new_rules_scenario = {
        "scheme_name": "Farmer Support Scheme (Version 2)",
        "document_name": "farmer_guidelines_2025.pdf",
        "eligibility_rules": [
            {
                "rule": "Annual household income shall not exceed Rs. 3,00,000",
                "type": "eligibility",
                "category": "income",
                "evidence": {
                    "page_number": 2,
                    "source_text": "Annual household income shall not exceed Rs. 3,00,000",
                    "ocr_confidence": 99.0
                }
            }
        ],
        "exclusion_rules": [
            {
                "rule": "Government employees are not eligible",
                "type": "exclusion",
                "category": "government_employee",
                "evidence": {
                    "page_number": 3,
                    "source_text": "Government employees are not eligible",
                    "ocr_confidence": 98.0
                }
            }
        ]
    }

    comp_thresh = compare_rules(
        old_rules_input=old_rules_scenario,
        new_rules_input=new_rules_scenario,
        save_output=True,
        output_dir=RULE_COMPARISONS_DIR
    )

    print(f"  - Total Rule Changes:    {len(comp_thresh.rule_changes)}")
    print(f"  - Modified Rules:        {len(comp_thresh.modified_rules)}")
    print(f"  - Unchanged Rules:       {len(comp_thresh.unchanged_rules)}")
    print(f"  - Eligibility Relevance: {comp_thresh.eligibility_relevance}")
    for mod in comp_thresh.modified_rules:
        print(f"    * Category: {mod.category} | Impact: {mod.impact} | Change: {mod.change_type}")
        print(f"      Old: '{mod.old_rule.rule if mod.old_rule else ''}'")
        print(f"      New: '{mod.new_rule.rule if mod.new_rule else ''}'")

    # =========================================================================
    # 3. Controlled Policy Test: Added Exclusion
    # =========================================================================
    print("\n[SCENARIO 3] Controlled Test - Added Exclusion Rule:")
    print("  (Simulated test scenario: Institutional landholders added to exclusions)")

    new_rules_added_exclusion = {
        "scheme_name": "Farmer Support Scheme (Version 3)",
        "document_name": "farmer_guidelines_2026.pdf",
        "eligibility_rules": [
            {
                "rule": "Annual household income shall not exceed Rs. 3,00,000",
                "type": "eligibility",
                "category": "income",
                "evidence": {
                    "page_number": 2,
                    "source_text": "Annual household income shall not exceed Rs. 3,00,000",
                    "ocr_confidence": 99.0
                }
            }
        ],
        "exclusion_rules": [
            {
                "rule": "Government employees are not eligible",
                "type": "exclusion",
                "category": "government_employee",
                "evidence": {
                    "page_number": 3,
                    "source_text": "Government employees are not eligible",
                    "ocr_confidence": 98.0
                }
            },
            {
                "rule": "Institutional landholders are not eligible",
                "type": "exclusion",
                "category": "institutional_landholder",
                "evidence": {
                    "page_number": 3,
                    "source_text": "Institutional landholders are not eligible",
                    "ocr_confidence": 98.5
                }
            }
        ]
    }

    comp_excl = compare_rules(
        old_rules_input=new_rules_scenario,
        new_rules_input=new_rules_added_exclusion,
        save_output=True,
        output_dir=RULE_COMPARISONS_DIR
    )

    print(f"  - Total Rule Changes:    {len(comp_excl.rule_changes)}")
    print(f"  - Added Rules:           {len(comp_excl.added_rules)}")
    print(f"  - Eligibility Relevance: {comp_excl.eligibility_relevance}")
    for add_item in comp_excl.added_rules:
        print(f"    * Category: {add_item.category} | Impact: {add_item.impact} | Change: {add_item.change_type}")
        print(f"      Rule: '{add_item.new_rule.rule if add_item.new_rule else ''}'")

    # =========================================================================
    # 4. Controlled Policy Test: Administrative Text (Non-Eligibility)
    # =========================================================================
    print("\n[SCENARIO 4] Controlled Test - Administrative / Procedural Text Filter:")
    print("  (Simulated test scenario: Office submission procedure changed to online portal)")

    admin_old = {
        "scheme_name": "Farmer Support Scheme",
        "document_name": "guidelines_admin_v1.pdf",
        "eligibility_rules": [
            {
                "rule": "Applications shall be submitted to the Taluk office.",
                "type": "eligibility",
                "category": "other",
                "evidence": {"page_number": 4, "source_text": "Applications shall be submitted to the Taluk office."}
            }
        ],
        "exclusion_rules": []
    }

    admin_new = {
        "scheme_name": "Farmer Support Scheme",
        "document_name": "guidelines_admin_v2.pdf",
        "eligibility_rules": [
            {
                "rule": "Applications shall be submitted through the online portal.",
                "type": "eligibility",
                "category": "other",
                "evidence": {"page_number": 4, "source_text": "Applications shall be submitted through the online portal."}
            }
        ],
        "exclusion_rules": []
    }

    comp_admin = compare_rules(
        old_rules_input=admin_old,
        new_rules_input=admin_new,
        save_output=True,
        output_dir=RULE_COMPARISONS_DIR
    )

    print(f"  - Eligibility Relevance: {comp_admin.eligibility_relevance}")
    print(f"  - Review Required:       {comp_admin.review_required}")
    for item in comp_admin.rule_changes:
        print(f"    * Impact: {item.impact} | Reasons: {item.review_reasons}")

    print("\n" + "=" * 75)
    print("CHECKPOINT 12 EXECUTION COMPLETE")
    print("=" * 75)


if __name__ == "__main__":
    main()
