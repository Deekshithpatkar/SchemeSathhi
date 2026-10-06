"""
Page Classification module.
Deterministically classifies each PDF page into:
- TEXT: Clean digital text pages
- SCANNED: Scanned image pages requiring OCR
- TABLE: Pages dominated by grid tables
- FORM: Pages containing application input fields
- MIXED: Pages containing combinations (e.g. text + table or scanned + text)
"""

from typing import Dict, Any, Optional
import pymupdf
from PIL import Image

from app.config import setup_logger
from app.document_processor import is_text_usable
from app.image_preprocessor import render_page_to_image, to_cv2
from app.table_extractor import detect_table_grid, find_cell_boxes
from app.form_detector import detect_form_fields

logger = setup_logger("document_classifier")


def classify_page(
    page: pymupdf.Page,
    image: Optional[Image.Image] = None,
    dpi: int = 200,
) -> Dict[str, Any]:
    """
    Deterministically evaluates a PDF page using PyMuPDF and computer vision signals.
    Returns page classification: 'TEXT', 'SCANNED', 'TABLE', 'FORM', or 'MIXED'.
    """
    raw_text = page.get_text().strip()
    text_usable = is_text_usable(raw_text)
    from app.text_reliability import assess_text_reliability
    reliability_assessment = assess_text_reliability(raw_text)
    if not reliability_assessment.reliable:
        text_usable = False
    images_count = len(page.get_images())
    text_blocks = page.get_text("blocks")

    # Render image for computer vision if not provided
    img = image or render_page_to_image(page, dpi=dpi)
    cv_img = to_cv2(img)

    # 1. Detect table lines & cell boxes
    table_mask, h_lines, v_lines = detect_table_grid(cv_img)
    cell_boxes = find_cell_boxes(table_mask)
    has_table = len(cell_boxes) >= 4

    # 2. Check for form input fields
    form_res = detect_form_fields(raw_text)
    is_form = form_res["is_form"]

    # 3. Decision Matrix
    primary_type = "UNKNOWN"
    tags = []

    if not text_usable:
        # Scanned page (no selectable text layer)
        tags.append("SCANNED")
        if is_form:
            primary_type = "FORM"
            tags.append("FORM")
        elif has_table:
            primary_type = "TABLE"
            tags.append("TABLE")
        else:
            primary_type = "SCANNED"
    else:
        # Digital text layer exists
        tags.append("TEXT")
        if has_table and len(text_blocks) > 5:
            primary_type = "MIXED"
            tags.append("TABLE")
        elif has_table:
            primary_type = "TABLE"
            tags.append("TABLE")
        elif is_form:
            primary_type = "FORM"
            tags.append("FORM")
        else:
            primary_type = "TEXT"

    logger.info(
        f"Page {page.number + 1} classified as '{primary_type}' "
        f"(Text usable: {text_usable}, Cells: {len(cell_boxes)}, Form: {is_form})"
    )

    return {
        "page_number": page.number + 1,
        "page_type": primary_type,
        "tags": tags,
        "text_usable": text_usable,
        "text_length": len(raw_text),
        "text_blocks_count": len(text_blocks),
        "images_count": images_count,
        "table_cells_count": len(cell_boxes),
        "is_form": is_form,
        "form_fields_count": form_res["fields_count"],
        "text_reliability": reliability_assessment.model_dump(),
    }
