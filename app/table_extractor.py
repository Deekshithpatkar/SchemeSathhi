"""
Table Detection and Structured Extraction module.
Uses OpenCV morphological line detection to identify table grids,
reconstruct rows and columns, and perform cell-level OCR to preserve table structure.
"""

from typing import List, Dict, Any, Tuple, Optional
import cv2
import numpy as np
from PIL import Image
import pytesseract
from psycopg.rows import dict_row

from app.config import setup_logger
from app.image_preprocessor import to_cv2, to_pil
from app.ocr import setup_ocr

logger = setup_logger("table_extractor")
setup_ocr()


def detect_table_grid(cv_img: np.ndarray, min_line_ratio: float = 30.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Detects horizontal and vertical lines of table grids using OpenCV morphology.
    Returns (table_mask, horizontal_lines, vertical_lines).
    """
    gray = cv_img if len(cv_img.shape) == 2 else cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    # Invert binary: lines and text become white (255), background becomes black (0)
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)

    height, width = gray.shape[:2]

    # Horizontal line kernel (e.g. width / 30)
    h_size = max(20, int(width / min_line_ratio))
    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (h_size, 1))
    h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel)

    # Vertical line kernel (e.g. height / 30)
    v_size = max(20, int(height / min_line_ratio))
    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, v_size))
    v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel)

    # Combined table grid mask
    table_mask = cv2.add(h_lines, v_lines)
    return table_mask, h_lines, v_lines


def find_cell_boxes(table_mask: np.ndarray, min_area: int = 400) -> List[Tuple[int, int, int, int]]:
    """
    Finds rectangular cell bounding boxes inside a detected table mask.
    Returns list of (x, y, w, h) sorted from top-to-bottom, left-to-right.
    """
    contours, _ = cv2.findContours(table_mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    height, width = table_mask.shape[:2]

    cell_boxes = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h

        # Filter out tiny noise and the full-page outer boundary
        if area < min_area:
            continue
        if w > width * 0.98 and h > height * 0.98:
            continue
        if w < 25 or h < 15:
            continue

        cell_boxes.append((x, y, w, h))

    return cell_boxes


def group_boxes_into_rows(
    boxes: List[Tuple[int, int, int, int]],
    y_tolerance: int = 15,
) -> List[List[Tuple[int, int, int, int]]]:
    """
    Groups bounding boxes into horizontal table rows based on their y coordinate.
    Sorts rows top-to-bottom and cells within each row left-to-right.
    """
    if not boxes:
        return []

    # Sort primarily by y, then by x
    sorted_boxes = sorted(boxes, key=lambda b: (b[1], b[0]))

    rows: List[List[Tuple[int, int, int, int]]] = []
    current_row: List[Tuple[int, int, int, int]] = []
    current_y = -1

    for box in sorted_boxes:
        x, y, w, h = box
        if current_y == -1 or abs(y - current_y) <= y_tolerance:
            current_row.append(box)
            if current_y == -1:
                current_y = y
        else:
            # Sort previous row by x coordinate
            current_row.sort(key=lambda b: b[0])
            rows.append(current_row)
            current_row = [box]
            current_y = y

    if current_row:
        current_row.sort(key=lambda b: b[0])
        rows.append(current_row)

    return rows


def ocr_cell(
    cv_img: np.ndarray,
    bbox: Tuple[int, int, int, int],
    languages: str = "kan+eng",
) -> Tuple[Optional[str], float]:
    """
    Crops a single table cell from the image and runs OCR.
    Returns (cleaned_text, average_confidence).
    """
    x, y, w, h = bbox
    # Add 2px margin inside cell to avoid reading table border lines
    pad = 3
    x0 = max(0, x + pad)
    y0 = max(0, y + pad)
    x1 = min(cv_img.shape[1], x + w - pad)
    y1 = min(cv_img.shape[0], y + h - pad)

    if x1 <= x0 or y1 <= y0:
        return None, 0.0

    crop = cv_img[y0:y1, x0:x1]
    pil_crop = to_pil(crop)

    # Use image_to_data for word-level confidence and text
    data = pytesseract.image_to_data(pil_crop, lang=languages, output_type=pytesseract.Output.DICT)

    words = []
    confs = []

    for i, word in enumerate(data.get("text", [])):
        word_clean = word.strip()
        if word_clean:
            words.append(word_clean)
            conf = float(data["conf"][i])
            if conf > 0:
                confs.append(conf)

    text = " ".join(words).strip() if words else None
    avg_conf = sum(confs) / len(confs) if confs else 0.0

    return text, round(avg_conf, 1)


def detect_and_extract_tables(
    image: Image.Image,
    page_number: int = 1,
    languages: str = "kan+eng",
    min_cells: int = 4,
) -> List[Dict[str, Any]]:
    """
    Main table extraction function:
    1. Detects table lines via OpenCV.
    2. Identifies and groups cell rectangles into rows.
    3. Crops each cell and runs OCR, retaining coordinates and confidence.
    4. Reconstructs structured table representation.
    """
    cv_img = to_cv2(image)
    table_mask, h_lines, v_lines = detect_table_grid(cv_img)

    cell_boxes = find_cell_boxes(table_mask)

    # Require at least min_cells (e.g. 2x2 grid) to declare a table
    if len(cell_boxes) < min_cells:
        return []

    grouped_rows = group_boxes_into_rows(cell_boxes)
    if len(grouped_rows) < 2:
        return []

    logger.info(f"Page {page_number}: Detected table with {len(grouped_rows)} rows and {len(cell_boxes)} cells")

    structured_rows = []
    for r_idx, row_boxes in enumerate(grouped_rows):
        cells_data = []
        for c_idx, box in enumerate(row_boxes):
            cell_text, conf = ocr_cell(cv_img, box, languages=languages)
            cells_data.append({
                "row": r_idx,
                "column": c_idx,
                "bbox": [box[0], box[1], box[2], box[3]],  # [x, y, w, h]
                "text": cell_text,
                "confidence": conf,
            })
        structured_rows.append({
            "row_index": r_idx,
            "cells": cells_data,
        })

    # Overall table bounding box
    min_x = min(b[0] for b in cell_boxes)
    min_y = min(b[1] for b in cell_boxes)
    max_x = max(b[0] + b[2] for b in cell_boxes)
    max_y = max(b[1] + b[3] for b in cell_boxes)

    table_data = {
        "type": "table",
        "page": page_number,
        "bbox": [min_x, min_y, max_x - min_x, max_y - min_y],
        "rows_count": len(structured_rows),
        "cells_count": len(cell_boxes),
        "rows": structured_rows,
    }

    return [table_data]
