"""
Checkpoint 13 Execution Script: PostgreSQL Knowledge Base Persistence.
Demonstrates:
1. Real Document Rule Persistence: Real CP10 extraction from PM-KISAN Karnataka document (0 rules).
2. Idempotency Check: Running the same PM-KISAN document again.
3. Controlled Test Scenario:
   - Version 1: Income <= Rs. 2.5 Lakh
   - Version 2: Income <= Rs. 3.0 Lakh
   - Verifying Version 1 = ARCHIVED, Version 2 = ACTIVE, history preserved, and rules queryable.

All controlled policy modifications are explicitly labeled as test simulations.
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import EXTRACTED_RULES_DIR
from app.db import init_db, get_connection
from app.knowledge_base import (
    apply_knowledge_update,
    get_current_rules,
    get_historical_versions,
    get_rules_for_version,
    get_scheme_by_key,
)


def main():
    print("=" * 75)
    print("CHECKPOINT 13: POSTGRESQL KNOWLEDGE BASE PERSISTENCE")
    print("=" * 75)

    # Initialize tables and migration columns
    init_db()

    pmkisan_rules_path = EXTRACTED_RULES_DIR / "e75996bb_PM-KISANSchemeguidelinesfinal_rules.json"

    # =========================================================================
    # 1. Real Document Persistence (PM-KISAN guidelines extraction)
    # =========================================================================
    print("\n[SCENARIO 1] Real Document Extraction Persistence:")
    if pmkisan_rules_path.exists():
        with open(pmkisan_rules_path, "r", encoding="utf-8") as f:
            pmkisan_raw = json.load(f)

        meta = pmkisan_raw.get("extraction_metadata", {})
        doc_hash = meta.get("document_hash") or "e75996bb31b6e6cf1e4a5009a7b69ffabeb8619bc2ad6e2d1d07ec05ec6866b1"
        scheme_key = "pradhan-mantri-kisan-samman-nidhi"
        scheme_name = pmkisan_raw.get("scheme_name") or "Pradhan Mantri Kisan Samman Nidhi"

        print(f"Loading real CP10 extraction from: {pmkisan_rules_path.name}")
        print(f"  - Extracted Eligibility Rules: {len(pmkisan_raw.get('eligibility_rules', []))}")
        print(f"  - Extracted Exclusion Rules:   {len(pmkisan_raw.get('exclusion_rules', []))}")

        res_real = apply_knowledge_update(
            scheme_key=scheme_key,
            scheme_name=scheme_name,
            document_hash=doc_hash,
            version_label="2019-guidelines",
            department="Agriculture Department",
            document_date="2019-07-04",
            rules_extraction=pmkisan_raw,
        )

        print(f"  - Update Status:         {res_real['status']}")
        print(f"  - Scheme ID:             {res_real['scheme_id']}")
        print(f"  - Version ID:            {res_real['version_id']}")
        print(f"  - Action Taken:          {res_real['action_taken']}")

        # Query active rules from PostgreSQL
        curr = get_current_rules(scheme_key)
        print(f"  - Database Active Version: {curr['active_version']['version_label'] if curr['active_version'] else 'None'}")
        print(f"  - Active Eligibility Rules: {len(curr['eligibility_rules'])}")
        print(f"  - Active Exclusion Rules:   {len(curr['exclusion_rules'])}")

        # =====================================================================
        # 2. Idempotency Check (Re-running same document hash)
        # =====================================================================
        print("\n[SCENARIO 2] Idempotency Verification (Re-running same document hash):")
        res_idempotent = apply_knowledge_update(
            scheme_key=scheme_key,
            scheme_name=scheme_name,
            document_hash=doc_hash,
            version_label="2019-guidelines",
            rules_extraction=pmkisan_raw,
        )
        print(f"  - Status:                {res_idempotent['status']}")
        print(f"  - Action Taken:          {res_idempotent['action_taken']}")
        print(f"  - Message:               {res_idempotent['message']}")
    else:
        print(f"[WARNING] CP10 extraction file not found: {pmkisan_rules_path}")

    # =========================================================================
    # 3. Controlled Test Scenario: Historical Version Evolution
    # =========================================================================
    print("\n[SCENARIO 3] Controlled Test - Historical Version Evolution:")
    print("  (Simulated test: Scheme policy evolves from Version 1 [<= 2.5L] to Version 2 [<= 3.0L])")

    controlled_scheme_key = "test-karnataka-raitha-bandhu"
    controlled_scheme_name = "Karnataka Raitha Bandhu Scheme (Test)"

    # Version 1: Income <= Rs. 2.5 Lakh
    print("\n  --> Applying Version 1 (Income <= Rs. 2.5 Lakh)...")
    v1_extraction = {
        "scheme_name": controlled_scheme_name,
        "eligibility_rules": [
            {
                "rule": "Annual family income must not exceed Rs. 2.5 lakh",
                "type": "eligibility",
                "category": "income",
                "evidence": {
                    "page_number": 2,
                    "section": "Section 3.1",
                    "source_text": "Annual family income must not exceed Rs. 2.5 lakh",
                    "ocr_confidence": 98.0,
                },
            }
        ],
        "exclusion_rules": [
            {
                "rule": "Government employees are not eligible",
                "type": "exclusion",
                "category": "government_employee",
                "evidence": {
                    "page_number": 3,
                    "section": "Section 4",
                    "source_text": "Government employees are not eligible",
                    "ocr_confidence": 99.0,
                },
            }
        ],
    }

    res_v1 = apply_knowledge_update(
        scheme_key=controlled_scheme_key,
        scheme_name=controlled_scheme_name,
        document_hash="controlled_hash_v1_2024",
        version_label="2024-v1",
        department="Agriculture Department",
        document_date="2024-04-01",
        rules_extraction=v1_extraction,
    )
    print(f"      Status: {res_v1['status']} (Version ID: {res_v1['version_id']}, Status: {res_v1['version_status']})")

    # Version 2: Income <= Rs. 3.0 Lakh
    print("\n  --> Applying Version 2 (Income <= Rs. 3.0 Lakh)...")
    v2_extraction = {
        "scheme_name": controlled_scheme_name,
        "eligibility_rules": [
            {
                "rule": "Annual family income must not exceed Rs. 3.0 lakh",
                "type": "eligibility",
                "category": "income",
                "evidence": {
                    "page_number": 2,
                    "section": "Section 3.1",
                    "source_text": "Annual family income must not exceed Rs. 3.0 lakh",
                    "ocr_confidence": 99.0,
                },
            }
        ],
        "exclusion_rules": [
            {
                "rule": "Government employees are not eligible",
                "type": "exclusion",
                "category": "government_employee",
                "evidence": {
                    "page_number": 3,
                    "section": "Section 4",
                    "source_text": "Government employees are not eligible",
                    "ocr_confidence": 99.0,
                },
            }
        ],
    }

    v2_comparison = {
        "summary": "Annual income limit increased from Rs. 2.5 Lakh to Rs. 3.0 Lakh.",
        "eligibility_relevance": "clearly_relevant",
        "review_required": False,
    }

    res_v2 = apply_knowledge_update(
        scheme_key=controlled_scheme_key,
        scheme_name=controlled_scheme_name,
        document_hash="controlled_hash_v2_2025",
        version_label="2025-v2",
        department="Agriculture Department",
        document_date="2025-04-01",
        rules_extraction=v2_extraction,
        comparison_result=v2_comparison,
    )
    print(f"      Status: {res_v2['status']} (Version ID: {res_v2['version_id']}, Status: {res_v2['version_status']})")
    print(f"      Old Active Version ID Archived: {res_v2['old_active_version_id']}")

    # Verify Historical State in PostgreSQL
    print("\n  --> Querying Historical Versions from PostgreSQL:")
    history = get_historical_versions(controlled_scheme_key)
    for h in history:
        print(f"      * Version ID {h['id']}: Label='{h['version_label']}', Status='{h['status']}', Hash='{h['document_hash']}'")

    # Verify Historical Rules Immutability
    print("\n  --> Verifying Rules Immutability:")
    v1_rules = get_rules_for_version(res_v1["version_id"])
    print(f"      Historical Version 1 Rules (ID: {res_v1['version_id']}):")
    for r in v1_rules["eligibility_rules"]:
        print(f"        - [ELIGIBILITY] {r['rule']} (Category: {r['category']})")

    v2_rules = get_rules_for_version(res_v2["version_id"])
    print(f"      Current Version 2 Rules (ID: {res_v2['version_id']}):")
    for r in v2_rules["eligibility_rules"]:
        print(f"        - [ELIGIBILITY] {r['rule']} (Category: {r['category']})")

    # Verify Currently Active Rules
    curr_active = get_current_rules(controlled_scheme_key)
    print(f"\n  --> Current Active Scheme Query:")
    print(f"      Active Version: {curr_active['active_version']['version_label']}")
    print(f"      Active Rule:    {curr_active['eligibility_rules'][0]['rule']}")

    # Clean up controlled test records
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM schemes WHERE slug = %s;", (controlled_scheme_key,))
        conn.commit()

    print("\n" + "=" * 75)
    print("CHECKPOINT 13 EXECUTION COMPLETE")
    print("=" * 75)


if __name__ == "__main__":
    main()
