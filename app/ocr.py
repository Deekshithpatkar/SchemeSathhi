"""
OCR Fallback module.
Performs spatial OCR with bounding boxes, confidence scores, and quality control.
Supports Kannada + English via Tesseract.
"""

import os
import shutil
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
import pymupdf
import pytesseract
from PIL import Image

from app.config import BASE_DIR, PROCESSED_DIR, STRUCTURED_DIR, setup_logger
from app.document_processor import clean_text
from app.image_preprocessor import (
    render_page_to_image,
    preprocess_image,
    to_cv2,
)

logger = setup_logger("ocr")

TESSERACT_CMD_CANDIDATES = [
    Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
    Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
]

LOCAL_TESSDATA_DIR = BASE_DIR / "data" / "tessdata"


def get_tesseract_command() -> Optional[str]:
    """Finds the tesseract.exe path on the system."""
    which_path = shutil.which("tesseract")
    if which_path:
        return which_path

    for candidate in TESSERACT_CMD_CANDIDATES:
        if candidate.exists():
            return str(candidate)

    return None


def setup_ocr() -> bool:
    """Configures pytesseract path and sets TESSDATA_PREFIX."""
    cmd = get_tesseract_command()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
        if LOCAL_TESSDATA_DIR.exists():
            os.environ["TESSDATA_PREFIX"] = str(LOCAL_TESSDATA_DIR.resolve())
        return True

    logger.warning("Tesseract OCR executable not found on system.")
    return False


# Auto-configure pytesseract path on module load
setup_ocr()


def extract_structured_ocr(
    image: Image.Image,
    languages: str = "kan+eng",
) -> Dict[str, Any]:
    """
    Runs Tesseract image_to_data to capture words, spatial bounding boxes,
    and confidence scores.
    """
    if not setup_ocr():
        raise RuntimeError("Tesseract OCR is not installed or configured.")

    data = pytesseract.image_to_data(image, lang=languages, output_type=pytesseract.Output.DICT)

    words = []
    confs = []
    blocks_dict: Dict[int, List[Dict[str, Any]]] = {}

    n_boxes = len(data.get("text", []))
    for i in range(n_boxes):
        text = data["text"][i].strip()
        conf = float(data["conf"][i])

        if not text or conf < 0:
            continue

        confs.append(conf)
        bbox = [data["left"][i], data["top"][i], data["width"][i], data["height"][i]]
        word_info = {
            "text": text,
            "bbox": bbox,
            "confidence": round(conf, 1),
            "block_num": data["block_num"][i],
            "line_num": data["line_num"][i],
        }
        words.append(word_info)

        block_num = data["block_num"][i]
        if block_num not in blocks_dict:
            blocks_dict[block_num] = []
        blocks_dict[block_num].append(word_info)

    avg_confidence = round(sum(confs) / len(confs), 1) if confs else 0.0
    low_conf_count = sum(1 for c in confs if c < 50.0)
    low_conf_ratio = round((low_conf_count / len(confs)) * 100, 1) if confs else 0.0

    # Build blocks
    blocks = []
    full_text_lines = []
    for block_num, block_words in sorted(blocks_dict.items()):
        block_text = " ".join(w["text"] for w in block_words)
        blocks.append({
            "block_number": block_num,
            "text": block_text,
            "word_count": len(block_words),
        })
        full_text_lines.append(block_text)

    full_text = "\n".join(full_text_lines)

    return {
        "text": full_text,
        "words": words,
        "blocks": blocks,
        "words_count": len(words),
        "avg_confidence": avg_confidence,
        "low_conf_percentage": low_conf_ratio,
    }


def ocr_image(
    image: Image.Image,
    languages: str = "kan+eng",
    auto_preprocess: bool = True,
) -> str:
    """
    Clean wrapper for plain text OCR (backward-compatible).
    """
    res = ocr_with_quality_control(image, languages=languages, auto_preprocess=auto_preprocess)
    return res["text"]


def ocr_with_quality_control(
    image: Image.Image,
    languages: str = "kan+eng",
    auto_preprocess: bool = True,
    max_attempts: int = 2,
) -> Dict[str, Any]:
    """
    OCR with Quality Control (Requirement 9):
    1. Runs OCR with initial preprocessing (Kannada unsharp).
    2. If average confidence is low (< 55%) or low confidence words > 35%,
       retries with alternative preprocessing (Standard CLAHE/Bilateral).
    3. Keeps the higher-confidence result and logs the chosen method.
    """
    if not auto_preprocess:
        res = extract_structured_ocr(image, languages=languages)
        res["method_used"] = "raw"
        return res

    # Attempt 1: Kannada-optimized sharpening
    prep_kan = preprocess_image(image, method="kannada")
    res1 = extract_structured_ocr(prep_kan, languages=languages)
    res1["method_used"] = "kannada_sharpen"

    # Check if quality check passes
    if res1["avg_confidence"] >= 55.0 and res1["low_conf_percentage"] <= 35.0:
        return res1

    # Attempt 2: Alternative standard thresholding
    logger.info(
        f"Initial OCR quality low (Conf: {res1['avg_confidence']}%, "
        f"Low-conf words: {res1['low_conf_percentage']}%). Retrying with alternative preprocessing..."
    )
    prep_std = preprocess_image(image, method="standard")
    res2 = extract_structured_ocr(prep_std, languages=languages)
    res2["method_used"] = "standard_clahe"

    # Select the result with better confidence
    if res2["avg_confidence"] > res1["avg_confidence"]:
        logger.info(f"Alternative preprocessing improved confidence to {res2['avg_confidence']}%. Keeping second result.")
        return res2

    return res1


def ocr_pdf_page(
    page: pymupdf.Page,
    languages: str = "kan+eng",
    dpi: int = 300,
) -> Dict[str, Any]:
    """
    Renders page at 300 DPI, runs OCR with quality control, and returns structured data.
    """
    image = render_page_to_image(page, dpi=dpi)
    res = ocr_with_quality_control(image, languages=languages)
    res["page_number"] = page.number + 1
    res["dpi"] = dpi
    return res


def process_with_ocr_fallback(
    file_path: Union[str, Path],
    languages: str = "kan+eng",
) -> Dict[str, Any]:
    """
    Backward-compatible entry point.
    Delegates to the new comprehensive document understanding pipeline in app.document_processor.
    """
    from app.document_processor import process_document_understanding
    return process_document_understanding(file_path, languages=languages)
