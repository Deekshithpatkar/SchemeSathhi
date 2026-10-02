"""
Test Document Downloader (CP6).
Verifies SHA-256 calculation, filename safety, PDF validation, download, and DB registration.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest
from app.db import init_db
from app.downloader import (
    calculate_sha256,
    get_safe_filename,
    is_valid_pdf_content,
    download_file,
    register_document,
    get_existing_document_by_hash,
    download_and_register,
)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database tables exist before testing."""
    init_db()


def test_calculate_sha256():
    """Verify deterministic SHA-256 hash output."""
    sample_bytes = b"%PDF-1.4 Hello Karnataka Scheme"
    h1 = calculate_sha256(sample_bytes)
    h2 = calculate_sha256(sample_bytes)

    assert len(h1) == 64
    assert h1 == h2
    assert calculate_sha256(b"Different") != h1


def test_get_safe_filename():
    """Verify safe filenames without invalid Windows path characters."""
    url = "https://example.com/schemes/Krishi:Bhagya*Rules 2026?.pdf"
    fake_hash = "abcdef1234567890abcdef1234567890"

    safe_name = get_safe_filename(url, fake_hash)

    assert safe_name.startswith("abcdef12_")
    assert safe_name.endswith(".pdf")
    for bad_char in [":", "*", "?", "<", ">", "|", " "]:
        assert bad_char not in safe_name


def test_is_valid_pdf_content():
    """Verify detection of PDF magic bytes."""
    valid_pdf = b"%PDF-1.7\nSome pdf binary stream..."
    invalid_html = b"<!DOCTYPE html><html><body>Error</body></html>"
    empty = b""

    assert is_valid_pdf_content(valid_pdf) is True
    assert is_valid_pdf_content(invalid_html) is False
    assert is_valid_pdf_content(empty) is False


def test_download_file_with_mock(tmp_path: Path):
    """Verify download_file saves content to output_dir and calculates hash."""
    fake_content = b"%PDF-1.4 Mock Government Order Content"
    mock_resp = MagicMock()
    mock_resp.content = fake_content
    mock_resp.raise_for_status = MagicMock()

    with patch("requests.get", return_value=mock_resp):
        res = download_file("https://example.com/docs/order.pdf", output_dir=tmp_path)

        assert res is not None
        assert res["file_size"] == len(fake_content)
        assert res["is_pdf"] is True
        assert Path(res["file_path"]).exists()
        assert Path(res["file_path"]).read_bytes() == fake_content


import uuid
from app.downloader import delete_document


def test_download_and_register_handles_new_and_duplicate(tmp_path: Path):
    """Verify that a new file registers as 'new', and the same file re-downloaded registers as 'unchanged'."""
    unique_run_id = uuid.uuid4().hex
    fake_pdf = f"%PDF-1.4 Duplicate Detection Test Content {unique_run_id}".encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.content = fake_pdf
    mock_resp.raise_for_status = MagicMock()

    doc_info = {
        "document_url": f"https://example.com/docs/test_{unique_run_id}.pdf",
        "title": "Test Duplicate Scheme",
        "document_type": "guideline",
        "source_page_url": "https://example.com/page",
    }

    doc_id = None
    try:
        with patch("requests.get", return_value=mock_resp):
            # 1. First download -> Should be registered as "new"
            res1 = download_and_register(doc_info, output_dir=tmp_path)
            assert res1["success"] is True
            assert res1["status"] == "new"
            doc_id = res1["document_id"]
            assert doc_id is not None

            # 2. Second download with identical content -> Should detect hash match and skip inserting duplicate
            res2 = download_and_register(doc_info, output_dir=tmp_path)
            assert res2["success"] is True
            assert res2["status"] == "unchanged"
            assert res2["document_id"] == doc_id
    finally:
        if doc_id:
            delete_document(doc_id)
