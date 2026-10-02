"""
Test Source Registry (CP3).
Verifies registering, fetching, updating, and removing official sources.
"""

import pytest
from app.db import init_db
from app.registry import (
    add_source,
    get_sources,
    get_source_by_id,
    update_source_status,
    record_source_check,
    delete_source,
)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure tables exist before tests run."""
    init_db()


def test_add_and_get_source():
    """Verify adding a source and retrieving it."""
    test_url = "https://test.karnataka.gov.in/schemes"
    record = add_source(
        source_name="Test Department Schemes",
        official_url=test_url,
        department="Test Department",
        source_type="scheme_page",
    )

    assert record["id"] is not None
    assert record["source_name"] == "Test Department Schemes"
    assert record["official_url"] == test_url
    assert record["active"] is True

    # Retrieve by ID
    fetched = get_source_by_id(record["id"])
    assert fetched is not None
    assert fetched["official_url"] == test_url

    # Cleanup
    delete_source(record["id"])


def test_add_source_duplicate_url_updates_record():
    """Verify that adding an existing URL updates instead of crashing with duplicate key error."""
    test_url = "https://duplicate-test.karnataka.gov.in"
    record1 = add_source(
        source_name="Original Name",
        official_url=test_url,
        department="Dept A",
    )

    # Re-register with updated name and department
    record2 = add_source(
        source_name="Updated Name",
        official_url=test_url,
        department="Dept B",
    )

    assert record1["id"] == record2["id"]
    assert record2["source_name"] == "Updated Name"
    assert record2["department"] == "Dept B"

    # Cleanup
    delete_source(record1["id"])


def test_update_status_and_filter():
    """Verify toggling active status and filtering active_only."""
    test_url = "https://status-test.karnataka.gov.in"
    record = add_source(
        source_name="Status Test",
        official_url=test_url,
        active=True,
    )

    # Deactivate
    update_source_status(record["id"], active=False)
    updated = get_source_by_id(record["id"])
    assert updated["active"] is False

    # Check active_only filter
    active_sources = get_sources(active_only=True)
    assert not any(s["id"] == record["id"] for s in active_sources)

    # Cleanup
    delete_source(record["id"])


def test_record_source_check():
    """Verify recording last_checked and last_successful_check."""
    test_url = "https://check-test.karnataka.gov.in"
    record = add_source(
        source_name="Check Test",
        official_url=test_url,
    )

    # Record successful check
    record_source_check(record["id"], success=True)
    checked = get_source_by_id(record["id"])
    assert checked["last_checked"] is not None
    assert checked["last_successful_check"] is not None

    # Cleanup
    delete_source(record["id"])
