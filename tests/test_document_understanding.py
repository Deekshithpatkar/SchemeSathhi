"""
Test Document Understanding Pipeline (CP9 Advanced).
Verifies:
1. Normal digital-text PDF (PyMuPDF blocks with coordinates, no OCR).
2. Scanned Kannada PDF (Tesseract with Kannada OCR).
3. Mixed PDF (Text + Scanned).
4. Table page (OpenCV grid detection, row/col structure, cell bboxes).
5. Form page (Field label detection, null values for blank lines).
6. Quality control & structured JSON output.
"""

from pathlib import Path
import json
import pymupdf
import pytest
from app.db import init_db
from app.document_processor import process_document_understanding
from app.document_classifier import classify_page
from app.form_detector import detect_form_fields
from app.table_extractor import detect_and_extract_tables
from app.image_preprocessor import render_page_to_image


@pytest.fixture(autouse=True)
def setup_database():
    """Ensure database tables exist before testing."""
    init_db()


def test_scenario_1_normal_digital_text_pdf(tmp_path: Path):
    """Scenario 1: Digital-text PDF should extract text blocks with coords and skip OCR."""
    pdf_path = tmp_path / "digital_text.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    content = (
        "Government of Karnataka - Agriculture Department.\n"
        "Guidelines for Scheme Implementation 2026.\n"
        "All small and marginal farmers owning agricultural land in Karnataka are eligible."
    )
    rect = pymupdf.Rect(50, 50, page.rect.width - 50, page.rect.height - 50)
    page.insert_textbox(rect, content)
    doc.save(str(pdf_path))
    doc.close()

    result = process_document_understanding(pdf_path)

    assert result["ocr_performed"] is False
    assert result["usable_pages_count"] == 1
    assert result["pages"][0]["page_type"] == "TEXT"
    assert result["pages"][0]["extraction_method"] == "direct_pymupdf"
    assert len(result["pages"][0]["blocks"]) > 0
    # Check that spatial bbox exists
    assert len(result["pages"][0]["blocks"][0]["bbox"]) == 4

    # Check structured JSON was generated
    assert Path(result["structured_json_path"]).exists()


def test_scenario_2_scanned_kannada_pdf(tmp_path: Path):
    """Scenario 2: Scanned Kannada PDF page triggers OCR with confidence & words."""
    raw_candidates = list(Path("data/raw").glob("*PM-KISAN*.pdf"))
    if not raw_candidates:
        pytest.skip("PM-KISAN PDF not found in data/raw")

    # Extract 1 page from the real scanned PM-KISAN PDF
    src_doc = pymupdf.open(str(raw_candidates[0]))
    single_page_pdf = tmp_path / "pmkisan_p1.pdf"
    out_doc = pymupdf.open()
    out_doc.insert_pdf(src_doc, from_page=0, to_page=0)
    out_doc.save(str(single_page_pdf))
    out_doc.close()
    src_doc.close()

    result = process_document_understanding(single_page_pdf, languages="kan+eng")

    assert result["ocr_performed"] is True
    assert result["pages"][0]["extraction_method"] == "tesseract_ocr"
    assert result["pages"][0]["avg_confidence"] > 0
    assert len(result["pages"][0]["words"]) > 0
    assert len(result["full_text"]) > 50


def test_scenario_3_table_page(tmp_path: Path):
    """Scenario 3: Table page detects grid, rows, cols, and cell bounding boxes."""
    # Create an image containing a grid table with horizontal & vertical lines
    img_doc = pymupdf.open()
    page = img_doc.new_page(width=600, height=300)

    # Draw table borders and inner grid lines
    # Outer rectangle
    page.draw_rect(pymupdf.Rect(50, 50, 550, 250), color=(0, 0, 0), width=2)
    # Horizontal line (header divider)
    page.draw_line(pymupdf.Point(50, 120), pymupdf.Point(550, 120), color=(0, 0, 0), width=2)
    # Vertical line (column divider)
    page.draw_line(pymupdf.Point(300, 50), pymupdf.Point(300, 250), color=(0, 0, 0), width=2)

    # Put cell texts
    page.insert_text((70, 90), "Scheme Name", fontsize=14)
    page.insert_text((320, 90), "Subsidy Amount", fontsize=14)
    page.insert_text((70, 180), "Krishi Bhagya", fontsize=14)
    page.insert_text((320, 180), "Rs 50,000", fontsize=14)

    img = render_page_to_image(page, dpi=150)
    img_doc.close()

    tables = detect_and_extract_tables(img, page_number=1, languages="eng", min_cells=2)

    assert len(tables) == 1
    table = tables[0]
    assert table["type"] == "table"
    assert table["rows_count"] >= 2
    # Verify cells have row, column, bbox, and confidence
    first_cell = table["rows"][0]["cells"][0]
    assert "row" in first_cell
    assert "column" in first_cell
    assert len(first_cell["bbox"]) == 4
    assert "confidence" in first_cell


def test_scenario_4_form_page():
    """Scenario 4: Form detection identifies application fields with null values."""
    sample_form_text = """
    ಕರ್ನಾಟಕ ಸರ್ಕಾರ - ಕೃಷಿ ಇಲಾಖೆ
    ಅರ್ಜಿ ನಮೂನೆ (Application Form)
    1. ಅರ್ಜಿದಾರರ ಹೆಸರು : ........................................
    2. ತಂದೆಯ ಹೆಸರು : ........................................
    3. ವಯಸ್ಸು : ....................
    4. ವಾಸ್ತವ್ಯ ವಿಳಾಸ : ........................................
    5. ಆಧಾರ್ ಸಂಖ್ಯೆ : ....................
    6. ಅರ್ಜಿದಾರರ ಸಹಿ :
    """
    form_res = detect_form_fields(sample_form_text)

    assert form_res["is_form"] is True
    assert form_res["fields_count"] >= 4

    labels = [f["label"] for f in form_res["fields"]]
    assert "Applicant Name" in labels
    assert "Age / DOB" in labels
    assert "Address" in labels
    assert "Aadhaar Number" in labels

    # Values for blank input fields must be null (not invented)
    for field in form_res["fields"]:
        assert field["value"] is None


def test_scenario_5_mixed_pdf(tmp_path: Path):
    """Scenario 5: Mixed PDF (Page 1 text, Page 2 scanned) processes both appropriately."""
    pdf_path = tmp_path / "mixed_document.pdf"
    doc = pymupdf.open()

    # Page 1: Digital text
    p1 = doc.new_page()
    p1.insert_textbox(
        pymupdf.Rect(50, 50, 450, 300),
        "Official Notification from Agriculture Department.\nDetailed instructions follow below in Annexure.",
    )

    # Page 2: Scanned image
    p2 = doc.new_page(width=500, height=200)
    p2.insert_text((50, 80), "Annexure Form Scanned", fontsize=16)
    pix = p2.get_pixmap(dpi=150)
    img_bytes = pix.tobytes("png")

    target_doc = pymupdf.open()
    # Add page 1 text
    target_p1 = target_doc.new_page()
    target_p1.insert_textbox(
        pymupdf.Rect(50, 50, 450, 300),
        "Official Notification from Agriculture Department.\nDetailed instructions follow below in Annexure.",
    )
    # Add page 2 scanned image
    target_p2 = target_doc.new_page(width=500, height=200)
    target_p2.insert_image(target_p2.rect, stream=img_bytes)

    target_doc.save(str(pdf_path))
    target_doc.close()
    doc.close()

    result = process_document_understanding(pdf_path, languages="eng")

    assert result["total_pages"] == 2
    assert result["usable_pages_count"] == 1
    assert result["scanned_pages_count"] == 1

    # Page 1 should be direct_pymupdf
    assert result["pages"][0]["extraction_method"] == "direct_pymupdf"
    # Page 2 should be tesseract_ocr
    assert result["pages"][1]["extraction_method"] == "tesseract_ocr"

    # Both pages in structured JSON
    structured_json = json.loads(Path(result["structured_json_path"]).read_text(encoding="utf-8"))
    assert len(structured_json["pages"]) == 2
