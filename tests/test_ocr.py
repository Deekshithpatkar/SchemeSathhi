"""
Test OCR Fallback (CP9).
Verifies Tesseract detection, image rendering, Kannada/English OCR execution,
and intelligent fallback triggering only when pages lack usable text.
"""

from pathlib import Path
import pymupdf
import pytest
from app.db import init_db
import os
from app.ocr import (
    setup_ocr,
    LOCAL_TESSDATA_DIR,
    render_page_to_image,
    ocr_image,
    process_with_ocr_fallback,
)


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database tables exist before testing."""
    init_db()


def test_setup_ocr():
    """Verify that Tesseract OCR is installed and detected on the system."""
    assert setup_ocr() is True, "Tesseract OCR should be detected on the system."
    assert "TESSDATA_PREFIX" in os.environ
    assert Path(os.environ["TESSDATA_PREFIX"]).exists()


def test_render_page_to_image(tmp_path: Path):
    """Verify that PyMuPDF page can be converted to a PIL Image."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 50), "Test Image Rendering")

    img = render_page_to_image(page, dpi=100)

    assert img is not None
    assert img.width > 0
    assert img.height > 0
    doc.close()


def test_ocr_image_extracts_text(tmp_path: Path):
    """Verify that ocr_image runs Tesseract and extracts readable text from an image."""
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=200)
    page.insert_text((50, 50), "Karnataka Scheme 2026", fontsize=20)

    img = render_page_to_image(page, dpi=150)
    text = ocr_image(img, languages="eng")

    assert "Karnataka" in text
    assert "2026" in text
    doc.close()


def test_process_with_ocr_fallback_text_pdf(tmp_path: Path):
    """Verify that a normal text-based PDF does NOT trigger unnecessary OCR."""
    pdf_path = tmp_path / "text_only.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    content = (
        "Government Order 2026 for Agriculture Support.\n"
        "All small and marginal farmers owning agricultural land in Karnataka are eligible for this program."
    )
    rect = pymupdf.Rect(50, 50, page.rect.width - 50, page.rect.height - 50)
    page.insert_textbox(rect, content)
    doc.save(str(pdf_path))
    doc.close()

    result = process_with_ocr_fallback(pdf_path)

    # Should not perform OCR since text was already extracted directly
    assert result["ocr_performed"] is False
    assert result["usable_pages_count"] == 1
    assert "Government Order 2026" in result["full_text"]


def test_process_with_ocr_fallback_scanned_pdf(tmp_path: Path):
    """
    Simulates a scanned document:
    Creates a page with rendered image content (no selectable text stream).
    Verifies that OCR fallback automatically detects and processes it!
    """
    # 1. Create an image containing text
    source_doc = pymupdf.open()
    source_page = source_doc.new_page(width=500, height=200)
    source_page.insert_text((50, 80), "Scanned Government Notification 2026", fontsize=18)
    pix = source_page.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")
    source_doc.close()

    # 2. Put only the image into a target PDF (zero text layer, pure image/scanned)
    scanned_pdf = tmp_path / "scanned_doc.pdf"
    target_doc = pymupdf.open()
    target_page = target_doc.new_page(width=500, height=200)
    target_page.insert_image(target_page.rect, stream=img_bytes)
    target_doc.save(str(scanned_pdf))
    target_doc.close()

    # 3. Process with OCR fallback
    result = process_with_ocr_fallback(scanned_pdf, languages="eng")

    assert result["ocr_performed"] is True
    assert result["ocr_pages_count"] == 1
    assert result["pages"][0]["is_ocr"] is True
    assert "Scanned Government Notification" in result["full_text"]
