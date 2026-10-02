"""
Form Detection module.
Detects application forms and input fields (Kannada & English)
to distinguish them from policy guideline text.
"""

import re
from typing import Dict, Any, List, Optional

from app.config import setup_logger

logger = setup_logger("form_detector")

# Standard Kannada and English form field label patterns
FORM_LABEL_PATTERNS = [
    # Applicant details
    (r"(?:ಹೆಸರು|ಅರ್ಜಿದಾರರ\s*ಹೆಸರು|name\s*of\s*the\s*applicant|applicant\s*name)\s*[:\.\_\-]*", "Applicant Name"),
    (r"(?:ತಂದೆ|ಗಂಡ|ಪತಿ|ತಾಯಿ)ಯ?\s*ಹೆಸರು|father['\s]*s?\s*name|husband['\s]*s?\s*name", "Father / Husband Name"),
    (r"(?:ವಯಸ್ಸು|ಹುಟ್ಟಿದ\s*ದಿನಾಂಕ|age|date\s*of\s*birth|dob)\s*[:\.\_\-]*", "Age / DOB"),
    (r"(?:ಲಿಂಗ|ಪುರುಷ|ಮಹಿಳೆ|gender|sex)\s*[:\.\_\-]*", "Gender"),
    (r"(?:ವಿಳಾಸ|ವಾಸ್ತವ್ಯ\s*ವಿಳಾಸ|address|residential\s*address)\s*[:\.\_\-]*", "Address"),
    (r"(?:ಮೊಬೈಲ್‌?\s*ಸಂಖ್ಯೆ|ದೂರವಾಣಿ\s*ಸಂಖ್ಯೆ|mobile\s*no|phone\s*no)\s*[:\.\_\-]*", "Mobile Number"),
    (r"(?:ಆಧಾರ್\s*ಸಂಖ್ಯೆ|ಆಧಾರ್\s*ಕಾರ್ಡ್|aadhaar\s*no|aadhaar\s*number)\s*[:\.\_\-]*", "Aadhaar Number"),
    # Socio-economic & land details
    (r"(?:ಜಾತಿ|ವರ್ಗ|ಪ್ರವರ್ಗ|caste|category)\s*[:\.\_\-]*", "Caste / Category"),
    (r"(?:ವಾರ್ಷಿಕ\s*ಆದಾಯ|ಕುಟುಂಬದ\s*ಆದಾಯ|annual\s*income|family\s*income)\s*[:\.\_\-]*", "Annual Income"),
    (r"(?:ಪಡಿತರ\s*ಚೀಟಿ|ರೇಷನ್\s*ಕಾರ್ಡ್|ration\s*card\s*no)\s*[:\.\_\-]*", "Ration Card Number"),
    (r"(?:ಸರ್ವೆ\s*ಸಂಖ್ಯೆ|ಸರ್ವೇ\s*ನಂ|survey\s*no|land\s*extent|ಖಾತೆ\s*ಸಂಖ್ಯೆ)\s*[:\.\_\-]*", "Survey Number / Land Extent"),
    # Financial & banking
    (r"(?:ಬ್ಯಾಂಕ್\s*ಖಾತೆ\s*ಸಂಖ್ಯೆ|bank\s*account\s*no|a/c\s*no)\s*[:\.\_\-]*", "Bank Account Number"),
    (r"(?:ಬ್ಯಾಂಕ್\s*ಹೆಸರು|ಶಾಖೆ|bank\s*name|branch|ifsc\s*code)\s*[:\.\_\-]*", "Bank / Branch / IFSC"),
    # Signature and declaration
    (r"(?:ಅರ್ಜಿದಾರರ\s*ಸಹಿ|ಹೆಬ್ಬೆಟ್ಟಿನ\s*ಗುರುತು|signature\s*of\s*applicant|applicant\s*signature)\s*[:\.\_\-]*", "Applicant Signature"),
    (r"(?:ದಿನಾಂಕ|ಸ್ಥಳ|date|place)\s*[:\.\_\-]*", "Date / Place"),
]


def detect_form_fields(text: str, tables: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Scans text and table cells for form input fields.
    Returns:
    {
        "is_form": True/False,
        "fields_count": int,
        "fields": [{"label": "...", "raw_match": "...", "value": None}],
        "form_confidence": float (0-100)
    }
    """
    detected_fields = []
    seen_labels = set()

    # 1. Scan plain/OCR text for form field indicators
    for regex_pat, normalized_label in FORM_LABEL_PATTERNS:
        match = re.search(regex_pat, text, re.IGNORECASE)
        if match and normalized_label not in seen_labels:
            seen_labels.add(normalized_label)
            detected_fields.append({
                "label": normalized_label,
                "raw_match": match.group(0).strip(),
                "value": None,  # Keep value null as blank form fields are unfulfilled
            })

    # 2. Check table cells: If table has 2 columns where column 0 is a label and column 1 is blank/empty, it's a form table!
    blank_cell_count = 0
    if tables:
        for t in tables:
            for row in t.get("rows", []):
                cells = row.get("cells", [])
                if len(cells) >= 2:
                    col0_text = (cells[0].get("text") or "").strip()
                    col1_text = (cells[1].get("text") or "").strip()
                    # Check if col0 is a label and col1 is blank
                    for regex_pat, normalized_label in FORM_LABEL_PATTERNS:
                        if re.search(regex_pat, col0_text, re.IGNORECASE) and normalized_label not in seen_labels:
                            seen_labels.add(normalized_label)
                            detected_fields.append({
                                "label": normalized_label,
                                "raw_match": col0_text,
                                "value": col1_text if col1_text else None,
                            })
                    if not col1_text:
                        blank_cell_count += 1

    # Form classification logic:
    # If 3 or more typical form labels are found, or multiple blank form cells exist
    is_form = len(detected_fields) >= 3 or (len(detected_fields) >= 2 and blank_cell_count >= 3)
    confidence = min(100.0, len(detected_fields) * 20.0 + (15.0 if blank_cell_count >= 3 else 0.0))

    if is_form:
        logger.info(f"Form detected with {len(detected_fields)} field(s) (Confidence: {confidence}%)")

    return {
        "is_form": is_form,
        "fields_count": len(detected_fields),
        "fields": detected_fields,
        "form_confidence": round(confidence, 1),
    }
