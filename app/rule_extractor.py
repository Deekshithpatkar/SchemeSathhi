"""
Semantic Scheme and Rule Extraction Pipeline (Checkpoint 10).
Laser-focused on extracting rules determining candidate eligibility and exclusions
from Step 9 Document Understanding JSON.
"""

import json
from pathlib import Path
from typing import Dict, Any, Union, Optional, List
from datetime import datetime, timezone

from app.config import EXTRACTED_RULES_DIR, setup_logger, LLM_MODEL
from app.schemas import (
    SchemeExtraction,
    SchemeEvidence,
    RuleItem,
    ExtractionMetadata,
)
from app.llm_client import LLMClient

logger = setup_logger("rule_extractor")

SYSTEM_PROMPT = """You are an expert Karnataka Government Scheme Rule Extraction Specialist.
Your sole purpose is to extract explicit rules that determine whether an individual citizen/candidate IS ELIGIBLE or IS EXCLUDED from a government scheme.

CRITICAL INSTRUCTIONS & ANTI-HALLUCINATION GUARDRAILS:

1. FOCUS ONLY ON CANDIDATE QUALIFICATION:
   Extract ONLY rules that directly decide if a person qualifies:
   A. ELIGIBILITY RULES (eligibility_rules):
      - Farmer status (e.g. 'Must be a small or marginal farmer')
      - Land ownership & land size (e.g. 'Must own less than 2 hectares of cultivable land')
      - Category / caste requirements (e.g. 'SC/ST/OBC or General')
      - Income thresholds (e.g. 'Annual family income must be below ₹2,00,000')
      - Age criteria (e.g. 'Age must be between 18 and 60 years')
      - Geographic & residency requirements (e.g. 'Must be a permanent resident of Karnataka')
      - Specific occupation or crop criteria

   B. EXCLUSION RULES (exclusion_rules):
      - Disqualifications (e.g. 'Institutional landholders are excluded')
      - Employment exclusions (e.g. 'Government employees and retired pensioners are not eligible')
      - Income tax payers or persons above income threshold
      - Persons already receiving duplicate/other specified benefits

2. REJECT AND IGNORE STATEMENTS ABOUT AMENDMENTS, DOCUMENT STATUS, ADMINISTRATIVE HANDLING, NOTIFICATIONS, OR PROCEDURAL CHANGES:
   You MUST IGNORE:
   - Statements about document amendments or notification status:
     e.g., 'There is no change in said notification' / 'ಸದರಿ ಅಧಿಸೂಚನೆಯಲ್ಲಿ ಯಾವುದೇ ಬದಲಾವಣೆ ಇರುವುದಿಲ್ಲ' / 'notification stands amended' / 'order remains in force' / 'clarification issued' -> MUST BE IGNORED. These are NOT exclusion rules!
   - Procedural or administrative handling:
     e.g., 'Physical declarations will be sent to Taluk office for preservation' / 'forwarded to Accountant General' / 'dispatch spare copies to guard file' -> MUST BE IGNORED.
   - Blank application form fields (Applicant Name, Gender, Mobile Number, Aadhaar Number, Bank Account Number) -> MUST BE IGNORED.
     * Note: Having an input blank on a form is NOT an eligibility rule. Only extract if the document explicitly mandates: "Applicant must possess an active Aadhaar number to qualify".
   - Application procedures / submission instructions (e.g. 'Submit forms to the Taluk Agriculture Officer' -> IGNORE).
   - Signatures, stamp blocks, office addresses, dispatch lists -> MUST BE IGNORED.
   - A rule is ONLY valid if its evidence explicitly describes a candidate qualification, disqualification, or condition that directly affects eligibility (e.g. land ceiling, farmer status, income limit, institutional landholders excluded, government employees excluded).
   - If the document contains NO explicit candidate qualification rules, return EMPTY lists:
     "eligibility_rules": [], "exclusion_rules": []

3. STRICT FACTUALITY & ZERO HALLUCINATION:
   - Extract ONLY rules physically supported by the text and tables in this document.
   - Do NOT use outside general knowledge of PM-KISAN, Karnataka schemes, or general farming policies.
   - If the document does NOT contain explicit eligibility or exclusion criteria, return empty lists:
     "eligibility_rules": [], "exclusion_rules": []
   - A correct empty result is far better than a fabricated rule!

4. EVIDENCE IS MANDATORY:
   - Every rule must have an 'evidence' object with:
     * 'page_number': 1-based page number where the rule appears
     * 'source_text': verbatim quote from the document
     * 'ocr_confidence': the OCR confidence score (0-100) from the source block/cell
     * 'table_index', 'row_index', 'column_index', 'cell_text' if from a table

5. SEMANTIC CONFIDENCE:
   - Set 'semantic_confidence' to a realistic value (default 0.85). Never set 1.0.
   - If meaning is ambiguous or text is degraded, set 'review_required': true.
"""


def format_document_context(doc_json: Dict[str, Any], max_text_chars: int = 12000) -> str:
    """
    Transforms Step 9 structured JSON into an optimized, readable representation
    for the LLM, clearly distinguishing pages, text blocks, tables, and form fields
    while preserving row/column coordinates and OCR confidence.
    """
    context_lines = []

    doc_meta = doc_json.get("document", {})
    context_lines.append(f"DOCUMENT FILENAME: {doc_meta.get('filename', 'Unknown')}")
    context_lines.append(f"TOTAL PAGES: {doc_meta.get('total_pages', len(doc_json.get('pages', [])))}")
    context_lines.append(f"SOURCE URL: {doc_meta.get('source_url', 'None')}")
    context_lines.append("=" * 60)

    pages = doc_json.get("pages", [])
    for page in pages:
        p_num = page.get("page_number", "?")
        p_type = page.get("page_type", "UNKNOWN")
        avg_conf = page.get("avg_confidence", 100.0)
        context_lines.append(f"\n--- PAGE {p_num} [Type: {p_type}, Avg OCR Conf: {avg_conf:.1f}%] ---")

        # 1. Tables on this page
        tables = page.get("tables", [])
        if tables:
            context_lines.append(f"Detected Tables: {len(tables)}")
            for t_idx, t in enumerate(tables):
                rows = t.get("rows", [])
                context_lines.append(f"  [Table {t_idx} - {len(rows)} rows, BBox: {t.get('bbox')}]")
                for r in rows:
                    r_idx = r.get("row_index", 0)
                    cells = r.get("cells", [])
                    cell_strs = []
                    for c in cells:
                        c_idx = c.get("column", 0)
                        txt = c.get("text")
                        conf = c.get("confidence", 0.0)
                        if txt:
                            cell_strs.append(f"Col {c_idx} (Conf: {conf:.0f}%): \"{txt}\"")
                        else:
                            cell_strs.append(f"Col {c_idx}: [BLANK]")
                    if any("Col" in s and "[BLANK]" not in s for s in cell_strs):
                        context_lines.append(f"    Row {r_idx}: " + " | ".join(cell_strs))

        # 2. Form fields detected on this page
        forms = page.get("forms")
        if forms and forms.get("is_form"):
            context_lines.append("  Detected Form Template Fields (IGNORE as rules unless explicitly stated as eligibility criteria):")
            for fld in forms.get("fields", []):
                val = fld.get("value")
                val_str = f"'{val}'" if val is not None else "[BLANK INPUT]"
                context_lines.append(f"    - Label: '{fld.get('label')}' -> Value: {val_str}")

        # 3. Text / narrative blocks
        blocks = page.get("blocks", [])
        if blocks:
            context_lines.append("  Text Content:")
            for b in blocks:
                b_text = b.get("text", "").strip()
                b_conf = b.get("confidence", avg_conf)
                if b_text:
                    context_lines.append(f"    [Conf: {b_conf:.0f}%] {b_text}")
        elif page.get("full_text"):
            context_lines.append(f"  Full Text: {page['full_text']}")

    full_context = "\n".join(context_lines)
    if len(full_context) > max_text_chars:
        return full_context[:max_text_chars] + "\n... [Context truncated due to size limits] ..."
    return full_context


def is_candidate_qualification_rule(rule: RuleItem) -> tuple[bool, str]:
    """
    Evaluates whether an extracted rule genuinely represents an explicit candidate
    qualification, disqualification, or condition that directly affects eligibility.

    Rejects any statement about:
    - amendments or document status (e.g. 'no change in said notification', 'remains in force')
    - administrative handling (e.g. internal forwarding, officer appointments, record preservation)
    - notifications or procedural circulars (e.g. gazette publication, dispatch lists)
    - application instructions or blank form fields

    Returns (is_valid, reason).
    """
    rule_text = (rule.rule or "").strip()
    evidence_text = ""
    if rule.evidence and rule.evidence.source_text:
        evidence_text = str(rule.evidence.source_text).strip()

    combined = f"{rule_text} {evidence_text}".lower()

    if not rule_text or rule_text.lower() in ("null", "none", ""):
        return False, "Empty or null rule statement"

    # 1. Non-qualification patterns: Amendments, Document Status, Notifications & Procedural
    amendment_and_status_patterns = [
        "ಬದಲಾವಣೆ ಇರುವುದಿಲ್ಲ", "ಬದಲಾವಣೆಯಿಲ್ಲ", "ಬದಲಾವಣೆ ಇಲ್ಲ", "ಯಾವುದೇ ಬದಲಾವಣೆ",
        "ಉಳಿದಂತೆ ಸದರಿ", "ಅಧಿಸೂಚನೆಯಲ್ಲಿ ಯಾವುದೇ", "ತಿದ್ದುಪಡಿ", "ಜಾರಿಯಲ್ಲಿರುತ್ತದೆ",
        "ಜಾರಿಗೆ ಬರುತ್ತದೆ", "ಹಿಂಪಡೆಯಲಾಗಿದೆ", "ಪ್ರಕಟಿಸಲಾಗಿದೆ",
        "no change in", "remains unchanged", "remains in force", "amendment",
        "amended", "notification status", "supersedes", "clarification issued",
        "published in gazette", "effective immediately", "effective from",
    ]
    for pat in amendment_and_status_patterns:
        if pat in combined:
            return False, f"Statement pertains to amendment, document status, or notification ('{pat}') rather than candidate eligibility"

    # 2. Administrative handling, office procedures, forwarding & dispatch
    admin_handling_patterns = [
        "ಕಳುಹಿಸಲಾಗುವುದು", "ರವಾನಿಸಲಾಗಿದೆ", "ರವಾನೆ", "ಸಂರಕ್ಷಿಸಲು",
        "ಪರಿಶೀಲಿಸಲು ಮತ್ತು ಸಂರಕ್ಷಿಸಲು", "ಕಛೇರಿಗೆ", "ಕಚೇರಿಗೆ", "ಕಛೇರಿ", "ಕಚೇರಿ",
        "ನಿಯತಕಾಲಿಕವಾಗಿ", "ರಕ್ಷಾ ಕಡತ", "ಹೆಚ್ಚುವರಿ ಪ್ರತಿಗಳು", "ಸಹಾಯಕ ಕೃಷಿ ನಿರ್ದೇಶಕರ",
        "ಅಧೀನ ಕಾರ್ಯದರ್ಶಿ", "ಪ್ರಧಾನ ಮಹಾಲೇಖಪಾಲರು", "ಆಂತರಿಕ ಆರ್ಥಿಕ ಸಲಹೆಗಾರರು",
        "ಆಯುಕ್ತರ ಮುಖಾಂತರ", "ಆಜ್ಞಾನುಸಾರ", "ರಾಜ್ಯಪಾಲರ",
        "forwarded to", "submitted to", "office of", "karyalaya",
        "coordinator", "periodically", "dispatch", "preservation",
        "guard file", "spare copies", "under secretary", "governor of karnataka",
        "accountant general", "internal financial advisor", "verification committee",
        "nodal officer", "administrative handling", "procedural change"
    ]
    for pat in admin_handling_patterns:
        if pat in combined:
            return False, f"Statement pertains to administrative handling or office procedure ('{pat}')"

    # 3. Explicit Candidate Qualification / Disqualification Condition Check:
    # Rule or evidence must describe an actual qualification, disqualification, or condition
    # that directly affects a candidate's eligibility.
    candidate_qualification_patterns = [
        # Kannada indicators
        "ರೈತ", "ಕೃಷಿಕ", "ಹಿಡುವಳಿ", "ಹಿಡುವಳಿದಾರ",
        "ಭೂಮಿ", "ಜಮೀನು", "ಹೆಕ್ಟೇರ್", "ಎಕರೆ", "ಗುಂಟೆ", "ಖುಷ್ಕಿ", "ತರಿ", "ಬಾಗಾಯ್ತು", "ಕ್ಷೇತ್ರ", "ವಿಸ್ತೀರ್ಣ",
        "ಆದಾಯ", "ಆದಾಯತೆರಿಗೆ", "ತೆರಿಗೆ", "ಬಿಪಿಎಲ್", "ಎಪಿಎಲ್", "ರೂಪಾಯಿ", "ರೂ.",
        "ವಯಸ್ಸು", "ವರ್ಷ",
        "ಪರಿಶಿಷ್ಟ ಜಾತಿ", "ಪರಿಶಿಷ್ಟ ಪಂಗಡ", "ಹಿಂದುಳಿದ ವರ್ಗ", "ಜಾತಿ", "ಪ್ರವರ್ಗ", "ಮಹಿಳೆ",
        "ಕುಟುಂಬ", "ಪತಿ", "ಪತ್ನಿ", "ಮಕ್ಕಳು", "ಅಪ್ರಾಪ್ತ",
        "ನಿವಾಸಿ", "ವಾಸವಾಗಿರುವ", "ಕರ್ನಾಟಕದ ನಿವಾಸಿ",
        "ಸರ್ಕಾರಿ ನೌಕರ", "ನೌಕರರಾಗಿ", "ಅಧಿಕಾರಿ", "ಸಾಂಸ್ಥಿಕ", "ಸಂಸ್ಥೆ", "ಪಿಂಚಣಿ", "ವೈದ್ಯ",
        "ಇಂಜಿನಿಯರ್", "ವಕೀಲ", "ಸಚಿವ", "ಸಂಸದ", "ಶಾಸಕ", "ತೆರಿಗೆ ಪಾವತಿದಾರ", "ಅನರ್ಹ",
        "ಅರ್ಹತೆ", "ಅರ್ಹ", "ಫಲಾನುಭವಿ", "ಆಧಾರ್", "ಫ್ರೂಟ್ಸ್",
        # English indicators
        "farmer", "cultivator", "landholder", "agriculturalist",
        "land", "landholding", "hectare", "acre", "ha", "gunta", "cultivable", "dry land", "wet land", "irrigated",
        "income", "annual income", "tax", "taxpayer", "payee", "bpl", "apl", "salary", "rupees", "rs.",
        "age", "years of age", "years old",
        "caste", "sc", "st", "obc", "general category", "minority", "women", "female", "male", "gender",
        "family", "household", "spouse", "children", "minor",
        "resident", "residency", "domicile", "karnataka",
        "government servant", "government employee", "psu employee", "institutional landholder", "pension",
        "income tax payee", "doctor", "engineer", "lawyer", "chartered accountant", "minister", "mp", "mla",
        "constitutional post", "disqualified", "excluded", "exclusion",
        "eligible", "eligibility", "qualifies", "qualification", "must own", "must possess", "beneficiary",
        "aadhaar", "fruits"
    ]
    has_candidate_indicator = any(p in combined for p in candidate_qualification_patterns)
    if not has_candidate_indicator:
        return False, "Evidence does not describe a candidate qualification, disqualification, or condition affecting eligibility"

    return True, "Valid candidate qualification rule"


def audit_and_enhance_extraction(
    extraction: SchemeExtraction,
    doc_json: Dict[str, Any],
    model_name: str,
    low_conf_threshold: float = 60.0,
) -> SchemeExtraction:
    """
    Quality control post-processor:
    1. Rejects non-candidate qualification rules (amendments, document status, administrative handling).
    2. Checks physical OCR confidence on all evidence items.
    3. Flags review_required if OCR confidence is below threshold.
    4. Calculates rule counts and review counts with 100% internal consistency.
    """
    review_reasons = list(extraction.review_reasons)
    rule_review_count = 0

    # 1. Audit and filter eligibility rules
    filtered_eligibility = []
    for rule in extraction.eligibility_rules:
        is_valid, reason = is_candidate_qualification_rule(rule)
        if not is_valid:
            logger.info(f"Filtering out invalid candidate eligibility rule: '{rule.rule[:60]}' - Reason: {reason}")
            continue

        if rule.evidence and rule.evidence.ocr_confidence is not None:
            if rule.evidence.ocr_confidence < low_conf_threshold:
                rule.review_required = True
                rev_reason = f"Low OCR confidence ({rule.evidence.ocr_confidence:.1f}%) on page {rule.evidence.page_number} for rule: '{rule.rule[:40]}'"
                rule.review_reasons.append(rev_reason)
                review_reasons.append(rev_reason)

        if rule.review_required:
            rule_review_count += 1
        filtered_eligibility.append(rule)

    extraction.eligibility_rules = filtered_eligibility

    # 2. Audit and filter exclusion rules
    filtered_exclusions = []
    for rule in extraction.exclusion_rules:
        is_valid, reason = is_candidate_qualification_rule(rule)
        if not is_valid:
            logger.info(f"Filtering out invalid candidate exclusion rule: '{rule.rule[:60]}' - Reason: {reason}")
            continue

        if rule.evidence and rule.evidence.ocr_confidence is not None:
            if rule.evidence.ocr_confidence < low_conf_threshold:
                rule.review_required = True
                rev_reason = f"Low OCR confidence ({rule.evidence.ocr_confidence:.1f}%) on page {rule.evidence.page_number} for exclusion: '{rule.rule[:40]}'"
                rule.review_reasons.append(rev_reason)
                review_reasons.append(rev_reason)

        if rule.review_required:
            rule_review_count += 1
        filtered_exclusions.append(rule)

    extraction.exclusion_rules = filtered_exclusions

    # 3. Audit document-level OCR quality from Step 9
    scanned_pages = [p for p in doc_json.get("pages", []) if p.get("page_type") in ("SCANNED", "TABLE")]
    if scanned_pages:
        avg_scan_conf = sum(p.get("avg_confidence", 0.0) for p in scanned_pages) / len(scanned_pages)
        if avg_scan_conf < low_conf_threshold:
            review_reasons.append(f"Average document OCR confidence is low ({avg_scan_conf:.1f}% across scanned pages).")

    # If scheme name is missing
    if not extraction.scheme_name or str(extraction.scheme_name).lower() in ("unknown", "scheme", "government order", "none"):
        review_reasons.append("Scheme name could not be definitively identified from document text.")

    # Deduplicate review reasons
    unique_review_reasons = list(dict.fromkeys(review_reasons))
    is_review_req = len(unique_review_reasons) > 0 or rule_review_count > 0

    # Ensure review_required_count accurately reflects both rule-level and document-level review needs
    review_required_count = rule_review_count
    if len(unique_review_reasons) > 0:
        review_required_count += len(unique_review_reasons)

    doc_meta = doc_json.get("document", {})
    filename = doc_meta.get("filename", "unknown_document")

    extraction.review_required = is_review_req
    extraction.review_reasons = unique_review_reasons

    extraction.extraction_metadata = ExtractionMetadata(
        pipeline_version="1.0_semantic_extraction",
        model=model_name,
        processed_at=datetime.now(timezone.utc).isoformat(),
        source_document=filename,
        validation_status="review_needed" if is_review_req else "valid",
        rule_count=len(extraction.eligibility_rules) + len(extraction.exclusion_rules),
        review_required_count=review_required_count,
        errors=[],
    )

    return extraction


def save_extracted_rules(
    extraction: SchemeExtraction,
    source_filename: str,
    output_dir: Optional[Path] = None,
) -> Path:
    """
    Saves the extracted semantic rules JSON to data/extracted_rules/<filename>_rules.json.
    """
    target_dir = output_dir or EXTRACTED_RULES_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    stem = Path(source_filename).stem
    out_file = target_dir / f"{stem}_rules.json"

    data = extraction.model_dump(mode="json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    logger.info(f"Saved extracted semantic scheme rules to: {out_file}")
    return out_file


def extract_scheme_rules(
    doc_input: Union[str, Path, Dict[str, Any]],
    llm_client: Optional[LLMClient] = None,
    model: Optional[str] = None,
    max_retries: int = 2,
    output_dir: Optional[Path] = None,
) -> SchemeExtraction:
    """
    Main Checkpoint 10 Pipeline function:
    1. Loads Step 9 structured JSON.
    2. Builds factual prompt context focused on candidate eligibility.
    3. Invokes LLM with strict Pydantic JSON schema.
    4. Validates and post-processes with quality assurance.
    5. Saves output to data/extracted_rules/<filename>_rules.json.
    """
    # Step 1: Load input JSON
    if isinstance(doc_input, (str, Path)):
        doc_path = Path(doc_input)
        if not doc_path.exists():
            raise FileNotFoundError(f"Step 9 structured JSON not found at: {doc_input}")
        with open(doc_path, "r", encoding="utf-8") as f:
            doc_json = json.load(f)
        filename = doc_path.name
    elif isinstance(doc_input, dict):
        doc_json = doc_input
        filename = doc_json.get("document", {}).get("filename", "in_memory_doc.json")
    else:
        raise TypeError("doc_input must be a file path or a dictionary")

    logger.info(f"Starting Checkpoint 10 semantic extraction for: {filename}")

    # Step 2: Initialize LLM client
    active_model = model or LLM_MODEL
    client = llm_client or LLMClient(model=active_model)

    # Step 3: Format document context
    doc_context = format_document_context(doc_json)

    # Concise JSON skeleton strictly focused on eligibility and exclusions
    json_skeleton = {
        "scheme_name": "Official Scheme Name or null",
        "department": "Government Department or null",
        "document_type": "guidelines / government_order / circular / application_form / unknown",
        "document_date": "Date as stated in document or null",
        "version_information": "GO number or version label or null",
        "purpose": "Brief stated purpose or null",
        "eligibility_rules": [
          {
            "rule": "Exact eligibility condition candidate must satisfy (e.g. Must be a small farmer owning < 2 Ha)",
            "type": "eligibility",
            "value": "Threshold or null",
            "category": "farmer_status / land_ownership / land_size / income / age / residency / caste/category / occupation / other",
            "evidence": {
              "page_number": 1,
              "source_text": "Verbatim quote from document",
              "ocr_confidence": 95.0,
              "table_index": None,
              "row_index": None,
              "column_index": None,
              "cell_text": None
            },
            "semantic_confidence": 0.85,
            "review_required": False,
            "review_reasons": []
          }
        ],
        "exclusion_rules": [
          {
            "rule": "Exact disqualification condition (e.g. Government employees are excluded)",
            "type": "exclusion",
            "value": None,
            "category": "employment / income / beneficiary_status / other",
            "evidence": {
              "page_number": 1,
              "source_text": "Verbatim quote",
              "ocr_confidence": 90.0
            },
            "semantic_confidence": 0.85,
            "review_required": False,
            "review_reasons": []
          }
        ],
        "review_required": False,
        "review_reasons": []
    }

    user_prompt = f"""DOCUMENT CONTENT FOR EXTRACTION:
{doc_context}

TARGET JSON FORMAT SPECIFICATION:
{json.dumps(json_skeleton, indent=2)}

TASK:
Extract ONLY candidate eligibility rules (who qualifies) and exclusion rules (who is disqualified).
Return valid JSON matching the format above.

REMEMBER:
- Extract ONLY explicit candidate qualifications (eligibility) or disqualifications (exclusions).
- Statements about amendments, document status (e.g. 'no change in said notification' / 'ಸದರಿ ಅಧಿಸೂಚನೆಯಲ್ಲಿ ಯಾವುದೇ ಬದಲಾವಣೆ ಇರುವುದಿಲ್ಲ'), notifications, administrative handling, office dispatch, or procedural changes MUST BE IGNORED.
- DO NOT convert blank form fields (Name, Gender, Mobile, Aadhaar) into eligibility rules.
- If the document contains NO actual candidate qualification rules, return:
  "eligibility_rules": [], "exclusion_rules": []
- DO NOT hallucinate rules from outside knowledge.
"""

    # Step 4: Call LLM with JSON enforcement and retry
    raw_json = client.generate_json(
        prompt=user_prompt,
        system_prompt=SYSTEM_PROMPT,
        temperature=0.0,
        max_retries=max_retries,
    )

    # Step 5: Pydantic Validation
    try:
        extraction = SchemeExtraction.model_validate(raw_json)
    except Exception as val_err:
        logger.warning(f"Pydantic validation issue on initial extraction: {val_err}. Attempting partial recovery...")
        if isinstance(raw_json, dict) and "scheme_extraction" in raw_json:
            extraction = SchemeExtraction.model_validate(raw_json["scheme_extraction"])
        else:
            raise

    # Step 6: Post-extraction audit and quality enhancement
    enhanced_extraction = audit_and_enhance_extraction(
        extraction=extraction,
        doc_json=doc_json,
        model_name=active_model,
    )

    # Step 7: Save output
    save_extracted_rules(enhanced_extraction, filename, output_dir=output_dir)

    logger.info(
        f"Checkpoint 10 complete for {filename}: {enhanced_extraction.extraction_metadata.rule_count} rules, "
        f"{enhanced_extraction.extraction_metadata.review_required_count} review-flagged items."
    )
    return enhanced_extraction
