"""
Test Document Processor (CP8).
Verifies PyMuPDF text extraction, text cleaning, usability validation, and scanned page detection.
"""

from pathlib import Path
import pymupdf
import pytest
from app.db import init_db
from app.document_processor import (
    clean_text,
    is_text_usable,
    extract_text_from_pdf,
    save_processed_text,
)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database tables exist before testing."""
    init_db()


def test_clean_text():
    """Verify cleaning whitespace, control characters, and multiple blank lines."""
    raw = "Karnataka\xa0Government\n\n\n\nSchemes\x00\x05Details"
    cleaned = clean_text(raw)
    assert "\xa0" not in cleaned
    assert "\x00" not in cleaned
    assert "Karnataka Government\n\nSchemesDetails" == cleaned


def test_is_text_usable():
    """Verify text usability checks for minimum words and corrupted text."""
    # Usable English text (more than 15 words)
    valid_eng = (
        "The Government of Karnataka hereby issues the following guidelines and eligibility "
        "criteria for all eligible farmers applying under the scheme."
    )
    assert is_text_usable(valid_eng) is True

    # Usable Kannada text
    valid_kannada = (
        "ಕರ್ನಾಟಕ ಸರ್ಕಾರ ಕೃಷಿ ಇಲಾಖೆ ವತಿಯಿಂದ ರೈತರಿಗೆ ವಿವಿಧ ಯೋಜನೆಗಳ ಮಾರ್ಗಸೂಚಿಗಳು "
        "ಮತ್ತು ಸವಲತ್ತುಗಳನ್ನು ಒದಗಿಸಲು ಈ ನಿಯಮಗಳನ್ನು ರೂಪಿಸಲಾಗಿದೆ ಪ್ರತಿಯೊಬ್ಬ ಅರ್ಹ ರೈತರು ಅರ್ಜಿ ಸಲ್ಲಿಸಬಹುದು."
    )
    assert is_text_usable(valid_kannada) is True

    # Too short / empty / scanned page text (fewer than 15 words)
    assert is_text_usable("") is False
    assert is_text_usable("Page 1") is False

    # Broken text with excessive \ufffd replacement characters
    corrupted = "\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd\ufffd Some text here"
    assert is_text_usable(corrupted) is False


def test_extract_text_from_pdf_text_based(tmp_path: Path):
    """Verify extracting Unicode text from a normal text-based PDF."""
    pdf_path = tmp_path / "sample_text.pdf"
    doc = pymupdf.open()
    page = doc.new_page()

    # Insert readable scheme text using insert_textbox so it wraps properly
    content = (
        "Karnataka Government Order: Agriculture Support Scheme 2026.\n"
        "Eligibility: All small and marginal farmers owning agricultural land in Karnataka.\n"
        "Financial assistance of Rupees Ten Thousand per hectare will be provided to all eligible beneficiaries."
    )
    rect = pymupdf.Rect(50, 50, page.rect.width - 50, page.rect.height - 50)
    page.insert_textbox(rect, content)
    doc.save(str(pdf_path))
    doc.close()

    res = extract_text_from_pdf(pdf_path)

    assert res["total_pages"] == 1
    assert res["usable_pages_count"] == 1
    assert res["scanned_pages_count"] == 0
    assert res["is_fully_usable"] is True
    assert res["requires_ocr"] is False
    assert "Agriculture Support Scheme 2026" in res["full_text"]
    assert res["pages"][0]["needs_ocr"] is False


def test_extract_text_from_pdf_scanned_detection(tmp_path: Path):
    """Verify that an empty/scanned page is correctly flagged as requiring OCR."""
    pdf_path = tmp_path / "scanned_sample.pdf"
    doc = pymupdf.open()
    # Create empty page without text
    doc.new_page()
    doc.save(str(pdf_path))
    doc.close()

    res = extract_text_from_pdf(pdf_path)

    assert res["total_pages"] == 1
    assert res["usable_pages_count"] == 0
    assert res["scanned_pages_count"] == 1
    assert res["is_fully_usable"] is False
    assert res["requires_ocr"] is True
    assert res["pages"][0]["needs_ocr"] is True


def test_save_processed_text(tmp_path: Path):
    """Verify saving extracted text to a .txt file."""
    mock_pdf = tmp_path / "scheme_doc.pdf"
    mock_pdf.touch()

    text_to_save = "Sample extracted scheme text."
    out_file = save_processed_text(mock_pdf, text_to_save, output_dir=tmp_path)

    assert out_file.exists()
    assert out_file.name == "scheme_doc.txt"
    assert out_file.read_text(encoding="utf-8") == text_to_save
