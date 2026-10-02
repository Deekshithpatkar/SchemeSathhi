"""
Source Registry module.
Manages official Karnataka government websites registered in the database.
"""

from typing import List, Optional, Dict, Any
from psycopg.rows import dict_row
from app.db import get_connection
from app.config import setup_logger

logger = setup_logger("registry")


def add_source(
    source_name: str,
    official_url: str,
    department: Optional[str] = None,
    source_type: str = "scheme_page",
    active: bool = True,
) -> Dict[str, Any]:
    """
    Registers a new official government source or updates it if it already exists.
    Returns the created/updated source record.
    """
    sql = """
    INSERT INTO source_registry (department, source_name, official_url, source_type, active)
    VALUES (%s, %s, %s, %s, %s)
    ON CONFLICT (official_url)
    DO UPDATE SET
        department = EXCLUDED.department,
        source_name = EXCLUDED.source_name,
        source_type = EXCLUDED.source_type,
        active = EXCLUDED.active
    RETURNING id, department, source_name, official_url, source_type, active, last_checked, last_successful_check, created_at;
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                sql,
                (department, source_name, official_url, source_type, active),
            )
            record = cur.fetchone()
        conn.commit()

    logger.info(f"Registered source '{source_name}' (ID: {record['id']})")
    return record


def get_sources(active_only: bool = True) -> List[Dict[str, Any]]:
    """
    Returns a list of all registered sources.
    If active_only=True, returns only sources where active is True.
    """
    if active_only:
        sql = "SELECT * FROM source_registry WHERE active = TRUE ORDER BY id ASC;"
    else:
        sql = "SELECT * FROM source_registry ORDER BY id ASC;"

    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            sources = cur.fetchall()

    return sources


def get_source_by_id(source_id: int) -> Optional[Dict[str, Any]]:
    """
    Finds and returns a source by its ID.
    Returns None if not found.
    """
    sql = "SELECT * FROM source_registry WHERE id = %s;"
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (source_id,))
            return cur.fetchone()


def update_source_status(source_id: int, active: bool) -> bool:
    """
    Enables or disables a source by setting its active flag.
    Returns True if the source was updated, False if not found.
    """
    sql = "UPDATE source_registry SET active = %s WHERE id = %s;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (active, source_id))
            updated = cur.rowcount > 0
        conn.commit()

    logger.info(f"Updated source ID {source_id} active status to {active}")
    return updated


def record_source_check(source_id: int, success: bool) -> bool:
    """
    Updates the last_checked timestamp for a source.
    If success=True, also updates last_successful_check.
    """
    if success:
        sql = """
        UPDATE source_registry
        SET last_checked = CURRENT_TIMESTAMP,
            last_successful_check = CURRENT_TIMESTAMP
        WHERE id = %s;
        """
    else:
        sql = """
        UPDATE source_registry
        SET last_checked = CURRENT_TIMESTAMP
        WHERE id = %s;
        """

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (source_id,))
            updated = cur.rowcount > 0
        conn.commit()

    return updated


def delete_source(source_id: int) -> bool:
    """
    Deletes a source from the registry.
    Returns True if deleted, False if not found.
    """
    sql = "DELETE FROM source_registry WHERE id = %s;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (source_id,))
            deleted = cur.rowcount > 0
        conn.commit()

    logger.info(f"Deleted source ID {source_id}")
    return deleted
