"""
Checkpoint 11: Document Comparison Module.
Implements a reliable TWO-LEVEL document comparison pipeline:
- Level 1: Deterministic Python comparison (SHA-256 hashes, metadata, page counts, exact text diffs, OCR noise detection)
- Level 2: Semantic document comparison (LLM classification of text differences and eligibility impact)

Strictly focused on candidate qualification and disqualification rules.
Administrative instructions, submission procedures, and document status statements
are explicitly separated and never misreported as eligibility changes.
"""

import json
import re
import difflib
import hashlib
from pathlib import Path
from typing import Dict, Any, Union, Optional, List, Tuple
from datetime import datetime, timezone

import pymupdf  # PyMuPDF

from app.config import COMPARISONS_DIR, setup_logger, LLM_MODEL
from app.comparison_schemas import (
    DocumentComparison,
    PageComparison,
    TextChange,
    MetadataChange,
    SemanticChangeItem,
    ComparisonMetadata,
)
from app.llm_client import LLMClient

logger = setup_logger("comparison")

# Candidate eligibility indicators (Kannada and English)
MULTI_WORD_ATTRIBUTES = [
    "annual income", "government servant", "government employee", "psu employee",
    "institutional landholder", "income tax payee", "small farmer", "marginal farmer",
    "cultivable land", "dry land", "wet land", "general category", "family income",
    "ಸರ್ಕಾರಿ ನೌಕರ", "ಸಣ್ಣ ರೈತ", "ಅತಿ ಸಣ್ಣ ರೈತ", "ಕರ್ನಾಟಕದ ನಿವಾಸಿ", "ಹಿಂದುಳಿದ ವರ್ಗ",
    "ಪರಿಶಿಷ್ಟ ಜಾತಿ", "ಪರಿಶಿಷ್ಟ ಪಂಗಡ"
]

SINGLE_WORD_ATTRIBUTES = {
    "income", "salary", "tax", "taxpayer", "age", "land", "landholding",
    "hectare", "acre", "farmer", "cultivator", "resident", "residency",
    "domicile", "caste", "pension", "disqualified", "excluded", "exclusion",
    "eligible", "eligibility", "qualifies", "qualification",
    "ರೈತ", "ಕೃಷಿಕ", "ಹಿಡುವಳಿ", "ಹಿಡುವಳಿದಾರ", "ಭೂಮಿ", "ಜಮೀನು", "ಹೆಕ್ಟೇರ್", "ಎಕರೆ",
    "ಗುಂಟೆ", "ಖುಷ್ಕಿ", "ತರಿ", "ಬಾಗಾಯ್ತು", "ಆದಾಯ", "ಆದಾಯತೆರಿಗೆ", "ತೆರಿಗೆ", "ರೂಪಾಯಿ",
    "ವಯಸ್ಸು", "ವರ್ಷ", "ಪರಿಶಿಷ್ಟ", "ನಿವಾಸಿ", "ಸಾಂಸ್ಥಿಕ", "ಪಿಂಚಣಿ", "ಅನರ್ಹ", "ಅರ್ಹತೆ"
}

KANNADA_SUBSTRINGS = [
    "ರೈತ", "ಕೃಷಿಕ", "ಭೂಮಿ", "ಜಮೀನು", "ಹೆಕ್ಟೇರ್", "ಎಕರೆ", "ಆದಾಯ", "ತೆರಿಗೆ",
    "ವಯಸ್ಸು", "ಪರಿಶಿಷ್ಟ", "ನಿವಾಸಿ", "ಸರ್ಕಾರಿ ನೌಕರ", "ಅನರ್ಹ", "ಅರ್ಹತೆ"
]

# Non-eligibility / Administrative / Document Status indicators
ADMIN_AND_STATUS_PATTERNS = [
    "submitted to", "applications shall be submitted", "submitted through", "office of",
    "taluk office", "assistant director", "forwarded to", "dispatch", "preservation",
    "guard file", "spare copies", "internal memo", "karyalaya", "coordinator",
    "no change in the notification", "amended notification", "amendment issued",
    "order remains in force", "notification status", "published in gazette",
    "ಬದಲಾವಣೆ ಇರುವುದಿಲ್ಲ", "ಉಳಿದಂತೆ ಸದರಿ", "ಅಧಿಸೂಚನೆ", "ತಿದ್ದುಪಡಿ", "ಕಛೇರಿಗೆ", "ಕಚೇರಿಗೆ",
    "ಕಳುಹಿಸಲಾಗುವುದು", "ರವಾನಿಸಲಾಗಿದೆ", "ಸಂರಕ್ಷಿಸಲು", "ರಕ್ಷಾ ಕಡತ"
]


def contains_candidate_attribute(text: str) -> bool:
    """Checks whether the text explicitly contains candidate qualification criteria."""
    text_lower = text.lower()
    if any(mw in text_lower for mw in MULTI_WORD_ATTRIBUTES):
        return True

    tokens = set(re.findall(r"\b\w+\b", text_lower))
    if tokens.intersection(SINGLE_WORD_ATTRIBUTES):
        return True

    if any(ks in text_lower for ks in KANNADA_SUBSTRINGS):
        return True

    return False


def calculate_sha256(content: bytes) -> str:
    """Calculates SHA-256 hash of byte content."""
    return hashlib.sha256(content).hexdigest()


def calculate_file_sha256(file_path: Union[str, Path]) -> Optional[str]:
    """Calculates SHA-256 hash of a file on disk."""
    p = Path(file_path)
    if not p.exists() or not p.is_file():
        return None
    with open(p, "rb") as f:
        return calculate_sha256(f.read())


def load_document_comparison_data(doc_input: Union[str, Path, Dict[str, Any]]) -> Dict[str, Any]:
    """
    Normalizes any input (PDF path, Step 9 structured JSON path, or dictionary)
    into a standardized document dictionary containing:
    - filename: str
    - sha256: Optional[str]
    - metadata: Dict[str, Any]
    - pages: List[Dict[str, Any]] with page_number, text, page_type
    """
    if isinstance(doc_input, (str, Path)):
        p = Path(doc_input)
        if not p.exists():
            raise FileNotFoundError(f"Document input not found: {p}")

        if p.suffix.lower() == ".json":
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            doc_meta = data.get("document", {})
            filename = doc_meta.get("filename", p.name)
            raw_pdf_path = doc_meta.get("filepath")
            file_hash = None
            if raw_pdf_path and Path(raw_pdf_path).exists():
                file_hash = calculate_file_sha256(raw_pdf_path)

            pages = []
            for pg in data.get("pages", []):
                p_num = pg.get("page_number", len(pages) + 1)
                p_text = pg.get("full_text", "")
                if not p_text and "blocks" in pg:
                    p_text = "\n".join(b.get("text", "") for b in pg["blocks"] if b.get("text"))
                pages.append({
                    "page_number": p_num,
                    "text": p_text or "",
                    "page_type": pg.get("page_type", "UNKNOWN"),
                })

            return {
                "filename": filename,
                "sha256": file_hash or doc_meta.get("sha256"),
                "metadata": {
                    "total_pages": len(pages),
                    "document_date": data.get("document_date"),
                    "version_information": data.get("version_information"),
                    "scheme_name": data.get("scheme_name"),
                },
                "pages": pages,
            }

        elif p.suffix.lower() == ".pdf":
            file_hash = calculate_file_sha256(p)
            doc = pymupdf.open(str(p))
            pages = []
            for idx, page in enumerate(doc, 1):
                pages.append({
                    "page_number": idx,
                    "text": page.get_text() or "",
                    "page_type": "TEXT" if page.get_text().strip() else "SCANNED",
                })
            doc.close()
            return {
                "filename": p.name,
                "sha256": file_hash,
                "metadata": {"total_pages": len(pages)},
                "pages": pages,
            }
        else:
            raise ValueError(f"Unsupported file format for comparison: {p.suffix}")

    elif isinstance(doc_input, dict):
        # In-memory dictionary
        doc_meta = doc_input.get("document", {})
        filename = doc_meta.get("filename", doc_input.get("filename", "in_memory_doc"))
        file_hash = doc_meta.get("sha256", doc_input.get("sha256"))

        raw_pages = doc_input.get("pages", [])
        pages = []
        for idx, pg in enumerate(raw_pages, 1):
            p_num = pg.get("page_number", idx)
            p_text = pg.get("text", pg.get("full_text", ""))
            if not p_text and "blocks" in pg:
                p_text = "\n".join(b.get("text", "") for b in pg["blocks"] if b.get("text"))
            pages.append({
                "page_number": p_num,
                "text": p_text or "",
                "page_type": pg.get("page_type", "TEXT"),
            })

        metadata = doc_input.get("metadata", {})
        if not metadata:
            metadata = {
                "total_pages": len(pages),
                "document_date": doc_input.get("document_date"),
                "version_information": doc_input.get("version_information"),
                "scheme_name": doc_input.get("scheme_name"),
            }

        return {
            "filename": filename,
            "sha256": file_hash,
            "metadata": metadata,
            "pages": pages,
        }

    else:
        raise TypeError("doc_input must be a file path or a dictionary")


def detect_ocr_noise(old_text: str, new_text: str) -> Tuple[bool, float]:
    """
    Evaluates whether the difference between old and new text represents OCR scanning noise
    (minor punctuation, character swapping, whitespace variance) rather than a substantive change.
    Returns (is_ocr_noise, similarity_ratio).
    """
    norm_old = " ".join(old_text.split())
    norm_new = " ".join(new_text.split())

    if norm_old == norm_new:
        return True, 1.0

    ratio = difflib.SequenceMatcher(None, norm_old, norm_new).ratio()

    # If similarity is lower than 0.85, it is not merely OCR noise
    if ratio < 0.85:
        return False, ratio

    # Examine differing tokens
    matcher = difflib.SequenceMatcher(None, norm_old.split(), norm_new.split())
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "delete", "insert"):
            old_chunk = " ".join(norm_old.split()[i1:i2])
            new_chunk = " ".join(norm_new.split()[j1:j2])
            diff_text = f"{old_chunk} {new_chunk}"

            # If any number/digit changed (e.g. 2,50,000 -> 3,00,000 or 18 -> 21), NOT OCR noise!
            if any(ch.isdigit() for ch in diff_text):
                return False, ratio

            # If candidate qualification attribute keywords changed, NOT OCR noise!
            if contains_candidate_attribute(diff_text):
                return False, ratio

    # High similarity with no numbers or qualification keywords altered -> OCR noise
    return True, ratio


def extract_page_diff_snippets(old_text: str, new_text: str, max_snippet_len: int = 1200) -> Tuple[str, str]:
    """
    Extracts concise relevant differing snippets between old and new text to avoid
    sending unnecessary unchanged boilerplate text to the LLM.
    """
    old_lines = old_text.strip().splitlines()
    new_lines = new_text.strip().splitlines()

    diff = list(difflib.ndiff(old_lines, new_lines))
    old_diff_lines = [line[2:] for line in diff if line.startswith("- ")]
    new_diff_lines = [line[2:] for line in diff if line.startswith("+ ")]

    old_snip = "\n".join(old_diff_lines) if old_diff_lines else old_text.strip()
    new_snip = "\n".join(new_diff_lines) if new_diff_lines else new_text.strip()

    if len(old_snip) > max_snippet_len:
        old_snip = old_snip[:max_snippet_len] + "... [truncated]"
    if len(new_snip) > max_snippet_len:
        new_snip = new_snip[:max_snippet_len] + "... [truncated]"

    return old_snip, new_snip


def deterministic_compare(old_data: Dict[str, Any], new_data: Dict[str, Any]) -> DocumentComparison:
    """
    Level 1: Deterministic Python Comparison.
    Compares:
    - SHA-256 hashes
    - Metadata (total pages, dates, titles)
    - Page counts and page-by-page text
    - Identifies added/removed/modified/unchanged pages
    - Evaluates OCR noise vs meaningful modifications
    """
    old_fn = old_data.get("filename", "old_document")
    new_fn = new_data.get("filename", "new_document")
    old_sha = old_data.get("sha256")
    new_sha = new_data.get("sha256")

    # 1. SHA-256 Hash Comparison
    hash_status = "identical" if (old_sha and new_sha and old_sha == new_sha) else "different"

    if hash_status == "identical":
        logger.info(f"Level 1: Documents '{old_fn}' and '{new_fn}' have IDENTICAL SHA-256 hash ({old_sha}).")
        total_p = len(old_data.get("pages", []))
        page_comps = [
            PageComparison(page_number=i, status="unchanged", similarity_ratio=1.0)
            for i in range(1, total_p + 1)
        ]
        return DocumentComparison(
            old_document=old_fn,
            new_document=new_fn,
            hash_status="identical",
            overall_status="unchanged",
            metadata_changes=[],
            page_comparisons=page_comps,
            text_changes=[],
            semantic_comparison_required=False,
            semantic_changes=[],
            semantic_summary="Documents are bit-for-bit identical based on SHA-256 hash.",
            eligibility_relevance="none",
            review_required=False,
            review_reasons=[],
            comparison_metadata=ComparisonMetadata(
                pipeline_version="1.0_document_comparison",
                old_sha256=old_sha,
                new_sha256=new_sha,
                deterministic_match=True,
                total_pages_old=total_p,
                total_pages_new=total_p,
                pages_modified=0,
                pages_added=0,
                pages_removed=0,
            ),
        )

    # 2. Metadata Comparison
    meta_changes = []
    old_meta = old_data.get("metadata", {})
    new_meta = new_data.get("metadata", {})
    all_keys = set(old_meta.keys()).union(set(new_meta.keys()))
    for k in sorted(all_keys):
        v1 = old_meta.get(k)
        v2 = new_meta.get(k)
        if v1 != v2 and (v1 is not None or v2 is not None):
            meta_changes.append(MetadataChange(field=k, old_value=v1, new_value=v2))

    # 3. Page-Level Comparison
    old_pages = old_data.get("pages", [])
    new_pages = new_data.get("pages", [])
    max_pages = max(len(old_pages), len(new_pages))

    page_comps: List[PageComparison] = []
    text_changes: List[TextChange] = []
    review_reasons: List[str] = []

    pages_modified = 0
    pages_added = 0
    pages_removed = 0
    has_substantive_text_change = False
    all_diffs_are_ocr_noise = True

    for p_idx in range(1, max_pages + 1):
        old_pg = next((p for p in old_pages if p.get("page_number") == p_idx), None)
        new_pg = next((p for p in new_pages if p.get("page_number") == p_idx), None)

        if old_pg and not new_pg:
            # Page Removed
            pages_removed += 1
            has_substantive_text_change = True
            all_diffs_are_ocr_noise = False
            tc = TextChange(
                page_number=p_idx,
                change_type="removed",
                old_text=old_pg.get("text", "").strip(),
                new_text=None,
                similarity_ratio=0.0,
                is_ocr_noise=False,
            )
            text_changes.append(tc)
            page_comps.append(PageComparison(
                page_number=p_idx,
                status="removed",
                similarity_ratio=0.0,
                text_changes=[tc],
                old_page_type=old_pg.get("page_type"),
            ))

        elif new_pg and not old_pg:
            # Page Added
            pages_added += 1
            has_substantive_text_change = True
            all_diffs_are_ocr_noise = False
            tc = TextChange(
                page_number=p_idx,
                change_type="added",
                old_text=None,
                new_text=new_pg.get("text", "").strip(),
                similarity_ratio=0.0,
                is_ocr_noise=False,
            )
            text_changes.append(tc)
            page_comps.append(PageComparison(
                page_number=p_idx,
                status="added",
                similarity_ratio=0.0,
                text_changes=[tc],
                new_page_type=new_pg.get("page_type"),
            ))

        else:
            # Page exists in both
            t_old = (old_pg.get("text") or "").strip()
            t_new = (new_pg.get("text") or "").strip()

            norm_old = " ".join(t_old.split())
            norm_new = " ".join(t_new.split())

            if norm_old == norm_new:
                # Unchanged
                page_comps.append(PageComparison(
                    page_number=p_idx,
                    status="unchanged",
                    similarity_ratio=1.0,
                    text_changes=[],
                    old_page_type=old_pg.get("page_type"),
                    new_page_type=new_pg.get("page_type"),
                ))
            else:
                # Text differs on this page
                is_noise, ratio = detect_ocr_noise(t_old, t_new)
                change_type = "ocr_noise" if is_noise else "modified"

                if not is_noise:
                    has_substantive_text_change = True
                    all_diffs_are_ocr_noise = False
                    pages_modified += 1
                else:
                    review_reasons.append(
                        f"Page {p_idx}: Minor text variance detected that appears to be OCR scanning noise ({ratio * 100:.1f}% similarity)."
                    )

                tc = TextChange(
                    page_number=p_idx,
                    change_type=change_type,
                    old_text=t_old,
                    new_text=t_new,
                    similarity_ratio=ratio,
                    is_ocr_noise=is_noise,
                )
                text_changes.append(tc)
                page_comps.append(PageComparison(
                    page_number=p_idx,
                    status="modified" if not is_noise else "unchanged",
                    similarity_ratio=ratio,
                    text_changes=[tc],
                    old_page_type=old_pg.get("page_type"),
                    new_page_type=new_pg.get("page_type"),
                ))

    # 4. Check for Identical Extracted Text (Scenario 2)
    if len(text_changes) == 0:
        logger.info(f"Level 1: Hashes differ, but all extracted page texts are 100% identical between '{old_fn}' and '{new_fn}'.")
        return DocumentComparison(
            old_document=old_fn,
            new_document=new_fn,
            hash_status="different",
            overall_status="unchanged",
            metadata_changes=meta_changes,
            page_comparisons=page_comps,
            text_changes=[],
            semantic_comparison_required=False,
            semantic_changes=[],
            semantic_summary="File SHA-256 differs (e.g. PDF metadata/encoding), but all extracted page texts are 100% identical.",
            eligibility_relevance="none",
            review_required=False,
            review_reasons=[],
            comparison_metadata=ComparisonMetadata(
                pipeline_version="1.0_document_comparison",
                old_sha256=old_sha,
                new_sha256=new_sha,
                deterministic_match=True,
                total_pages_old=len(old_pages),
                total_pages_new=len(new_pages),
                pages_modified=0,
                pages_added=0,
                pages_removed=0,
            ),
        )

    # 5. Check for Completely Different Documents (Scenario 14)
    old_full = " ".join((p.get("text") or "") for p in old_pages).strip()
    new_full = " ".join((p.get("text") or "") for p in new_pages).strip()
    old_words = set(re.findall(r"\b\w+\b", old_full.lower()))
    new_words = set(re.findall(r"\b\w+\b", new_full.lower()))
    word_jaccard = (
        len(old_words.intersection(new_words)) / len(old_words.union(new_words))
        if (old_words and new_words) else 0.0
    )
    overall_sim = difflib.SequenceMatcher(None, old_full, new_full).ratio() if old_full and new_full else 0.0

    old_title = str(old_meta.get("scheme_name") or old_fn).lower()
    new_title = str(new_meta.get("scheme_name") or new_fn).lower()
    is_completely_different = (
        (old_title != new_title and word_jaccard < 0.35 and len(old_pages) > 0 and len(new_pages) > 0)
        or (word_jaccard < 0.15 and len(old_pages) > 0 and len(new_pages) > 0)
        or (overall_sim < 0.25 and len(old_pages) > 0 and len(new_pages) > 0 and old_title != new_title)
    )

    if is_completely_different:
        reason = f"Documents appear to be completely different schemes (Vocabulary overlap: {word_jaccard * 100:.1f}%, text similarity: {overall_sim * 100:.1f}%)."
        review_reasons.append(reason)
        return DocumentComparison(
            old_document=old_fn,
            new_document=new_fn,
            hash_status="different",
            overall_status="different_document",
            metadata_changes=meta_changes,
            page_comparisons=page_comps,
            text_changes=text_changes,
            semantic_comparison_required=True,
            semantic_changes=[],
            semantic_summary="Documents appear to be completely different or unrelated government schemes.",
            eligibility_relevance="uncertain",
            review_required=True,
            review_reasons=list(dict.fromkeys(review_reasons)),
            comparison_metadata=ComparisonMetadata(
                pipeline_version="1.0_document_comparison",
                old_sha256=old_sha,
                new_sha256=new_sha,
                deterministic_match=False,
                total_pages_old=len(old_pages),
                total_pages_new=len(new_pages),
                pages_modified=pages_modified,
                pages_added=pages_added,
                pages_removed=pages_removed,
            ),
        )

    # 6. Check if only OCR Noise exists (Scenario 13)
    if all_diffs_are_ocr_noise and len(text_changes) > 0:
        logger.info(f"Level 1: Differences between '{old_fn}' and '{new_fn}' are minor OCR scanning noise.")
        return DocumentComparison(
            old_document=old_fn,
            new_document=new_fn,
            hash_status="different",
            overall_status="unchanged",
            metadata_changes=meta_changes,
            page_comparisons=page_comps,
            text_changes=text_changes,
            semantic_comparison_required=False,
            semantic_changes=[],
            semantic_summary="Text differences are minor OCR noise/scanning artifacts without substantive policy changes.",
            eligibility_relevance="uncertain",
            review_required=True,
            review_reasons=list(dict.fromkeys(review_reasons)),
            comparison_metadata=ComparisonMetadata(
                pipeline_version="1.0_document_comparison",
                old_sha256=old_sha,
                new_sha256=new_sha,
                deterministic_match=True,
                total_pages_old=len(old_pages),
                total_pages_new=len(new_pages),
                pages_modified=pages_modified,
                pages_added=pages_added,
                pages_removed=pages_removed,
            ),
        )

    # 7. Substantive changes require Level 2 Semantic LLM comparison
    return DocumentComparison(
        old_document=old_fn,
        new_document=new_fn,
        hash_status="different",
        overall_status="possible_change",
        metadata_changes=meta_changes,
        page_comparisons=page_comps,
        text_changes=text_changes,
        semantic_comparison_required=has_substantive_text_change,
        semantic_changes=[],
        semantic_summary=None,
        eligibility_relevance="none",
        review_required=len(review_reasons) > 0,
        review_reasons=list(dict.fromkeys(review_reasons)),
        comparison_metadata=ComparisonMetadata(
            pipeline_version="1.0_document_comparison",
            old_sha256=old_sha,
            new_sha256=new_sha,
            deterministic_match=False,
            total_pages_old=len(old_pages),
            total_pages_new=len(new_pages),
            pages_modified=pages_modified,
            pages_added=pages_added,
            pages_removed=pages_removed,
        ),
    )


SEMANTIC_SYSTEM_PROMPT = """You are an expert Karnataka Government Scheme Document Comparison Specialist.
Your sole job is to analyze textual differences between an OLD and NEW document version and determine whether
the changes affect CANDIDATE ELIGIBILITY (who qualifies or is disqualified) versus administrative/procedural changes.

CRITICAL INSTRUCTIONS & ANTI-HALLUCINATION GUARDRAILS:

1. CLASSIFY EACH CHANGE INTO EXACTLY ONE CATEGORY:
   - 'eligibility_related': Changes in who qualifies (e.g. land ceiling, farmer status, income limit, age limit, residency criteria, caste/category).
   - 'exclusion_related': Changes in disqualifications (e.g. government servants, institutional landholders, income tax payees excluded).
   - 'administrative': Changes in government office coordination, staff appointment, file forwarding, record preservation.
   - 'procedural': Changes in application submission methods, portal login steps, or document verification process (e.g. 'Submit to Taluk office' vs 'Submit through designated office'). This is NOT an eligibility change!
   - 'document_status': Changes in notification status, amendment notes (e.g. 'There is no change in notification' vs 'Amended notification issued'). This is NOT an eligibility change!
   - 'formatting': Preamble, headers, styling, or minor rephrasing without meaning change.
   - 'unclear': Degraded text or ambiguous wording.

2. ELIGIBILITY IMPACT CRITERIA:
   - 'clearly_relevant': Change directly modifies candidate qualification or disqualification terms (income, age, land size, occupation, resident status).
   - 'potentially_relevant': Change modifies definitions or conditions that might alter who qualifies.
   - 'none': Change is purely administrative, procedural, document status, or formatting.
   - 'uncertain': Ambiguous or degraded text.

3. STRICT FACTUAL EVIDENCE:
   - Provide verbatim old_evidence and new_evidence from the supplied snippets.
   - NEVER invent rules, criteria, or provisions not explicitly present in the text snippets.
"""


def filter_and_validate_semantic_changes(
    semantic_changes: List[SemanticChangeItem],
    text_changes: List[TextChange],
) -> Tuple[List[SemanticChangeItem], str, bool, List[str]]:
    """
    Quality control post-processor on LLM semantic output:
    Guards against misclassifying administrative or document status changes as eligibility.
    Returns (cleaned_changes, overall_eligibility_relevance, review_required, review_reasons).
    """
    cleaned_changes = []
    has_clearly_relevant = False
    has_potentially_relevant = False
    has_uncertain = False
    review_reasons = []

    for item in semantic_changes:
        ev_text = f"{item.old_evidence or ''} {item.new_evidence or ''} {item.description}".lower()

        # Check if accidentally classified administrative instruction or status note as eligibility
        is_admin_or_status = any(k in ev_text for k in ADMIN_AND_STATUS_PATTERNS)
        has_qualification_marker = contains_candidate_attribute(ev_text)

        if item.category in ("eligibility_related", "exclusion_related"):
            if is_admin_or_status and not has_qualification_marker:
                logger.info(
                    f"Correcting misclassified eligibility item to procedural/administrative: '{item.description[:60]}'"
                )
                if any(s in ev_text for s in ("notification", "amendment", "ಅಧಿಸೂಚನೆ", "ತಿದ್ದುಪಡಿ")):
                    item.category = "document_status"
                else:
                    item.category = "procedural"
                item.eligibility_relevance = "none"

        # Determine attribute if not set
        if item.category in ("eligibility_related", "exclusion_related") and not item.affected_attribute:
            if any(k in ev_text for k in ("income", "ಆದಾಯ", "rupees", "rs.", "tax", "ತೆರಿಗೆ")):
                item.affected_attribute = "income"
            elif any(k in ev_text for k in ("age", "ವಯಸ್ಸು", "years old")):
                item.affected_attribute = "age"
            elif any(k in ev_text for k in ("land", "hectare", "acre", "ಭೂಮಿ", "ಜಮೀನು", "ಹೆಕ್ಟೇರ್", "ಎಕರೆ")):
                item.affected_attribute = "landholding"
            elif any(k in ev_text for k in ("resident", "residency", "ನಿವಾಸಿ")):
                item.affected_attribute = "residency"
            elif any(k in ev_text for k in ("farmer", "small farmer", "marginal farmer", "ರೈತ")):
                item.affected_attribute = "farmer_category"
            elif any(k in ev_text for k in ("government employee", "government servant", "ಸರ್ಕಾರಿ ನೌಕರ", "pension")):
                item.affected_attribute = "government_employee"

        if item.category in ("eligibility_related", "exclusion_related"):
            if item.eligibility_relevance not in ("clearly_relevant", "potentially_relevant"):
                item.eligibility_relevance = "clearly_relevant"

        if item.eligibility_relevance == "clearly_relevant":
            has_clearly_relevant = True
        elif item.eligibility_relevance == "potentially_relevant":
            has_potentially_relevant = True
        elif item.eligibility_relevance == "uncertain":
            has_uncertain = True

        cleaned_changes.append(item)

    if has_clearly_relevant:
        overall_relevance = "clearly_relevant"
    elif has_potentially_relevant:
        overall_relevance = "potentially_relevant"
    elif has_uncertain:
        overall_relevance = "uncertain"
        review_reasons.append("Semantic comparison contains uncertain or ambiguous modifications.")
    else:
        overall_relevance = "none"

    review_required = len(review_reasons) > 0 or has_uncertain
    return cleaned_changes, overall_relevance, review_required, review_reasons


def semantic_compare(
    comparison: DocumentComparison,
    llm_client: Optional[LLMClient] = None,
    model: Optional[str] = None,
    max_retries: int = 2,
) -> DocumentComparison:
    """
    Level 2: Semantic LLM Comparison.
    Provides only the relevant old and new differing snippets to the LLM.
    Classifies changes into eligibility_related, exclusion_related, administrative,
    procedural, document_status, formatting, or unclear.
    """
    if not comparison.semantic_comparison_required:
        return comparison

    active_model = model or LLM_MODEL
    client = llm_client or LLMClient(model=active_model)

    # Format relevant differences
    diff_sections = []
    for tc in comparison.text_changes:
        if tc.is_ocr_noise:
            continue
        old_snip, new_snip = extract_page_diff_snippets(tc.old_text or "", tc.new_text or "")
        diff_sections.append(
            f"--- PAGE {tc.page_number} [{tc.change_type.upper()}] ---\n"
            f"[OLD TEXT]:\n{old_snip if old_snip else '[NO PREVIOUS TEXT]'}\n\n"
            f"[NEW TEXT]:\n{new_snip if new_snip else '[PAGE REMOVED]'}\n"
        )

    if not diff_sections:
        comparison.semantic_comparison_required = False
        comparison.semantic_summary = "No substantive text differences to evaluate semantically."
        return comparison

    diff_context = "\n" + ("=" * 50) + "\n" + "\n".join(diff_sections)

    json_skeleton = {
        "semantic_summary": "Concise summary of differences and whether eligibility is affected",
        "eligibility_relevance": "clearly_relevant / potentially_relevant / none / uncertain",
        "changes": [
            {
                "category": "eligibility_related / exclusion_related / administrative / procedural / document_status / formatting / unclear",
                "description": "Clear explanation of what changed",
                "eligibility_relevance": "clearly_relevant / potentially_relevant / none / uncertain",
                "affected_attribute": "income / age / landholding / farmer_category / residency / other / null",
                "old_evidence": "Verbatim quote from old text or null",
                "new_evidence": "Verbatim quote from new text or null"
            }
        ]
    }

    user_prompt = f"""TEXT DIFFERENCES BETWEEN OLD AND NEW DOCUMENT VERSIONS:
{diff_context}

TARGET JSON FORMAT SPECIFICATION:
{json.dumps(json_skeleton, indent=2)}

TASK:
Analyze the text differences above. Classify each difference into:
- eligibility_related / exclusion_related: ONLY if it changes who qualifies or who is disqualified.
- administrative / procedural: Application submission instructions, office forwarding, coordinator appointments. (NOT eligibility!)
- document_status: Statements about amendments, circular dispatch, or notification status. (NOT eligibility!)
- formatting: Headers, spacing, rephrasing without policy impact.

Return valid JSON matching the format specification above.
"""

    try:
        raw_json = client.generate_json(
            prompt=user_prompt,
            system_prompt=SEMANTIC_SYSTEM_PROMPT,
            temperature=0.0,
            max_retries=max_retries,
        )

        semantic_summary = raw_json.get("semantic_summary", "Semantic comparison completed.")
        raw_changes = raw_json.get("changes", [])

        parsed_items = []
        for ch in raw_changes:
            parsed_items.append(SemanticChangeItem(
                category=ch.get("category", "unclear"),
                description=ch.get("description", "Text modification"),
                eligibility_relevance=ch.get("eligibility_relevance", "none"),
                affected_attribute=ch.get("affected_attribute"),
                old_evidence=ch.get("old_evidence"),
                new_evidence=ch.get("new_evidence"),
            ))

        # Quality Control
        cleaned_items, overall_rel, rev_req, rev_reasons = filter_and_validate_semantic_changes(
            parsed_items, comparison.text_changes
        )

        comparison.semantic_summary = semantic_summary
        comparison.semantic_changes = cleaned_items
        comparison.eligibility_relevance = overall_rel
        if rev_req:
            comparison.review_required = True
            comparison.review_reasons.extend(rev_reasons)
            comparison.review_reasons = list(dict.fromkeys(comparison.review_reasons))

        comparison.comparison_metadata.model_used = active_model

    except Exception as e:
        logger.warning(f"Semantic comparison fallback due to LLM error: {type(e).__name__} - {e}")
        comparison.semantic_summary = f"Semantic LLM comparison could not be completed: {str(e)}"
        comparison.eligibility_relevance = "uncertain"
        comparison.review_required = True
        comparison.review_reasons.append(f"Semantic LLM interpretation failed: {str(e)}")

    return comparison


def compare_documents(
    old_doc: Union[str, Path, Dict[str, Any]],
    new_doc: Union[str, Path, Dict[str, Any]],
    llm_client: Optional[LLMClient] = None,
    model: Optional[str] = None,
    save_output: bool = True,
    output_dir: Optional[Path] = None,
) -> DocumentComparison:
    """
    Master Checkpoint 11 Entry Point.
    Executes two-level comparison:
    1. Deterministic Python comparison
    2. Semantic LLM comparison (if needed)
    Saves structured result to data/comparisons/
    """
    old_data = load_document_comparison_data(old_doc)
    new_data = load_document_comparison_data(new_doc)

    logger.info(
        f"Starting Document Comparison: Old='{old_data.get('filename')}' vs New='{new_data.get('filename')}'"
    )

    # Level 1: Deterministic Comparison
    comp_result = deterministic_compare(old_data, new_data)

    # Level 2: Semantic Comparison (if required)
    if comp_result.semantic_comparison_required:
        logger.info("Level 1 detected substantive text changes. Proceeding to Level 2 Semantic Comparison...")
        comp_result = semantic_compare(
            comp_result,
            llm_client=llm_client,
            model=model,
        )
    else:
        logger.info("Level 1 deterministic comparison concluded no semantic LLM evaluation is needed.")

    # Save output if requested
    if save_output:
        target_dir = output_dir or COMPARISONS_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        old_stem = Path(comp_result.old_document).stem
        new_stem = Path(comp_result.new_document).stem
        out_path = target_dir / f"{old_stem}_vs_{new_stem}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(comp_result.model_dump_json(indent=2))
        logger.info(f"Saved comparison result to: {out_path}")

    return comp_result
