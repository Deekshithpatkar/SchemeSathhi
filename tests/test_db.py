"""
Test PostgreSQL Foundation (CP2).
Verifies connection and checks that tables can be created and queried.
"""

import pytest
from app.db import test_connection as check_connection, init_db, get_connection


def test_postgres_connection():
    """Verify that we can connect to the configured PostgreSQL database."""
    connected = check_connection()
    assert connected is True, "PostgreSQL connection failed. Check DATABASE_URL in .env."


def test_init_db_creates_tables():
    """Verify that init_db creates all 6 expected tables."""
    init_db()

    expected_tables = {
        "source_registry",
        "schemes",
        "documents",
        "scheme_versions",
        "eligibility_rules",
        "update_logs",
    }

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public';
            """)
            existing_tables = {row[0] for row in cur.fetchall()}

    # All expected tables must exist in public schema
    assert expected_tables.issubset(existing_tables), (
        f"Missing tables: {expected_tables - existing_tables}"
    )
