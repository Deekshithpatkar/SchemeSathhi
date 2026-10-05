"""
Comprehensive Test Suite for Checkpoint 13: PostgreSQL Knowledge Base Persistence.
Covers all 18 required scenarios:
1. Create new scheme
2. Create first active version
3. Store eligibility rule
4. Store exclusion rule
5. Store rule evidence
6. Retrieve current rules
7. Create second version
8. Archive old version
9. Activate new version
10. Retrieve historical versions
11. Same document hash is idempotent
12. Two active versions are prevented
13. Review-required version does not replace ACTIVE
14. Transaction rollback on failure
15. Update log creation
16. No duplicate rules
17. Historical version rules remain unchanged
18. Multiple schemes remain isolated
"""

import pytest
import psycopg
from psycopg.rows import dict_row
from datetime import datetime, timezone
from app.db import get_connection, init_db
from app.schemas import RuleItem, SchemeEvidence, SchemeExtraction
from app.rule_comparison_schemas import RuleComparisonResult, RuleComparisonMetadata, RuleComparison
from app.knowledge_base import (
    create_scheme,
    get_scheme_by_key,
    create_scheme_version,
    get_version_by_hash,
    get_active_version,
    archive_version,
    activate_version,
    store_rule,
    store_rule_evidence,
    create_update_log,
    apply_knowledge_update,
    get_current_rules,
    get_historical_versions,
    get_rules_for_version,
)


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    """Ensure database tables and schema migrations are applied."""
    init_db()


@pytest.fixture(autouse=True)
def cleanup_test_schemes():
    """Clean up any test schemes created during testing before and after each test."""
    yield
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM schemes WHERE slug LIKE 'test-%';")
        conn.commit()


# ==============================================================================
# TEST 1: Create New Scheme
# ==============================================================================
def test_1_create_new_scheme():
    scheme_id = create_scheme(
        scheme_key="test-farmer-welfare",
        scheme_name="Karnataka Farmer Welfare Scheme",
        department="Agriculture Department",
    )
    assert isinstance(scheme_id, int)
    assert scheme_id > 0

    record = get_scheme_by_key("test-farmer-welfare")
    assert record is not None
    assert record["scheme_name"] == "Karnataka Farmer Welfare Scheme"
    assert record["department"] == "Agriculture Department"
    assert record["state"] == "Karnataka"


# ==============================================================================
# TEST 2: Create First Active Version
# ==============================================================================
def test_2_create_first_active_version():
    scheme_id = create_scheme("test-scheme-versioning", "Test Versioning Scheme")
    v_id = create_scheme_version(
        scheme_id=scheme_id,
        version_label="2024-v1",
        document_hash="hash_test_version_1",
        document_date="2024-04-01",
        status="ACTIVE",
    )
    assert v_id > 0

    active_ver = get_active_version(scheme_id)
    assert active_ver is not None
    assert active_ver["id"] == v_id
    assert active_ver["version_label"] == "2024-v1"
    assert active_ver["status"] == "ACTIVE"


# ==============================================================================
# TEST 3: Store Eligibility Rule
# ==============================================================================
def test_3_store_eligibility_rule():
    scheme_id = create_scheme("test-rules-scheme", "Test Rules Scheme")
    v_id = create_scheme_version(scheme_id, "v1", "hash_r1", status="ACTIVE")

    rule_item = RuleItem(
        rule="Annual family income must not exceed Rs. 2.5 lakh",
        type="eligibility",
        category="income",
        semantic_confidence=0.92,
    )
    rule_id = store_rule(v_id, rule_item)
    assert rule_id > 0

    rules_data = get_rules_for_version(v_id)
    assert len(rules_data["eligibility_rules"]) == 1
    r = rules_data["eligibility_rules"][0]
    assert r["rule"] == "Annual family income must not exceed Rs. 2.5 lakh"
    assert r["category"] == "income"
    assert r["type"] == "eligibility"


# ==============================================================================
# TEST 4: Store Exclusion Rule
# ==============================================================================
def test_4_store_exclusion_rule():
    scheme_id = create_scheme("test-exclusion-scheme", "Test Exclusion Scheme")
    v_id = create_scheme_version(scheme_id, "v1", "hash_ex1", status="ACTIVE")

    ex_item = RuleItem(
        rule="Government employees are not eligible",
        type="exclusion",
        category="government_employee",
        semantic_confidence=0.95,
    )
    ex_id = store_rule(v_id, ex_item)
    assert ex_id > 0

    rules_data = get_rules_for_version(v_id)
    assert len(rules_data["exclusion_rules"]) == 1
    ex = rules_data["exclusion_rules"][0]
    assert ex["rule"] == "Government employees are not eligible"
    assert ex["category"] == "government_employee"
    assert ex["type"] == "exclusion"


# ==============================================================================
# TEST 5: Store Rule Evidence
# ==============================================================================
def test_5_store_rule_evidence():
    scheme_id = create_scheme("test-evidence-scheme", "Test Evidence Scheme")
    v_id = create_scheme_version(scheme_id, "v1", "hash_ev1", status="ACTIVE")

    evidence = SchemeEvidence(
        page_number=3,
        section="Section 4.1 Eligibility Criteria",
        source_text="Annual family income must not exceed Rs. 2.5 lakh per annum.",
        ocr_confidence=98.5,
    )
    rule_item = RuleItem(
        rule="Annual family income must not exceed Rs. 2.5 lakh",
        type="eligibility",
        category="income",
        evidence=evidence,
    )
    rule_id = store_rule(v_id, rule_item)

    rules_data = get_rules_for_version(v_id)
    r = rules_data["eligibility_rules"][0]
    assert len(r["evidence"]) == 1
    ev = r["evidence"][0]
    assert ev["page_number"] == 3
    assert ev["section"] == "Section 4.1 Eligibility Criteria"
    assert ev["evidence_text"] == "Annual family income must not exceed Rs. 2.5 lakh per annum."
    assert float(ev["ocr_confidence"]) == 98.5


# ==============================================================================
# TEST 6: Retrieve Current Rules
# ==============================================================================
def test_6_retrieve_current_rules():
    scheme_id = create_scheme("test-current-rules", "Current Rules Query Test")
    v_id = create_scheme_version(scheme_id, "2024-v1", "hash_curr_1", status="ACTIVE")

    store_rule(v_id, RuleItem(rule="Resident of Karnataka", type="eligibility", category="residency"))
    store_rule(v_id, RuleItem(rule="Government employees excluded", type="exclusion", category="government_employee"))

    curr = get_current_rules("test-current-rules")
    assert curr is not None
    assert curr["scheme_name"] == "Current Rules Query Test"
    assert curr["active_version"]["version_label"] == "2024-v1"
    assert len(curr["eligibility_rules"]) == 1
    assert curr["eligibility_rules"][0]["category"] == "residency"
    assert len(curr["exclusion_rules"]) == 1
    assert curr["exclusion_rules"][0]["category"] == "government_employee"


# ==============================================================================
# TEST 7: Create Second Version
# ==============================================================================
def test_7_create_second_version():
    scheme_id = create_scheme("test-multi-ver", "Multi Version Scheme")
    v1_id = create_scheme_version(scheme_id, "v1", "hash_v1_multi", status="ACTIVE")
    # Store second version with status REVIEW (before activation)
    v2_id = create_scheme_version(scheme_id, "v2", "hash_v2_multi", status="REVIEW")

    assert v2_id != v1_id
    active = get_active_version(scheme_id)
    assert active["id"] == v1_id


# ==============================================================================
# TEST 8: Archive Old Version
# ==============================================================================
def test_8_archive_old_version():
    scheme_id = create_scheme("test-archive-ver", "Archive Version Test")
    v1_id = create_scheme_version(scheme_id, "v1", "hash_arch_1", status="ACTIVE")

    archive_version(v1_id)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM scheme_versions WHERE id = %s;", (v1_id,))
            status = cur.fetchone()[0]
    assert status == "ARCHIVED"

    # Scheme now has no active version
    assert get_active_version(scheme_id) is None


# ==============================================================================
# TEST 9: Activate New Version
# ==============================================================================
def test_9_activate_new_version():
    scheme_id = create_scheme("test-activate-ver", "Activate Version Test")
    v1_id = create_scheme_version(scheme_id, "v1", "hash_act_1", status="ACTIVE")
    v2_id = create_scheme_version(scheme_id, "v2", "hash_act_2", status="REVIEW")

    # Transition: Archive v1, Activate v2
    archive_version(v1_id)
    activate_version(v2_id)

    active = get_active_version(scheme_id)
    assert active is not None
    assert active["id"] == v2_id
    assert active["version_label"] == "v2"
    assert active["status"] == "ACTIVE"


# ==============================================================================
# TEST 10: Retrieve Historical Versions
# ==============================================================================
def test_10_retrieve_historical_versions():
    scheme_id = create_scheme("test-hist-versions", "Historical Versions Query Test")
    v1_id = create_scheme_version(scheme_id, "v1", "hash_h1", status="ACTIVE")
    archive_version(v1_id)
    v2_id = create_scheme_version(scheme_id, "v2", "hash_h2", status="ACTIVE")

    history = get_historical_versions("test-hist-versions")
    assert len(history) == 2
    assert history[0]["id"] == v1_id
    assert history[0]["status"] == "ARCHIVED"
    assert history[1]["id"] == v2_id
    assert history[1]["status"] == "ACTIVE"


# ==============================================================================
# TEST 11: Same Document Hash is Idempotent
# ==============================================================================
def test_11_same_document_hash_is_idempotent():
    scheme_key = "test-idempotent-scheme"
    doc_hash = "sha256_exact_duplicate_hash_123"

    res1 = apply_knowledge_update(
        scheme_key=scheme_key,
        scheme_name="Idempotency Test Scheme",
        document_hash=doc_hash,
        version_label="2024-v1",
        rules_extraction={"eligibility_rules": [{"rule": "Must be 18 years old", "type": "eligibility", "category": "age"}]},
    )
    assert res1["status"] == "activated"
    v_id = res1["version_id"]

    # Second run with exact same document hash
    res2 = apply_knowledge_update(
        scheme_key=scheme_key,
        scheme_name="Idempotency Test Scheme",
        document_hash=doc_hash,
        version_label="2024-v1",
        rules_extraction={"eligibility_rules": [{"rule": "Must be 18 years old", "type": "eligibility", "category": "age"}]},
    )
    assert res2["status"] == "already_exists"
    assert res2["version_id"] == v_id
    assert res2["action_taken"] == "none"

    # Verify no duplicate versions created
    history = get_historical_versions(scheme_key)
    assert len(history) == 1


# ==============================================================================
# TEST 12: Two Active Versions are Prevented
# ==============================================================================
def test_12_two_active_versions_are_prevented():
    scheme_id = create_scheme("test-active-constraint", "Constraint Enforcement Test")
    create_scheme_version(scheme_id, "v1", "hash_const_1", status="ACTIVE")

    # Attempting to insert a second ACTIVE version for the same scheme violates partial unique index
    with pytest.raises(psycopg.errors.UniqueViolation):
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO scheme_versions (scheme_id, version_label, document_hash, status)
                    VALUES (%s, 'v2', 'hash_const_2', 'ACTIVE');
                    """,
                    (scheme_id,),
                )


# ==============================================================================
# TEST 13: Review-Required Version Does Not Replace ACTIVE
# ==============================================================================
def test_13_review_required_version_does_not_replace_active():
    scheme_key = "test-review-safety"
    res1 = apply_knowledge_update(
        scheme_key=scheme_key,
        scheme_name="Review Safety Scheme",
        document_hash="hash_safe_v1",
        version_label="v1",
        rules_extraction={"eligibility_rules": [{"rule": "Income under 2.5L", "type": "eligibility", "category": "income"}]},
    )
    assert res1["status"] == "activated"
    v1_id = res1["version_id"]

    # Second incoming update requires review
    res2 = apply_knowledge_update(
        scheme_key=scheme_key,
        scheme_name="Review Safety Scheme",
        document_hash="hash_safe_v2",
        version_label="v2",
        rules_extraction={"eligibility_rules": [{"rule": "Ambiguous discretionary rule", "type": "eligibility", "category": "other"}]},
        force_review=True,
    )
    assert res2["status"] == "review_stored"
    assert res2["version_status"] == "REVIEW"

    # Check database state: v1 remains ACTIVE, v2 is stored as REVIEW
    curr = get_current_rules(scheme_key)
    assert curr["active_version"]["id"] == v1_id
    assert curr["active_version"]["version_label"] == "v1"

    history = get_historical_versions(scheme_key)
    assert len(history) == 2
    assert history[0]["status"] == "ACTIVE"
    assert history[1]["status"] == "REVIEW"


# ==============================================================================
# TEST 14: Transaction Rollback on Failure
# ==============================================================================
def test_14_transaction_rollback_on_failure():
    scheme_key = "test-rollback-scheme"
    scheme_id = create_scheme(scheme_key, "Rollback Scheme")
    v1_id = create_scheme_version(scheme_id, "v1", "hash_rb_v1", status="ACTIVE")

    # Execute custom transactional block that fails midway
    with pytest.raises(ValueError):
        with get_connection() as conn:
            with conn.transaction():
                # Step 1: archive v1
                archive_version(v1_id, conn=conn)
                # Step 2: create v2
                create_scheme_version(scheme_id, "v2", "hash_rb_v2", status="ACTIVE", conn=conn)
                # Step 3: raise failure
                raise ValueError("Simulated catastrophic crash during version transition!")

    # Check that database rolled back: v1 must STILL be ACTIVE, v2 must NOT exist
    active = get_active_version(scheme_id)
    assert active is not None
    assert active["id"] == v1_id
    assert active["status"] == "ACTIVE"

    v2 = get_version_by_hash(scheme_id, "hash_rb_v2")
    assert v2 is None


# ==============================================================================
# TEST 15: Update Log Creation
# ==============================================================================
def test_15_update_log_creation():
    scheme_key = "test-audit-logs"
    apply_knowledge_update(
        scheme_key=scheme_key,
        scheme_name="Audit Log Scheme",
        document_hash="hash_log_v1",
        version_label="v1",
    )
    apply_knowledge_update(
        scheme_key=scheme_key,
        scheme_name="Audit Log Scheme",
        document_hash="hash_log_v2",
        version_label="v2",
        comparison_result={
            "summary": "Income limit raised from 2.5L to 3.0L",
            "eligibility_relevance": "clearly_relevant",
            "review_required": False,
        },
    )

    scheme = get_scheme_by_key(scheme_key)
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT change_type, summary, eligibility_relevance, status
                FROM update_logs
                WHERE scheme_id = %s
                ORDER BY id ASC;
                """,
                (scheme["id"],),
            )
            logs = cur.fetchall()

    assert len(logs) == 2
    assert logs[0]["change_type"] == "INITIAL_ACTIVE"
    assert logs[1]["change_type"] == "MODIFIED"
    assert "raised from 2.5L to 3.0L" in logs[1]["summary"]
    assert logs[1]["eligibility_relevance"] == "clearly_relevant"


# ==============================================================================
# TEST 16: No Duplicate Rules
# ==============================================================================
def test_16_no_duplicate_rules():
    scheme_id = create_scheme("test-dedup-rules", "Rule Dedup Test")
    v_id = create_scheme_version(scheme_id, "v1", "hash_dedup_1", status="ACTIVE")

    rule = RuleItem(rule="Karnataka resident", type="eligibility", category="residency")
    rid1 = store_rule(v_id, rule)
    rid2 = store_rule(v_id, rule)

    # Identical rule within same version should return same ID without inserting duplicate
    assert rid1 == rid2
    rules_data = get_rules_for_version(v_id)
    assert len(rules_data["eligibility_rules"]) == 1


# ==============================================================================
# TEST 17: Historical Version Rules Remain Unchanged
# ==============================================================================
def test_17_historical_version_rules_remain_unchanged():
    scheme_key = "test-history-immutability"
    # Version 1 with threshold Rs. 2.5L
    res1 = apply_knowledge_update(
        scheme_key=scheme_key,
        scheme_name="Immutability Scheme",
        document_hash="hash_imm_v1",
        version_label="v1",
        rules_extraction={"eligibility_rules": [{"rule": "Income <= Rs. 2.5 lakh", "type": "eligibility", "category": "income"}]},
    )
    v1_id = res1["version_id"]

    # Version 2 with threshold Rs. 3.0L
    res2 = apply_knowledge_update(
        scheme_key=scheme_key,
        scheme_name="Immutability Scheme",
        document_hash="hash_imm_v2",
        version_label="v2",
        rules_extraction={"eligibility_rules": [{"rule": "Income <= Rs. 3.0 lakh", "type": "eligibility", "category": "income"}]},
    )
    v2_id = res2["version_id"]

    # Verify v1 historical rules are unchanged and still queryable
    v1_rules = get_rules_for_version(v1_id)
    assert len(v1_rules["eligibility_rules"]) == 1
    assert v1_rules["eligibility_rules"][0]["rule"] == "Income <= Rs. 2.5 lakh"

    # Verify v2 active rules reflect new criteria
    v2_rules = get_rules_for_version(v2_id)
    assert len(v2_rules["eligibility_rules"]) == 1
    assert v2_rules["eligibility_rules"][0]["rule"] == "Income <= Rs. 3.0 lakh"

    # Both versions are preserved in history
    history = get_historical_versions(scheme_key)
    assert len(history) == 2
    assert history[0]["status"] == "ARCHIVED"
    assert history[1]["status"] == "ACTIVE"


# ==============================================================================
# TEST 18: Multiple Schemes Remain Isolated
# ==============================================================================
def test_18_multiple_schemes_remain_isolated():
    # Scheme A (e.g. Ganga Kalyana)
    apply_knowledge_update(
        scheme_key="test-scheme-ganga-kalyana",
        scheme_name="Ganga Kalyana Scheme",
        document_hash="hash_ganga_v1",
        version_label="2024-v1",
        rules_extraction={"eligibility_rules": [{"rule": "Small & marginal farmers only", "type": "eligibility", "category": "farmer_category"}]},
    )

    # Scheme B (e.g. Yuva Nidhi)
    apply_knowledge_update(
        scheme_key="test-scheme-yuva-nidhi",
        scheme_name="Yuva Nidhi Scheme",
        document_hash="hash_yuva_v1",
        version_label="2024-v1",
        rules_extraction={"eligibility_rules": [{"rule": "Unemployed graduates only", "type": "eligibility", "category": "employment_status"}]},
    )

    # Update Scheme B to v2
    apply_knowledge_update(
        scheme_key="test-scheme-yuva-nidhi",
        scheme_name="Yuva Nidhi Scheme",
        document_hash="hash_yuva_v2",
        version_label="2025-v2",
        rules_extraction={"eligibility_rules": [{"rule": "Unemployed graduates and diploma holders", "type": "eligibility", "category": "employment_status"}]},
    )

    # Verify Scheme A is completely unaffected
    ganga_curr = get_current_rules("test-scheme-ganga-kalyana")
    assert ganga_curr["active_version"]["version_label"] == "2024-v1"
    assert len(ganga_curr["eligibility_rules"]) == 1
    assert ganga_curr["eligibility_rules"][0]["category"] == "farmer_category"

    # Verify Scheme B has v2 active and v1 archived
    yuva_curr = get_current_rules("test-scheme-yuva-nidhi")
    assert yuva_curr["active_version"]["version_label"] == "2025-v2"
    yuva_hist = get_historical_versions("test-scheme-yuva-nidhi")
    assert len(yuva_hist) == 2
