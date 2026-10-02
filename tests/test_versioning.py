"""
Test Version Detection and Historical Preservation (CP7).
Verifies slug generation, date parsing, version label extraction, and preserving historical versions.
"""

import uuid
import pytest
from app.db import init_db, get_connection
from app.downloader import register_document, delete_document
from app.versioning import (
    make_slug,
    parse_date_to_iso,
    extract_version_label,
    get_or_create_scheme,
    get_scheme_versions,
    detect_and_register_version,
)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database tables exist before testing."""
    init_db()


def test_make_slug():
    """Verify clean URL-friendly slugs."""
    assert make_slug("Krishi Bhagya Scheme 2026") == "krishi-bhagya-scheme-2026"
    assert make_slug("PM-KISAN: Karnataka GO!") == "pm-kisan-karnataka-go"


def test_parse_date_to_iso():
    """Verify standard date formatting for PostgreSQL."""
    assert parse_date_to_iso("07-08-2021") == "2021-08-07"
    assert parse_date_to_iso("15/05/2023") == "2023-05-15"
    assert parse_date_to_iso("2026-01-29") == "2026-01-29"
    assert parse_date_to_iso("Invalid") is None


def test_extract_version_label():
    """Verify extracting version labels from titles, dates, or URLs."""
    # Financial year
    assert extract_version_label("Guidelines for 2024-25", "http://x.com/g.pdf") == "2024-25"

    # Version string
    assert extract_version_label("Scheme Rules v2.1", "http://x.com/r.pdf") == "v2.1"

    # Year
    assert extract_version_label("Krishi Scheme 2026", "http://x.com/k.pdf") == "2026"

    # From published date fallback
    assert extract_version_label("Order", "http://x.com/o.pdf", published_date="07-08-2021") == "2021"


def test_historical_version_preservation():
    """
    Core Checkpoint 7 test:
    Simulates discovering 2025 guidelines, then an updated 2026 guideline.
    Verifies that:
    1. 2025 guideline is registered as ACTIVE.
    2. Resubmitting identical hash returns UNCHANGED.
    3. 2026 guideline is added as ACTIVE, and 2025 is marked ARCHIVED (not deleted!).
    """
    unique_name = f"Test Scheme {uuid.uuid4().hex[:6]}"
    doc_id1 = None
    doc_id2 = None

    try:
        # Create mock Document 1 (2025 version)
        hash1 = uuid.uuid4().hex
        d1 = register_document(
            source_url=f"http://example.com/docs/{hash1}.pdf",
            file_hash=hash1,
            file_path=f"data/raw/{hash1}.pdf",
            title=f"{unique_name} 2025 Guidelines",
        )
        doc_id1 = d1["id"]

        # Step 1: Register 2025 version
        res1 = detect_and_register_version(
            scheme_name=unique_name,
            document_id=doc_id1,
            file_hash=hash1,
            document_title=f"{unique_name} 2025 Guidelines",
            document_url="http://example.com/docs/2025.pdf",
            published_date="01-01-2025",
        )
        assert res1["status"] == "NEW_SCHEME"
        scheme_id = res1["scheme_id"]

        # Step 2: Test identical hash -> Should return UNCHANGED
        res_same = detect_and_register_version(
            scheme_name=unique_name,
            document_id=doc_id1,
            file_hash=hash1,
            document_title=f"{unique_name} 2025 Guidelines",
            document_url="http://example.com/docs/2025.pdf",
            published_date="01-01-2025",
        )
        assert res_same["status"] == "UNCHANGED"

        # Create mock Document 2 (2026 updated version)
        hash2 = uuid.uuid4().hex
        d2 = register_document(
            source_url=f"http://example.com/docs/{hash2}.pdf",
            file_hash=hash2,
            file_path=f"data/raw/{hash2}.pdf",
            title=f"{unique_name} 2026 Guidelines",
        )
        doc_id2 = d2["id"]

        # Step 3: Register 2026 version -> Should detect NEW_VERSION
        res2 = detect_and_register_version(
            scheme_name=unique_name,
            document_id=doc_id2,
            file_hash=hash2,
            document_title=f"{unique_name} 2026 Guidelines",
            document_url="http://example.com/docs/2026.pdf",
            published_date="01-01-2026",
        )
        assert res2["status"] == "NEW_VERSION"
        assert res2["old_version_label"] == "2025"
        assert res2["version_label"] == "2026"

        # Step 4: Verify that BOTH versions exist in PostgreSQL!
        versions = get_scheme_versions(scheme_id)
        assert len(versions) == 2, "Both historical and new versions must be preserved!"

        v2025 = next(v for v in versions if v["version_label"] == "2025")
        v2026 = next(v for v in versions if v["version_label"] == "2026")

        assert v2025["status"] == "ARCHIVED", "Old version must be ARCHIVED"
        assert v2026["status"] == "ACTIVE", "New version must be ACTIVE"

    finally:
        # Cleanup test documents and scheme
        if doc_id1:
            delete_document(doc_id1)
        if doc_id2:
            delete_document(doc_id2)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM schemes WHERE name = %s;", (unique_name,))
            conn.commit()
