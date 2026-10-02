"""
Document Processor and Document Understanding module.
Combines PyMuPDF digital text extraction with OpenCV table detection,
form detection, Tesseract OCR with spatial coordinates, and structured JSON output.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Union, Optional
import pymupdf

from app.config import PROCESSED_DIR, STRUCTURED_DIR, setup_logger
from app.db import get_connection

logger = setup_logger("document_processor")


def clean_text(raw_text: str) -> str:
    """
    Cleans up raw extracted text:
    - Normalizes non-breaking spaces and irregular whitespace
    - Removes unprintable control characters
    - Collapses excessive blank lines
    """
    if not raw_text:
        return ""

    text = raw_text.replace("\xa0", " ")
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    return text.strip()


def is_text_usable(text: str, min_words: int = 10) -> bool:
    """
    Determines whether extracted text from a page is usable.
    Returns False if:
    - Text is empty or has fewer than min_words (scanned page)
    - Text consists mostly of replacement/garbage characters (\ufffd)
    """
    if not text:
        return False

    cleaned = clean_text(text)
    words = cleaned.split()

    if len(words) < min_words:
        return False

    # Check for broken font encoding / excessive replacement characters
    replacement_count = cleaned.count("\ufffd")
    if replacement_count > 10 and (replacement_count / len(cleaned)) > 0.1:
        return False

    return True


def save_processed_text(file_path: Union[str, Path], text: str, output_dir: Path = PROCESSED_DIR) -> Path:
    """Saves human-readable extracted text to data/processed/<filename>.txt."""
    path = Path(file_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{path.stem}.txt"

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(text)

    logger.info(f"Saved processed text to {out_file.name}")
    return out_file


def save_structured_json(file_path: Union[str, Path], data: Dict[str, Any], output_dir: Path = STRUCTURED_DIR) -> Path:
    """Saves primary structured JSON document representation to data/structured/<filename>.json."""
    path = Path(file_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{path.stem}.json"

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved structured JSON representation to {out_file.name}")
    return out_file


def update_version_extracted_text(version_id: int, text: str) -> bool:
    """Updates the extracted_text column in PostgreSQL for the given scheme_version."""
    sql = "UPDATE scheme_versions SET extracted_text = %s WHERE id = %s;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (text, version_id))
            updated = cur.rowcount > 0
        conn.commit()

    logger.info(f"Updated extracted text in PostgreSQL for scheme version ID {version_id}")
    return updated


def process_document_understanding(
    file_path: Union[str, Path],
    languages: str = "kan+eng",
    dpi: int = 300,
    source_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Comprehensive Document Understanding Pipeline:
    1. Classifies each page (TEXT, SCANNED, TABLE, FORM, MIXED).
    2. Digital Text: Uses PyMuPDF blocks with coordinates (no unnecessary OCR).
    3. Scanned/Table Pages:
       - Detects tables with OpenCV line detection and extracts cell rows/columns.
       - Detects form fields.
       - Performs spatial OCR with word coordinates and confidence scores.
    4. Quality control & validation.
    5. Saves structured JSON and text fallback.
    """
    from app.document_classifier import classify_page
    from app.image_preprocessor import render_page_to_image
    from app.table_extractor import detect_and_extract_tables
    from app.form_detector import detect_form_fields
    from app.ocr import ocr_with_quality_control

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    logger.info(f"Starting Document Understanding pipeline on: {path.name}")
    doc = pymupdf.open(str(path))
    total_pages = len(doc)

    pages_output: List[Dict[str, Any]] = []
    text_fallback_chunks: List[str] = []

    usable_pages = 0
    scanned_pages = 0
    total_tables = 0
    ocr_performed = False

    for page_idx in range(total_pages):
        page_num = page_idx + 1
        page = doc[page_idx]

        # Step 1: Deterministic Page Classification
        classification = classify_page(page, dpi=200)
        page_type = classification["page_type"]

        page_data: Dict[str, Any] = {
            "page_number": page_num,
            "page_type": page_type,
            "tags": classification["tags"],
            "extraction_method": "direct_pymupdf",
            "dpi": dpi,
            "blocks": [],
            "tables": [],
            "forms": None,
            "full_text": "",
            "avg_confidence": 100.0,
        }

        # Step 2: Handle Digital Text vs Scanned/Table
        if page_type == "TEXT":
            # Extract digital text blocks with coordinates
            raw_blocks = page.get_text("blocks")
            blocks = []
            page_text_lines = []

            for b in raw_blocks:
                b_text = clean_text(b[4])
                if b_text:
                    blocks.append({
                        "bbox": [round(b[0], 1), round(b[1], 1), round(b[2] - b[0], 1), round(b[3] - b[1], 1)],
                        "text": b_text,
                        "type": "text",
                        "confidence": 100.0,
                    })
                    page_text_lines.append(b_text)

            usable_pages += 1
            full_page_text = "\n".join(page_text_lines)
            page_data["blocks"] = blocks
            page_data["full_text"] = full_page_text
            text_fallback_chunks.append(f"--- Page {page_num} (Text) ---\n{full_page_text}")

        else:
            # Page is SCANNED, TABLE, FORM, or MIXED -> Needs high-resolution image rendering
            scanned_pages += 1
            ocr_performed = True
            page_data["extraction_method"] = "tesseract_ocr"
            page_data["is_ocr"] = True

            # Render 300 DPI image
            img = render_page_to_image(page, dpi=dpi)

            # Step 2a: Table Detection & Cell Extraction
            tables = detect_and_extract_tables(img, page_number=page_num, languages=languages)
            page_data["tables"] = tables
            total_tables += len(tables)

            # Step 2b: Form Field Detection
            form_info = detect_form_fields(text="", tables=tables)

            # Step 2c: OCR with Word Coordinates & Quality Control
            ocr_res = ocr_with_quality_control(img, languages=languages)
            page_data["blocks"] = ocr_res["blocks"]
            page_data["words"] = ocr_res["words"]
            page_data["avg_confidence"] = ocr_res["avg_confidence"]
            page_data["low_conf_percentage"] = ocr_res["low_conf_percentage"]
            page_data["ocr_preprocessing"] = ocr_res.get("method_used", "standard")

            # Re-check form fields against OCR text
            if not form_info["is_form"]:
                form_info = detect_form_fields(text=ocr_res["text"], tables=tables)

            if form_info["is_form"]:
                page_data["forms"] = form_info

            # Assemble full page text
            page_text_elements = []
            if tables:
                for t in tables:
                    page_text_elements.append(f"[Table: {t['rows_count']} rows x {t['cells_count']} cells]")
                    for row in t["rows"]:
                        row_vals = [c.get("text") or "-" for c in row["cells"]]
                        page_text_elements.append(" | ".join(row_vals))

            page_text_elements.append(ocr_res["text"])
            full_page_text = "\n".join(page_text_elements).strip()
            page_data["full_text"] = full_page_text

            label_tag = "Table/OCR" if tables else "OCR"
            text_fallback_chunks.append(f"--- Page {page_num} ({label_tag}) ---\n{full_page_text}")

        pages_output.append(page_data)

    doc.close()

    # Step 3: Document-level Summary & Structured Representation
    consolidated_text = "\n\n".join(text_fallback_chunks)

    document_structured = {
        "document": {
            "filename": path.name,
            "filepath": str(path.resolve()),
            "source_url": source_url,
            "total_pages": total_pages,
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "pipeline_version": "2.0_document_understanding",
        },
        "summary": {
            "total_pages": total_pages,
            "usable_pages_count": usable_pages,
            "scanned_pages_count": scanned_pages,
            "ocr_pages_count": scanned_pages,
            "total_tables_detected": total_tables,
            "requires_ocr": scanned_pages > 0,
            "ocr_performed": ocr_performed,
        },
        "pages": pages_output,
    }

    # Step 4: Save outputs
    json_path = save_structured_json(path, document_structured)
    txt_path = save_processed_text(path, consolidated_text)

    # Return dictionary with full backward-compatibility for existing callers
    return {
        "file_name": path.name,
        "file_path": str(path),
        "total_pages": total_pages,
        "usable_pages_count": usable_pages,
        "scanned_pages_count": scanned_pages,
        "ocr_pages_count": scanned_pages,
        "is_fully_usable": scanned_pages == 0,
        "requires_ocr": scanned_pages > 0,
        "ocr_performed": ocr_performed,
        "full_text": consolidated_text,
        "processed_file_path": str(txt_path),
        "structured_json_path": str(json_path),
        "tables_detected_count": total_tables,
        "structured_data": document_structured,
        "pages": pages_output,
    }


def extract_text_from_pdf(file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Lightweight PyMuPDF text extractor (kept for fast inspection / testing).
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    doc = pymupdf.open(str(path))
    total_pages = len(doc)
    pages_data = []
    usable_pages = 0
    scanned_pages = 0
    full_text_chunks = []

    for page_idx in range(total_pages):
        page_num = page_idx + 1
        page = doc[page_idx]

        raw_text = page.get_text()
        cleaned = clean_text(raw_text)

        usable = is_text_usable(cleaned)
        if usable:
            usable_pages += 1
            full_text_chunks.append(f"--- Page {page_num} ---\n{cleaned}")
        else:
            scanned_pages += 1

        pages_data.append({
            "page_number": page_num,
            "text": cleaned,
            "char_count": len(cleaned),
            "word_count": len(cleaned.split()),
            "is_usable": usable,
            "needs_ocr": not usable,
        })

    doc.close()

    full_text = "\n\n".join(full_text_chunks)
    return {
        "file_name": path.name,
        "file_path": str(path),
        "total_pages": total_pages,
        "usable_pages_count": usable_pages,
        "scanned_pages_count": scanned_pages,
        "is_fully_usable": usable_pages == total_pages and total_pages > 0,
        "requires_ocr": scanned_pages > 0,
        "full_text": full_text,
        "pages": pages_data,
    }
