"""
Checkpoint 11 Execution Script: Document Comparison.
Demonstrates Level 1 Deterministic comparison on the real PM-KISAN Karnataka government document
and controlled policy comparison scenarios.
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import STRUCTURED_DIR, COMPARISONS_DIR, LLM_MODEL
from app.comparison import compare_documents


def main():
    print("=" * 70)
    print("CHECKPOINT 11: DOCUMENT COMPARISON PIPELINE")
    print("=" * 70)

    pmkisan_json = STRUCTURED_DIR / "e75996bb_PM-KISANSchemeguidelinesfinal.json"
    if not pmkisan_json.exists():
        print(f"[ERROR] Target JSON not found: {pmkisan_json}")
        return

    # 1. Real Document Self-Comparison (Idempotency & Hash Match)
    print("\n[TEST 1] Real Document Self-Comparison (Deterministic Level 1):")
    print(f"Comparing '{pmkisan_json.name}' with itself...")

    comp1 = compare_documents(
        old_doc=pmkisan_json,
        new_doc=pmkisan_json,
        save_output=True,
        output_dir=COMPARISONS_DIR
    )

    print(f"  - Hash Status:                  {comp1.hash_status}")
    print(f"  - Overall Status:               {comp1.overall_status}")
    print(f"  - Semantic Comparison Required: {comp1.semantic_comparison_required}")
    print(f"  - Eligibility Relevance:        {comp1.eligibility_relevance}")
    print(f"  - Review Required:              {comp1.review_required}")
    print(f"  - Summary:                      {comp1.semantic_summary}")

    # 2. Simulated Version Update: Income Threshold Policy Amendment
    print("\n[TEST 2] Policy Amendment Scenario (Income Threshold Change):")
    old_doc = {
        "filename": "karnataka_farmer_guidelines_v1.pdf",
        "sha256": "aaaa111122223333444455556666777788889999000011112222333344445555",
        "pages": [
            {
                "page_number": 1,
                "text": "Agriculture Department Karnataka.\nAnnual family income shall not exceed Rs. 2,50,000 to be eligible.\nApplications submitted to Taluk office."
            }
        ]
    }
    new_doc = {
        "filename": "karnataka_farmer_guidelines_v2.pdf",
        "sha256": "bbbb111122223333444455556666777788889999000011112222333344445555",
        "pages": [
            {
                "page_number": 1,
                "text": "Agriculture Department Karnataka.\nAnnual family income shall not exceed Rs. 3,00,000 to be eligible.\nApplications submitted to Taluk office."
            }
        ]
    }

    comp2 = compare_documents(
        old_doc=old_doc,
        new_doc=new_doc,
        model=LLM_MODEL,
        save_output=True,
        output_dir=COMPARISONS_DIR
    )

    print(f"  - Hash Status:                  {comp2.hash_status}")
    print(f"  - Overall Status:               {comp2.overall_status}")
    print(f"  - Semantic Comparison Required: {comp2.semantic_comparison_required}")
    print(f"  - Eligibility Relevance:        {comp2.eligibility_relevance}")
    print(f"  - Summary:                      {comp2.semantic_summary}")
    for item in comp2.semantic_changes:
        print(f"    * [{item.category.upper()}] {item.description} (Relevance: {item.eligibility_relevance}, Attribute: {item.affected_attribute})")

    # 3. Simulated Procedural Update (Non-Eligibility Instruction)
    print("\n[TEST 3] Procedural Change Scenario (Application Submission Office):")
    doc_proc_new = {
        "filename": "karnataka_farmer_guidelines_v3.pdf",
        "sha256": "cccc111122223333444455556666777788889999000011112222333344445555",
        "pages": [
            {
                "page_number": 1,
                "text": "Agriculture Department Karnataka.\nAnnual family income shall not exceed Rs. 3,00,000 to be eligible.\nApplications shall be submitted through the designated online portal."
            }
        ]
    }

    comp3 = compare_documents(
        old_doc=new_doc,
        new_doc=doc_proc_new,
        model=LLM_MODEL,
        save_output=True,
        output_dir=COMPARISONS_DIR
    )

    print(f"  - Hash Status:                  {comp3.hash_status}")
    print(f"  - Overall Status:               {comp3.overall_status}")
    print(f"  - Semantic Comparison Required: {comp3.semantic_comparison_required}")
    print(f"  - Eligibility Relevance:        {comp3.eligibility_relevance}")
    print(f"  - Summary:                      {comp3.semantic_summary}")
    for item in comp3.semantic_changes:
        print(f"    * [{item.category.upper()}] {item.description} (Relevance: {item.eligibility_relevance})")

    print("\n" + "=" * 70)
    print("[NOTE ON REAL HISTORICAL VERSIONS]")
    print("A real previous/historical Government Order version of PM-KISAN is not currently downloaded.")
    print("The system strictly operates on factually discovered documents and does not fabricate historical files.")
    print("=" * 70)


if __name__ == "__main__":
    main()
