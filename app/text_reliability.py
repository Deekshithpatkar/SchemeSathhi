"""
Document Text Reliability Detector (Checkpoint 16.1).
Evaluates whether digitally extracted PDF text is reliable, or if it represents
mojibake, non-standard legacy font encoding (Nudi/Baraha), or degraded ASCII noise.
"""

import re
from typing import Dict, Any, List
from pydantic import BaseModel, Field

from app.config import setup_logger

logger = setup_logger("text_reliability")


class TextReliabilityResult(BaseModel):
    """Structured assessment of page or document digital text quality."""
    reliable: bool = Field(description="True if digital text is trustworthy; False if OCR should be run")
    score: float = Field(ge=0.0, le=1.0, description="Quality confidence score from 0.0 to 1.0")
    reasons: List[str] = Field(default_factory=list, description="Specific triggers or anomalies found")
    detected_encoding_issue: bool = Field(description="True if non-standard font encoding / mojibake detected")
    recommended_action: str = Field(description="'USE_DIGITAL_TEXT', 'RUN_OCR', or 'REVIEW'")


COMMON_ENGLISH_WORDS = {
    "the", "of", "and", "to", "in", "is", "for", "government", "karnataka",
    "department", "state", "order", "scheme", "directorate", "agriculture",
    "under", "proceedings", "date", "dated", "secretary", "commissioner",
    "subject", "read", "preamble", "bengaluru", "finance", "development",
    "central", "share", "allocation", "annual", "total", "general", "component",
    "plan", "guidelines", "rules", "district", "meeting", "officer", "public"
}


def assess_text_reliability(
    text: str,
    min_words: int = 10,
    min_kannada_char_count: int = 25,
) -> TextReliabilityResult:
    """
    Evaluates digital text reliability across multiple complementary linguistic signals:
    1. Genuine Kannada Unicode check (U+0C80 to U+0CFF).
    2. Genuine English vocabulary check (common government dictionary words).
    3. Mojibake signals (excessive ASCII symbol/punctuation density, unusual repeated patterns).
    4. Non-standard font encoding detection (high token count with zero dictionary match).
    """
    cleaned = (text or "").strip()
    if not cleaned:
        return TextReliabilityResult(
            reliable=False,
            score=0.0,
            reasons=["Digital text is empty (scanned or image page)"],
            detected_encoding_issue=False,
            recommended_action="RUN_OCR",
        )

    words = cleaned.split()
    total_chars = len(cleaned)

    if len(words) < min_words:
        return TextReliabilityResult(
            reliable=False,
            score=0.1,
            reasons=[f"Insufficient word count ({len(words)} < {min_words})"],
            detected_encoding_issue=False,
            recommended_action="RUN_OCR",
        )

    # 1. Check for genuine Kannada Unicode characters
    kannada_chars = sum(1 for c in cleaned if 0x0C80 <= ord(c) <= 0x0CFF)
    kannada_ratio = kannada_chars / total_chars

    if kannada_chars >= min_kannada_char_count and kannada_ratio >= 0.15:
        # High confidence genuine Kannada digital text
        return TextReliabilityResult(
            reliable=True,
            score=0.98,
            reasons=[],
            detected_encoding_issue=False,
            recommended_action="USE_DIGITAL_TEXT",
        )

    # 2. English text analysis
    latin_tokens = [re.sub(r"[^a-zA-Z]", "", w).lower() for w in words if len(w) >= 2]
    eng_matches = sum(1 for w in latin_tokens if w in COMMON_ENGLISH_WORDS)

    # Check ASCII symbol & punctuation density (Baraha/Nudi encoding heavily uses symbols like ~, `, ^, _, {, }, ;, :)
    unusual_symbol_chars = sum(1 for c in cleaned if c in "~`^_{}|\\;:$%@*<>[]+=")
    symbol_ratio = unusual_symbol_chars / total_chars

    reasons = []
    encoding_issue = False

    # Signal A: Excessive symbol density
    if symbol_ratio > 0.035:
        reasons.append(f"Excessive non-standard ASCII symbol density ({symbol_ratio * 100:.1f}%)")
        encoding_issue = True

    # Signal B: Repeated symbol patterns typical of legacy font ligatures (e.g. ';;;', '.._', '~rjijj', ';;i2Jve')
    if re.search(r"[;~`_]{2,}|[a-zA-Z]{1,3}[;~`^]{1,3}[a-zA-Z]{1,3}", cleaned):
        reasons.append("Unusual repeated legacy font ligature character patterns found")
        encoding_issue = True

    # Signal C: Latin alphabet presence but almost zero English dictionary match
    if len(latin_tokens) >= 15 and eng_matches < 3:
        reasons.append(
            f"Latin text lacks natural language vocabulary (only {eng_matches} standard words in {len(latin_tokens)} tokens)"
        )
        encoding_issue = True

    # Calculate final quality score
    if encoding_issue:
        score = max(0.0, round(0.40 - min(0.40, symbol_ratio * 8), 2))
        reliable = False
        action = "RUN_OCR"
    elif eng_matches >= 3 or (len(words) >= 15 and (sum(c.isalnum() for c in cleaned) / total_chars) > 0.70):
        # Reliable English or alphanumeric government document text
        score = 0.95
        reliable = True
        action = "USE_DIGITAL_TEXT"
    else:
        score = 0.50
        reliable = False
        action = "REVIEW"
        reasons.append("Ambiguous text composition requiring verification")

    return TextReliabilityResult(
        reliable=reliable,
        score=score,
        reasons=reasons,
        detected_encoding_issue=encoding_issue,
        recommended_action=action,
    )
