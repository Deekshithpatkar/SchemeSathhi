"""
Checkpoint 13: Knowledge Base Persistence and Version Management Module.
Persists validated scheme versions and their candidate eligibility/exclusion rules into PostgreSQL.

Key Invariants:
1. Never overwrite historical records: old versions transition to ARCHIVED, never deleted or mutated.
2. At most one ACTIVE version per scheme at any time.
3. Stable version identity via document SHA-256 and version labels.
4. Idempotent: identical document hashes produce no duplicate versions or rules.
5. Review isolation: uncertain/review-flagged versions are stored as REVIEW without replacing ACTIVE.
6. Atomic ACID updates via PostgreSQL transactions.
"""

import json
from contextlib import contextmanager
from datetime import datetime, date
from typing import Optional, Dict, Any, List, Union, Tuple
from psycopg.rows import dict_row

from app.db import get_connection
from app.config import setup_logger
from app.schemas import RuleItem, SchemeEvidence, SchemeExtraction
from app.rule_comparison_schemas import RuleComparisonResult
from app.versioning import make_slug, parse_date_to_iso

logger = setup_logger("knowledge_base")


@contextmanager
def get_db_cursor(conn: Optional[Any] = None, autocommit: bool = False):
    """
    Context manager yielding a dictionary cursor.
    Uses existing connection if provided; otherwise manages a new connection.
    """
    if conn is not None:
        with conn.cursor(row_factory=dict_row) as cur:
            yield cur
    else:
        with get_connection() as new_conn:
            if autocommit:
                new_conn.autocommit = True
            with new_conn.cursor(row_factory=dict_row) as cur:
                yield cur
            if not autocommit:
                new_conn.commit()


# ==============================================================================
# 1. Scheme Management
# ==============================================================================

def create_scheme(
    scheme_key: str,
    scheme_name: str,
    department: Optional[str] = None,
    state: str = "Karnataka",
    conn: Optional[Any] = None,
) -> int:
    """
    Creates or retrieves a master scheme record by unique scheme_key (slug).
    Returns scheme ID.
    """
    slug = make_slug(scheme_key)
    with get_db_cursor(conn) as cur:
        cur.execute(
            """
            INSERT INTO schemes (slug, name, department, state)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (slug) DO UPDATE
            SET name = EXCLUDED.name,
                department = COALESCE(EXCLUDED.department, schemes.department),
                updated_at = CURRENT_TIMESTAMP
            RETURNING id;
            """,
            (slug, scheme_name, department, state),
        )
        row = cur.fetchone()
        return row["id"]


def get_scheme_by_key(
    scheme_key: str,
    conn: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """
    Looks up master scheme by scheme_key (slug).
    """
    slug = make_slug(scheme_key)
    with get_db_cursor(conn) as cur:
        cur.execute(
            """
            SELECT id, slug, slug AS scheme_key, name, name AS scheme_name, department, state, created_at, updated_at
            FROM schemes
            WHERE slug = %s;
            """,
            (slug,),
        )
        return cur.fetchone()


# ==============================================================================
# 2. Scheme Version Management
# ==============================================================================

def create_scheme_version(
    scheme_id: int,
    version_label: str,
    document_hash: Optional[str] = None,
    document_date: Optional[Union[str, date, datetime]] = None,
    source_url: Optional[str] = None,
    status: str = "ACTIVE",
    document_id: Optional[int] = None,
    extracted_text: Optional[str] = None,
    conn: Optional[Any] = None,
) -> int:
    """
    Creates a new scheme version with a given status ('ACTIVE', 'ARCHIVED', 'REVIEW').
    Returns version ID.
    """
    valid_statuses = {"ACTIVE", "ARCHIVED", "REVIEW"}
    status_upper = status.upper().strip()
    if status_upper not in valid_statuses:
        raise ValueError(f"Invalid status '{status}'. Must be one of {valid_statuses}")

    iso_date = parse_date_to_iso(str(document_date)) if document_date else None

    with get_db_cursor(conn) as cur:
        cur.execute(
            """
            INSERT INTO scheme_versions (
                scheme_id, version_label, document_id, document_hash,
                document_date, published_date, source_url, status, extracted_text
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                scheme_id,
                version_label,
                document_id,
                document_hash,
                iso_date,
                iso_date,
                source_url,
                status_upper,
                extracted_text,
            ),
        )
        row = cur.fetchone()
        return row["id"]


def get_version_by_hash(
    scheme_id: int,
    document_hash: str,
    conn: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """
    Retrieves a scheme version by document SHA-256 hash.
    Used to guarantee idempotency.
    """
    if not document_hash:
        return None
    with get_db_cursor(conn) as cur:
        cur.execute(
            """
            SELECT id, scheme_id, version_label, document_hash, document_date, source_url, status, created_at
            FROM scheme_versions
            WHERE scheme_id = %s AND document_hash = %s;
            """,
            (scheme_id, document_hash),
        )
        return cur.fetchone()


def get_active_version(
    scheme_id: int,
    conn: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """
    Returns the currently ACTIVE version for a scheme, if one exists.
    """
    with get_db_cursor(conn) as cur:
        cur.execute(
            """
            SELECT id, scheme_id, version_label, document_hash, document_date, source_url, status, created_at
            FROM scheme_versions
            WHERE scheme_id = %s AND status = 'ACTIVE';
            """,
            (scheme_id,),
        )
        return cur.fetchone()


def archive_version(
    version_id: int,
    conn: Optional[Any] = None,
) -> None:
    """
    Transitions an active version to ARCHIVED status.
    Historical records and rules remain permanently preserved.
    """
    with get_db_cursor(conn) as cur:
        cur.execute(
            """
            UPDATE scheme_versions
            SET status = 'ARCHIVED'
            WHERE id = %s;
            """,
            (version_id,),
        )


def activate_version(
    version_id: int,
    conn: Optional[Any] = None,
) -> None:
    """
    Marks a scheme version as ACTIVE.
    Note: Caller must ensure existing active version is archived first,
    or PostgreSQL partial unique index will raise UniqueViolation.
    """
    with get_db_cursor(conn) as cur:
        cur.execute(
            """
            UPDATE scheme_versions
            SET status = 'ACTIVE'
            WHERE id = %s;
            """,
            (version_id,),
        )


# ==============================================================================
# 3. Rule & Evidence Storage
# ==============================================================================

def store_rule(
    scheme_version_id: int,
    rule: Union[RuleItem, Dict[str, Any]],
    conn: Optional[Any] = None,
) -> int:
    """
    Stores an individual eligibility or exclusion rule for a scheme version.
    Deduplicates identical rules within the same version.
    If evidence is present on the rule, stores it in rule_evidence.
    Returns rule ID.
    """
    if isinstance(rule, RuleItem):
        rule_text = rule.rule
        rule_type = (rule.type or "eligibility").lower().strip()
        category = rule.category or "other"
        val = rule.value
        confidence = float(rule.semantic_confidence)
        review_req = bool(rule.review_required)
        review_reasons = rule.review_reasons or []
        evidence = rule.evidence
        rule_data = rule.model_dump()
    elif isinstance(rule, dict):
        rule_text = rule.get("rule", "")
        rule_type = (rule.get("type") or "eligibility").lower().strip()
        category = rule.get("category") or "other"
        val = rule.get("value")
        confidence = float(rule.get("semantic_confidence", 0.85))
        review_req = bool(rule.get("review_required", False))
        review_reasons = rule.get("review_reasons", [])
        evidence = rule.get("evidence")
        rule_data = rule
    else:
        raise TypeError("rule must be a RuleItem instance or dictionary")

    # Serialize JSON values
    val_json = json.dumps(val) if val is not None else None
    reasons_json = json.dumps(review_reasons)
    rule_data_json = json.dumps(rule_data)

    with get_db_cursor(conn) as cur:
        # Deduplication check within this version
        cur.execute(
            """
            SELECT id FROM eligibility_rules
            WHERE scheme_version_id = %s AND rule = %s AND type = %s AND category = %s;
            """,
            (scheme_version_id, rule_text, rule_type, category),
        )
        existing = cur.fetchone()
        if existing:
            return existing["id"]

        cur.execute(
            """
            INSERT INTO eligibility_rules (
                scheme_version_id, rule, type, category, value,
                semantic_confidence, review_required, review_reasons, rule_data
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                scheme_version_id,
                rule_text,
                rule_type,
                category,
                val_json,
                confidence,
                review_req,
                reasons_json,
                rule_data_json,
            ),
        )
        rule_id = cur.fetchone()["id"]

        # Store grounding evidence if present
        if evidence:
            store_rule_evidence(rule_id, evidence, conn=cur.connection)

        return rule_id


def store_rule_evidence(
    rule_id: int,
    evidence: Union[SchemeEvidence, Dict[str, Any]],
    source_url: Optional[str] = None,
    conn: Optional[Any] = None,
) -> int:
    """
    Stores physical grounding evidence for an eligibility/exclusion rule.
    Returns evidence ID.
    """
    if isinstance(evidence, SchemeEvidence):
        page_num = evidence.page_number
        section = evidence.section
        text = evidence.source_text
        ocr_conf = evidence.ocr_confidence
    elif isinstance(evidence, dict):
        page_num = evidence.get("page_number", 1)
        section = evidence.get("section")
        text = evidence.get("source_text") or evidence.get("evidence_text")
        ocr_conf = evidence.get("ocr_confidence")
    else:
        raise TypeError("evidence must be a SchemeEvidence instance or dictionary")

    with get_db_cursor(conn) as cur:
        cur.execute(
            """
            INSERT INTO rule_evidence (
                rule_id, page_number, section, evidence_text, source_url, ocr_confidence
            )
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (rule_id, page_num, section, text, source_url, ocr_conf),
        )
        return cur.fetchone()["id"]


# ==============================================================================
# 4. Audit Log
# ==============================================================================

def create_update_log(
    scheme_id: int,
    old_version_id: Optional[int],
    new_version_id: Optional[int],
    change_type: str,
    summary: str,
    eligibility_relevance: str,
    changes: Optional[Dict[str, Any]] = None,
    status: Optional[str] = None,
    conn: Optional[Any] = None,
) -> int:
    """
    Creates an audit log entry for version transitions and update events.
    """
    changes_json = json.dumps(changes) if changes is not None else None
    with get_db_cursor(conn) as cur:
        cur.execute(
            """
            INSERT INTO update_logs (
                scheme_id, old_version_id, new_version_id, change_type,
                summary, eligibility_relevance, changes, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                scheme_id,
                old_version_id,
                new_version_id,
                change_type,
                summary,
                eligibility_relevance,
                changes_json,
                status,
            ),
        )
        return cur.fetchone()["id"]


# ==============================================================================
# 5. Master Transactional Knowledge Base Update (CP13 Workflow)
# ==============================================================================

def apply_knowledge_update(
    scheme_key: str,
    scheme_name: str,
    document_hash: str,
    version_label: str,
    department: Optional[str] = None,
    document_date: Optional[Union[str, date, datetime]] = None,
    source_url: Optional[str] = None,
    rules_extraction: Optional[Union[Dict[str, Any], SchemeExtraction]] = None,
    comparison_result: Optional[Union[Dict[str, Any], RuleComparisonResult]] = None,
    force_review: bool = False,
    conn: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Atomic transactional knowledge base update for CP13:
    1. Identifies/creates master scheme.
    2. Enforces idempotency: if document_hash exists for this scheme, returns 'already_exists'.
    3. Evaluates review flags:
       - If force_review, or comparison review_required, or uncertain relevance:
         New version is stored with status='REVIEW'.
         Current ACTIVE version remains untouched and ACTIVE.
       - Otherwise:
         Current ACTIVE version is transitioned to ARCHIVED.
         New version is stored with status='ACTIVE'.
    4. Stores all eligibility and exclusion rules with grounded evidence.
    5. Writes structured audit update log.
    6. Guarantees rollback on any failure.
    """
    def _execute_update(active_conn):
        # 1. Identify or create master scheme
        scheme_id = create_scheme(
            scheme_key=scheme_key,
            scheme_name=scheme_name,
            department=department,
            conn=active_conn,
        )

        # 2. Check for duplicate document hash (Idempotency)
        existing_version = get_version_by_hash(scheme_id, document_hash, conn=active_conn)
        if existing_version:
            logger.info(
                f"Idempotency hit: Version with hash {document_hash[:10]}... already exists "
                f"(ID: {existing_version['id']}, Label: {existing_version['version_label']}). Skipping update."
            )
            return {
                "status": "already_exists",
                "scheme_id": scheme_id,
                "version_id": existing_version["id"],
                "version_label": existing_version["version_label"],
                "current_status": existing_version["status"],
                "action_taken": "none",
                "message": f"Document hash {document_hash} already exists as version {existing_version['version_label']}.",
            }

        # 3. Determine if review is required
        needs_review = force_review
        summary = ""
        relevance = "none"

        if comparison_result is not None:
            if isinstance(comparison_result, RuleComparisonResult):
                needs_review = needs_review or comparison_result.review_required or (comparison_result.eligibility_relevance == "uncertain")
                summary = comparison_result.summary
                relevance = comparison_result.eligibility_relevance
            elif isinstance(comparison_result, dict):
                needs_review = needs_review or comparison_result.get("review_required", False) or (comparison_result.get("eligibility_relevance") == "uncertain")
                summary = comparison_result.get("summary", "")
                relevance = comparison_result.get("eligibility_relevance", "none")

        if rules_extraction is not None:
            if isinstance(rules_extraction, SchemeExtraction):
                needs_review = needs_review or rules_extraction.review_required
            elif isinstance(rules_extraction, dict):
                needs_review = needs_review or rules_extraction.get("review_required", False)

        current_active = get_active_version(scheme_id, conn=active_conn)

        # 4. Version State Transition
        if needs_review:
            # Review required: Do NOT deactivate current ACTIVE version. Store as REVIEW.
            new_version_id = create_scheme_version(
                scheme_id=scheme_id,
                version_label=version_label,
                document_hash=document_hash,
                document_date=document_date,
                source_url=source_url,
                status="REVIEW",
                conn=active_conn,
            )
            target_status = "REVIEW"
            change_type = "REVIEW_REQUIRED"
            summary_log = summary or "New version stored with status=REVIEW for human verification. Active version preserved."
        else:
            # Genuinely accepted active version
            target_status = "ACTIVE"
            if current_active:
                archive_version(current_active["id"], conn=active_conn)
                change_type = "MODIFIED"
                summary_log = summary or f"Active version updated from '{current_active['version_label']}' to '{version_label}'."
            else:
                change_type = "INITIAL_ACTIVE"
                summary_log = summary or f"Initial active scheme version '{version_label}' established."

            new_version_id = create_scheme_version(
                scheme_id=scheme_id,
                version_label=version_label,
                document_hash=document_hash,
                document_date=document_date,
                source_url=source_url,
                status="ACTIVE",
                conn=active_conn,
            )

        # 5. Extract and persist candidate rules
        el_rules: List[Union[RuleItem, Dict[str, Any]]] = []
        ex_rules: List[Union[RuleItem, Dict[str, Any]]] = []

        if rules_extraction is not None:
            if isinstance(rules_extraction, SchemeExtraction):
                el_rules = rules_extraction.eligibility_rules
                ex_rules = rules_extraction.exclusion_rules
            elif isinstance(rules_extraction, dict):
                el_rules = rules_extraction.get("eligibility_rules", [])
                ex_rules = rules_extraction.get("exclusion_rules", [])

        rules_stored_count = 0
        for r in el_rules:
            store_rule(new_version_id, r, conn=active_conn)
            rules_stored_count += 1
        for r in ex_rules:
            store_rule(new_version_id, r, conn=active_conn)
            rules_stored_count += 1

        # 6. Create Update Log
        create_update_log(
            scheme_id=scheme_id,
            old_version_id=current_active["id"] if current_active else None,
            new_version_id=new_version_id,
            change_type=change_type,
            summary=summary_log,
            eligibility_relevance=relevance,
            changes={"rules_stored": rules_stored_count, "review_required": needs_review},
            status=target_status,
            conn=active_conn,
        )

        return {
            "status": "review_stored" if needs_review else "activated",
            "scheme_id": scheme_id,
            "version_id": new_version_id,
            "version_label": version_label,
            "version_status": target_status,
            "old_active_version_id": current_active["id"] if current_active else None,
            "rules_stored": rules_stored_count,
            "review_required": needs_review,
            "action_taken": "stored_for_review" if needs_review else "activated_new_version",
            "message": summary_log,
        }

    # Execute within explicit transaction block
    if conn is not None:
        return _execute_update(conn)
    else:
        with get_connection() as managed_conn:
            with managed_conn.transaction():
                return _execute_update(managed_conn)


# ==============================================================================
# 6. Query Functions: Current & Historical Rules
# ==============================================================================

def get_current_rules(
    scheme_key: str,
    conn: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """
    Answers: 'What are the currently active eligibility rules for this Karnataka government scheme?'
    Returns active version metadata, eligibility rules, and exclusion rules with grounded evidence.
    """
    scheme = get_scheme_by_key(scheme_key, conn=conn)
    if not scheme:
        return None

    active_ver = get_active_version(scheme["id"], conn=conn)
    if not active_ver:
        return {
            "scheme_id": scheme["id"],
            "scheme_key": scheme["slug"],
            "scheme_name": scheme["name"],
            "active_version": None,
            "eligibility_rules": [],
            "exclusion_rules": [],
        }

    rules_data = get_rules_for_version(active_ver["id"], conn=conn)
    return {
        "scheme_id": scheme["id"],
        "scheme_key": scheme["slug"],
        "scheme_name": scheme["name"],
        "active_version": active_ver,
        "eligibility_rules": rules_data["eligibility_rules"],
        "exclusion_rules": rules_data["exclusion_rules"],
    }


def get_historical_versions(
    scheme_key: str,
    conn: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    Answers: 'What were the historical versions of this scheme?'
    Returns all versions for a scheme ordered chronologically by created_at.
    """
    scheme = get_scheme_by_key(scheme_key, conn=conn)
    if not scheme:
        return []

    with get_db_cursor(conn) as cur:
        cur.execute(
            """
            SELECT id, scheme_id, version_label, document_hash, document_date, source_url, status, created_at
            FROM scheme_versions
            WHERE scheme_id = %s
            ORDER BY created_at ASC, id ASC;
            """,
            (scheme["id"],),
        )
        return cur.fetchall()


def get_rules_for_version(
    version_id: int,
    conn: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Answers: 'What were the eligibility rules in a specific historical version?'
    Retrieves all eligibility and exclusion rules plus evidence for any version.
    """
    with get_db_cursor(conn) as cur:
        # Fetch rules
        cur.execute(
            """
            SELECT id, scheme_version_id, rule, type, category, value,
                   semantic_confidence, review_required, review_reasons, created_at
            FROM eligibility_rules
            WHERE scheme_version_id = %s
            ORDER BY id ASC;
            """,
            (version_id,),
        )
        all_rules = cur.fetchall()

        # Fetch evidence for all rules
        cur.execute(
            """
            SELECT e.id, e.rule_id, e.page_number, e.section, e.evidence_text, e.source_url, e.ocr_confidence
            FROM rule_evidence e
            JOIN eligibility_rules r ON e.rule_id = r.id
            WHERE r.scheme_version_id = %s
            ORDER BY e.id ASC;
            """,
            (version_id,),
        )
        all_evidences = cur.fetchall()

    evidence_by_rule: Dict[int, List[Dict[str, Any]]] = {}
    for ev in all_evidences:
        rid = ev["rule_id"]
        if rid not in evidence_by_rule:
            evidence_by_rule[rid] = []
        evidence_by_rule[rid].append(ev)

    eligibility_rules = []
    exclusion_rules = []

    for r in all_rules:
        r_item = dict(r)
        r_item["evidence"] = evidence_by_rule.get(r["id"], [])
        if r["type"] == "exclusion":
            exclusion_rules.append(r_item)
        else:
            eligibility_rules.append(r_item)

    return {
        "version_id": version_id,
        "eligibility_rules": eligibility_rules,
        "exclusion_rules": exclusion_rules,
    }
