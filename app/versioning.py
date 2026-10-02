"""
Version Detection and Historical Version Management module.
Detects whether a scheme document is unchanged, new, or an updated version.
Preserves all historical versions by archiving previous versions and adding new ones.
"""

import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from psycopg.rows import dict_row

from app.db import get_connection
from app.config import setup_logger

logger = setup_logger("versioning")


def make_slug(text: str) -> str:
    """
    Converts a scheme name into a clean, URL-friendly slug.
    Example: 'PM KISAN Scheme' -> 'pm-kisan-scheme'
    """
    cleaned = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    slug = re.sub(r"[\s_-]+", "-", cleaned)
    return slug or "unnamed-scheme"


def parse_date_to_iso(date_str: Optional[str]) -> Optional[str]:
    """
    Safely converts date strings like '07-08-2021', '07/08/2021', or '2026-01-29'
    into standard ISO format 'YYYY-MM-DD' for PostgreSQL.
    """
    if not date_str:
        return None

    clean_str = date_str.strip().replace("/", "-")
    formats = [
        "%d-%m-%Y",  # 07-08-2021
        "%Y-%m-%d",  # 2021-08-07
        "%d-%m-%y",  # 07-08-21
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(clean_str, fmt)
            return parsed.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def extract_version_label(title: str, url: str, published_date: Optional[str] = None) -> str:
    """
    Extracts a human-readable version label from signals:
    1. Financial year pattern (e.g. '2024-25', '2026-27')
    2. Explicit 4-digit year (e.g. '2026', '2025')
    3. Version number (e.g. 'v2.0', 'v1.1')
    4. Year from published date (e.g. '2021')
    5. Fallback to 'Initial'
    """
    combined_text = f"{title} {url}"

    # 1. Financial year like 2024-25 or 2024-2025
    fy_match = re.search(r"\b(20\d{2}[-_/]\d{2,4})\b", combined_text)
    if fy_match:
        return fy_match.group(1).replace("_", "-").replace("/", "-")

    # 2. Version notation like v1.0, v2, Rev-1
    v_match = re.search(r"\b(v(?:er)?\.?\s*\d+(?:\.\d+)?)\b", combined_text, re.IGNORECASE)
    if v_match:
        return v_match.group(1).replace(" ", "")

    # 3. Explicit 4-digit year in title or URL (2015 to 2035)
    year_match = re.search(r"\b(20[1-3]\d)\b", combined_text)
    if year_match:
        return year_match.group(1)

    # 4. Fallback to year from published_date
    if published_date:
        iso_date = parse_date_to_iso(published_date)
        if iso_date:
            return iso_date.split("-")[0]

    return "Initial"


def get_or_create_scheme(
    name: str,
    department: Optional[str] = None,
    slug: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Finds a scheme by slug or creates a new master scheme record in PostgreSQL.
    """
    scheme_slug = slug or make_slug(name)
    select_sql = "SELECT * FROM schemes WHERE slug = %s;"
    insert_sql = """
    INSERT INTO schemes (slug, name, department, state)
    VALUES (%s, %s, %s, 'Karnataka')
    RETURNING id, slug, name, department, state, created_at;
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(select_sql, (scheme_slug,))
            row = cur.fetchone()
            if row:
                return row

            cur.execute(insert_sql, (scheme_slug, name, department))
            record = cur.fetchone()
        conn.commit()

    logger.info(f"Created new master scheme: {name} (Slug: {scheme_slug}, ID: {record['id']})")
    return record


def get_active_version(scheme_id: int) -> Optional[Dict[str, Any]]:
    """Gets the currently ACTIVE version for a scheme."""
    sql = """
    SELECT sv.*, d.file_hash, d.source_url
    FROM scheme_versions sv
    LEFT JOIN documents d ON sv.document_id = d.id
    WHERE sv.scheme_id = %s AND sv.status = 'ACTIVE'
    ORDER BY sv.id DESC LIMIT 1;
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (scheme_id,))
            return cur.fetchone()


def get_scheme_versions(scheme_id: int) -> List[Dict[str, Any]]:
    """Returns all versions for a scheme (both ACTIVE and ARCHIVED)."""
    sql = """
    SELECT sv.*, d.file_hash, d.source_url
    FROM scheme_versions sv
    LEFT JOIN documents d ON sv.document_id = d.id
    WHERE sv.scheme_id = %s
    ORDER BY sv.id ASC;
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (scheme_id,))
            return cur.fetchall()


def archive_active_versions(scheme_id: int) -> int:
    """Marks any currently ACTIVE versions as ARCHIVED for a scheme."""
    sql = "UPDATE scheme_versions SET status = 'ARCHIVED' WHERE scheme_id = %s AND status = 'ACTIVE';"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (scheme_id,))
            count = cur.rowcount
        conn.commit()
    return count


def create_scheme_version(
    scheme_id: int,
    version_label: str,
    document_id: int,
    published_date: Optional[str] = None,
    status: str = "ACTIVE",
) -> Dict[str, Any]:
    """
    Inserts a new version record into PostgreSQL.
    Previous versions are preserved.
    """
    iso_date = parse_date_to_iso(published_date)
    sql = """
    INSERT INTO scheme_versions (scheme_id, version_label, document_id, published_date, status)
    VALUES (%s, %s, %s, %s, %s)
    RETURNING id, scheme_id, version_label, document_id, published_date, status, created_at;
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (scheme_id, version_label, document_id, iso_date, status))
            record = cur.fetchone()
        conn.commit()

    logger.info(f"Created scheme version {version_label} (ID: {record['id']}) with status '{status}'")
    return record


def detect_and_register_version(
    scheme_name: str,
    document_id: int,
    file_hash: str,
    document_title: str,
    document_url: str,
    published_date: Optional[str] = None,
    department: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Core Step 7 function:
    1. Finds or creates the scheme in the database.
    2. Checks the active version:
       - If same hash already exists -> Status: UNCHANGED
       - If no versions exist yet -> Status: NEW_SCHEME (creates first version)
       - If a version exists but hash or label is different -> Status: NEW_VERSION (archives old, creates new)
    3. Guarantees old versions are never overwritten or deleted.
    """
    scheme = get_or_create_scheme(name=scheme_name, department=department)
    scheme_id = scheme["id"]

    active_ver = get_active_version(scheme_id)
    version_label = extract_version_label(document_title, document_url, published_date)

    # Case 1: Active version has the exact same content hash
    if active_ver and active_ver.get("file_hash") == file_hash:
        logger.info(f"Scheme '{scheme_name}' is unchanged. Active version ID {active_ver['id']} matches file hash.")
        return {
            "status": "UNCHANGED",
            "scheme_id": scheme_id,
            "scheme_name": scheme_name,
            "active_version_id": active_ver["id"],
            "version_label": active_ver["version_label"],
            "message": "Document content matches the current active version. No update needed.",
        }

    # Case 2: New scheme (no versions exist yet)
    if not active_ver:
        new_ver = create_scheme_version(
            scheme_id=scheme_id,
            version_label=version_label,
            document_id=document_id,
            published_date=published_date,
            status="ACTIVE",
        )
        return {
            "status": "NEW_SCHEME",
            "scheme_id": scheme_id,
            "scheme_name": scheme_name,
            "new_version_id": new_ver["id"],
            "version_label": version_label,
            "message": f"First version '{version_label}' registered for new scheme.",
        }

    # Case 3: New version detected! Archive previous active version and add new version
    old_version_id = active_ver["id"]
    old_version_label = active_ver["version_label"]

    # Archive previous version(s)
    archive_active_versions(scheme_id)

    # Add new active version
    new_ver = create_scheme_version(
        scheme_id=scheme_id,
        version_label=version_label,
        document_id=document_id,
        published_date=published_date,
        status="ACTIVE",
    )

    logger.info(
        f"Version update for '{scheme_name}': Archived version {old_version_label} (ID: {old_version_id}), "
        f"activated new version {version_label} (ID: {new_ver['id']})"
    )

    return {
        "status": "NEW_VERSION",
        "scheme_id": scheme_id,
        "scheme_name": scheme_name,
        "old_version_id": old_version_id,
        "old_version_label": old_version_label,
        "new_version_id": new_ver["id"],
        "version_label": version_label,
        "message": f"Updated from '{old_version_label}' to '{version_label}'. Previous version preserved as ARCHIVED.",
    }
