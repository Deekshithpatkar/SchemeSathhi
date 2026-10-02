"""
Document Processor module.
Extracts Unicode text from PDFs using PyMuPDF, cleans the text,
evaluates whether pages have usable text or are scanned images requiring OCR,
and stores processed text in files and PostgreSQL.
"""

import re
from pathlib import Path
from typing import Dict, Any, List, Union
import pymupdf
from app.config import PROCESSED_DIR, setup_logger
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

    # Replace non-breaking space with normal space
    text = raw_text.replace("\xa0", " ")

    # Remove non-printable control characters (except newline, tab, carriage return)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Normalize multiple blank lines to at most two newlines
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    # Strip leading and trailing whitespace
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


def extract_text_from_pdf(file_path: Union[str, Path]) -> Dict[str, Any]:
    """
    Opens a PDF using PyMuPDF and extracts text page-by-page.
    Detects whether each page contains usable Unicode text or is scanned.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    logger.info(f"Processing PDF: {path.name}")
    doc = pymupdf.open(str(path))
    total_pages = len(doc)

    pages_data: List[Dict[str, Any]] = []
    usable_pages = 0
    scanned_pages = 0
    full_text_chunks = []

    for page_idx in range(total_pages):
        page_num = page_idx + 1
        page = doc[page_idx]

        # Extract text directly using PyMuPDF
        raw_text = page.get_text()
        cleaned = clean_text(raw_text)

        usable = is_text_usable(cleaned)
        word_count = len(cleaned.split())
        char_count = len(cleaned)

        if usable:
            usable_pages += 1
            full_text_chunks.append(f"--- Page {page_num} ---\n{cleaned}")
        else:
            scanned_pages += 1

        pages_data.append({
            "page_number": page_num,
            "text": cleaned,
            "char_count": char_count,
            "word_count": word_count,
            "is_usable": usable,
            "needs_ocr": not usable,
        })

    doc.close()

    full_text = "\n\n".join(full_text_chunks)
    requires_ocr = scanned_pages > 0
    is_fully_usable = usable_pages == total_pages and total_pages > 0

    logger.info(
        f"PDF {path.name}: {total_pages} total pages | "
        f"{usable_pages} usable pages | {scanned_pages} scanned pages (Requires OCR: {requires_ocr})"
    )

    return {
        "file_name": path.name,
        "file_path": str(path),
        "total_pages": total_pages,
        "usable_pages_count": usable_pages,
        "scanned_pages_count": scanned_pages,
        "is_fully_usable": is_fully_usable,
        "requires_ocr": requires_ocr,
        "full_text": full_text,
        "pages": pages_data,
    }


def save_processed_text(file_path: Union[str, Path], text: str, output_dir: Path = PROCESSED_DIR) -> Path:
    """
    Saves extracted text to data/processed/<filename>.txt for inspection and downstream use.
    """
    path = Path(file_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{path.stem}.txt"

    with open(out_file, "w", encoding="utf-8") as f:
        f.write(text)

    logger.info(f"Saved processed text to {out_file.name}")
    return out_file


def update_version_extracted_text(version_id: int, text: str) -> bool:
    """
    Updates the extracted_text column in PostgreSQL for the given scheme_version.
    """
    sql = "UPDATE scheme_versions SET extracted_text = %s WHERE id = %s;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (text, version_id))
            updated = cur.rowcount > 0
        conn.commit()

    logger.info(f"Updated extracted text in PostgreSQL for scheme version ID {version_id}")
    return updated
