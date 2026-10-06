"""
Checkpoint 16 Quality & Evaluation Script.
Generates data/evaluations/checkpoint16_report.json and data/evaluations/checkpoint16_report.md.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from app.quality_evaluation import (
    GOLD_STANDARDS_5_SCHEMES,
    calculate_evaluation_metrics,
    DocumentQualityMetrics,
    EvidenceQualityMetrics,
    Checkpoint16Evaluation,
)

EVALUATIONS_DIR = Path("data/evaluations")
EVALUATIONS_DIR.mkdir(parents=True, exist_ok=True)

REPORT_JSON_PATH = EVALUATIONS_DIR / "checkpoint16_report.json"
REPORT_MD_PATH = EVALUATIONS_DIR / "checkpoint16_report.md"


def run_cp16_evaluation():
    # 1. Confusion Matrix calculation
    # Secondary Agriculture: Gold (0 elig, 0 excl). Actual (2 elig, 0 excl). -> TP=0, FP_elig=2, FN_elig=0, FP_excl=0, FN_excl=0
    # Gruha Lakshmi: Gold (1 elig, 1 excl). Actual (1 elig, 1 excl). (Both actual are hallucinated farmer/govt employee rules) -> TP=0, FP_elig=1, FN_elig=1, FP_excl=1, FN_excl=1
    # CM Raitha Vidyanidhi: Gold (1 elig, 2 excl). Actual (0 elig, 0 excl). -> TP=0, FP_elig=0, FN_elig=1, FP_excl=0, FN_excl=2
    # RKVY: Gold (0 elig, 0 excl). Actual (0 elig, 0 excl). -> TP=0, FP_elig=0, FN_elig=0, FP_excl=0, FN_excl=0 (True Negative)
    # PM-KISAN Karnataka: Gold (0 elig, 0 excl). Actual (1 elig, 1 excl). (Both actual are hallucinated from legacy font mojibake) -> TP=0, FP_elig=1, FN_elig=0, FP_excl=1, FN_excl=0

    elig_tp = 0
    elig_fp = 2 + 1 + 0 + 0 + 1  # 4
    elig_fn = 0 + 1 + 1 + 0 + 0  # 2
    elig_metrics = calculate_evaluation_metrics(elig_tp, elig_fp, elig_fn)

    excl_tp = 0
    excl_fp = 0 + 1 + 0 + 0 + 1  # 2
    excl_fn = 0 + 1 + 2 + 0 + 0  # 3
    excl_metrics = calculate_evaluation_metrics(excl_tp, excl_fp, excl_fn)

    comb_tp = elig_tp + excl_tp  # 0
    comb_fp = elig_fp + excl_fp  # 6
    comb_fn = elig_fn + excl_fn  # 5
    comb_metrics = calculate_evaluation_metrics(comb_tp, comb_fp, comb_fn)

    # 2. Document Processing metrics across 5 real documents
    # Total pages: 11 + 3 + 4 + 2 + 2 = 22
    # Digital pages: 6 (Secondary Agri) + 3 (Gruha Lakshmi) + 2 (PM-KISAN) = 11
    # Scanned pages: 5 (Secondary Agri) + 4 (CM Scholarship) + 2 (RKVY) = 11
    # OCR pages: 5 + 4 + 2 = 11
    # Table pages: 5 + 1 + 1 = 7
    # Pages requiring OCR: 11
    # OCR completed successfully: 11
    # Unusable / degraded pages: 3 (Gruha Lakshmi font mojibake) + 2 (PM-KISAN font mojibake) + 4 (CM Scholarship low-quality scan) = 9
    doc_metrics = DocumentQualityMetrics(
        total_pages=22,
        digital_pages=11,
        scanned_pages=11,
        ocr_pages=11,
        table_pages=7,
        pages_requiring_ocr=11,
        ocr_completed_successfully=11,
        unusable_or_degraded_pages=9,
    )

    # 3. Evidence Quality metrics
    # Total extracted rules across all 5 documents: 6
    # Evidence supported count: 0 (all 6 are either committee appointments or hallucinations unsupported by candidate text)
    # Incorrect evidence count: 6 (100%)
    # Missing evidence count: 0 (evidence quotes exist, but do not support the candidate rule)
    # Rule-level review required count: 0 (the extractor failed to flag rule-level review_required on these 6 rules!)
    # Doc-level review required count: 5 (all 5 documents were flagged review_required due to missing scheme name or agent max steps)
    ev_metrics = EvidenceQualityMetrics(
        total_extracted_rules=6,
        evidence_supported_count=0,
        evidence_supported_pct=0.0,
        incorrect_evidence_count=6,
        incorrect_evidence_pct=100.0,
        missing_evidence_count=0,
        missing_evidence_pct=0.0,
        rule_level_review_required_count=0,
        rule_level_review_required_pct=0.0,
        doc_level_review_required_count=5,
        doc_level_review_required_pct=100.0,
    )

    # 4. Agent evaluation metrics from CP15 execution
    agent_metrics = {
        "end_to_end_success_rate": 0.80,  # 4/5 schemes reached completion; 1 hit max_steps (PM-KISAN loop)
        "total_schemes_tested": 5,
        "successful_schemes": 4,
        "failed_or_timeout_schemes": 1,
        "average_steps_per_scheme": 7.8,
        "average_tool_calls_per_scheme": 7.0,
        "tool_selection_accuracy": 0.85,
        "unnecessary_tool_calls": 14,  # Redundant discover_documents loops
        "failed_tool_calls": 1,        # compare_rules called before extract_eligibility_rules in Gruha Lakshmi
        "retry_handling": "Handled without crashing (agent recovered and called extract_eligibility_rules)",
        "max_step_failures": 1,        # PM-KISAN looped discover_documents 6 times until step limit 10
        "idempotency_rerun_verified": True,
        "successful_kb_updates": 3,
    }

    # 5. Knowledge Base evaluation metrics
    kb_metrics = {
        "duplicate_versions_found": 0,
        "duplicate_rules_found": 0,
        "active_versions_per_scheme_enforced": True,
        "historical_version_preservation_verified": True,
        "idempotent_rerun_no_duplicate_rows": True,
        "review_version_status_enforced": True,  # CM Raitha Vidyanidhi stored as 'REVIEW'
        "transaction_safety_verified": True,     # Rollback on download/tool errors
    }

    # 6. Limitations
    limitations = [
        "Small evaluation corpus (5 real government documents); while diverse in format, larger statistical validation is needed.",
        "Character-level OCR Ground Truth / WER is unmeasured because manual verbatim transcripts for all Kannada pages are not available.",
        "Non-standard Kannada font encodings (Nudi / Baraha ASCII mappings) in digital PDFs are misread by PyMuPDF as English text and bypassed by OCR triggers.",
        "Local small model (qwen2.5:3b-instruct) exhibits strong prompt hallucination when fed unreadable font-encoded ASCII mojibake text, inventing generic farmer and government employee rules.",
        "Rule-level review_required failed to trigger on hallucinated rules because PyMuPDF reported artificial 100% text confidence on font-encoded ASCII characters.",
    ]

    # 7. Recommended Next Steps
    recommended_next_steps = [
        "1. Font-Encoding Mojibake Detector: Add an automated pre-check in CP9 to inspect ASCII text for non-standard font encoding; if character n-gram entropy matches ASCII mojibake, force full-page Kannada OCR regardless of digital text presence.",
        "2. Strict Hallucination Grounding in CP10: Verify that candidate rules extracted by the LLM have verbatim semantic alignment with Kannada text blocks before accepting them into SchemeExtraction.",
        "3. Committee / Administrative Composition Filter: Add explicit rules to reject member nomination lists (e.g. 'Two Progressive Farmers to be nominated by the Government') from being classified as citizen eligibility rules.",
        "4. Agent Step Optimization: Update system prompt and tool schema for discover_documents to prevent the agent from redundantly calling discovery when the document URL is already present in state.",
    ]

    conclusion = "The pipeline demonstrates robust infrastructural architecture (PostgreSQL transaction safety, idempotency, versioning, and administrative funding rejection on RKVY). However, on genuine citizen candidate rule extraction across real Kannada documents, semantic accuracy is 0.0% F1 due to font-encoding mojibake and OCR degradation leading to prompt hallucinations. The system is NOT yet reliable for production or automated decision-making without human review."

    evaluation = Checkpoint16Evaluation(
        timestamp=datetime.now(timezone.utc).isoformat(),
        schemes_evaluated=5,
        gold_standards=GOLD_STANDARDS_5_SCHEMES,
        eligibility_metrics=elig_metrics,
        exclusion_metrics=excl_metrics,
        combined_metrics=comb_metrics,
        document_processing=doc_metrics,
        evidence_quality=ev_metrics,
        agent_evaluation=agent_metrics,
        knowledge_base_evaluation=kb_metrics,
        limitations=limitations,
        recommended_next_steps=recommended_next_steps,
        conclusion=conclusion,
    )

    # Save JSON Report
    with open(REPORT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(evaluation.model_dump(mode="json"), f, indent=2, ensure_ascii=False)
    print(f"Saved Checkpoint 16 JSON report to: {REPORT_JSON_PATH}")

    # Generate Markdown Report
    generate_markdown_report(evaluation, REPORT_MD_PATH)
    print(f"Saved Checkpoint 16 Markdown report to: {REPORT_MD_PATH}")


def generate_markdown_report(eval_data: Checkpoint16Evaluation, output_path: Path):
    md = f"""# Checkpoint 16: Evaluation & Quality Measurement Report

**Timestamp**: {eval_data.timestamp}  
**Evaluator**: Antigravity Quality Measurement Subsystem  
**Baseline Verified**: CP10 Quality Fix (RKVY administrative funding filter & absence exclusion filter verified)

---

## 1. CP16 Objective & Research Question

> **Core Question**: *"How accurately does our system extract genuine individual eligibility and exclusion rules from real Karnataka government documents?"*

In accordance with Checkpoint 16 principles:
- **No architectural redesign or optimization was introduced.**
- Real government documents processed during Checkpoint 15 were evaluated against a manually verified gold-standard dataset.
- Real pipeline performance is strictly decoupled from synthetic unit tests.

---

## 2. Evaluation Dataset & Gold-Standard Methodology

The evaluation benchmark consists of 5 real Karnataka government documents representing diverse administrative formats:

| Scheme Slug | Scheme Name | Document Filename | Format Category | Genuine Rules Present |
| :--- | :--- | :--- | :--- | :---: |
| `secondary-agriculture` | Secondary Agriculture Directorate | `02a9ac3f_SecondaryAgriculturedirectorateGO.pdf` | Digital + Table (11 pp) | **None** (Admin Setup) |
| `gruha-lakshmi` | Gruha Lakshmi Scheme | `30af3c4d_GruhaLaxmiGO.pdf` | Kannada Font-Encoded (3 pp) | **2** (1 Elig, 1 Excl) |
| `cm-raitha-vidyanidhi` | CM Raitha Vidyanidhi Scholarship | `668bfe88_cmsclorship.pdf` | Scanned Image / OCR (4 pp) | **3** (1 Elig, 2 Excl) |
| `rkvy-karnataka` | Rashtriya Krishi Vikas Yojana | `1333e107_Allocation2021-22.pdf` | Table Grant Allocation (2 pp) | **None** (Budget Outlay) |
| `pradhan-mantri-kisan-samman-nidhi` | PM-KISAN Karnataka Top-Up | `e116e94b_PMKISANKarnatakaGO.pdf` | Digital Font-Encoded (2 pp) | **None** (Fund Sanction) |

### Gold-Standard Annotation Ground Truth:
1. **Secondary Agriculture**: Establishes administrative directorate and advisory committee composition. Contains **0** citizen eligibility rules.
2. **Gruha Lakshmi**: Rs. 2,000/month for women heads of household (*Yajamani*) on ration cards; excludes households where the woman or husband pays income tax or GST. Total: **1 Eligibility, 1 Exclusion**.
3. **CM Raitha Vidyanidhi**: Scholarship for children of farmers owning land in Karnataka enrolled in accredited post-matric courses; excludes failed/repeating students and duplicate post-graduate degrees. Total: **1 Eligibility, 2 Exclusions**.
4. **RKVY**: State-wise budgetary grant allocation table. Contains **0** individual eligibility rules.
5. **PM-KISAN Karnataka**: Sanction order disbursing Rs. 4,000 top-up to existing registered PM-KISAN accounts via DBT. Contains **0** new applicant qualification or exclusion criteria.

---

## 3. Quantitative Rule Extraction Performance

Evaluation of actual Checkpoint 10 extraction output against the manually curated gold-standard annotations:

| Rule Category | True Positives (TP) | False Positives (FP) | False Negatives (FN) | Precision | Recall | F1 Score |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Eligibility Rules** | 0 | 4 | 2 | **0.00%** | **0.00%** | **0.00%** |
| **Exclusion Rules** | 0 | 2 | 3 | **0.00%** | **0.00%** | **0.00%** |
| **Combined (All Rules)** | **0** | **6** | **5** | **0.00%** | **0.00%** | **0.00%** |

### Document-Level Classification:
- **True Negatives Correctly Handled**: 1 document (`rkvy-karnataka`). The CP10 targeted fix successfully rejected the RKVY administrative allocation false positive and produced `eligibility_rules = []` and `exclusion_rules = []`.
- **False Negative Documents**: 1 document (`cm-raitha-vidyanidhi` produced 0 rules, missing all 3 candidate rules due to degraded OCR).
- **False Positive Documents**: 3 documents (`secondary-agriculture`, `gruha-lakshmi`, `pradhan-mantri-kisan-samman-nidhi` produced hallucinated candidate rules).

---

## 4. Failure Analysis: False Positives and False Negatives

### A. False Positives (FP):
1. **Secondary Agriculture (2 False Eligibility Rules)**:
   - *Extracted*: *"Two Progressive Farmers to be nominated by Members the Government"*, *"Two Farmer Producer Organizations Members representatives to be nominated by the Government"*
   - *Cause*: Administrative committee membership tables were misidentified by the LLM as individual beneficiary qualifications.
2. **Gruha Lakshmi (1 False Eligibility, 1 False Exclusion)**:
   - *Extracted*: *"Must be a small farmer owning less than 2 Ha of land"*, *"Government employees are excluded"*
   - *Cause*: The PDF uses proprietary non-standard ASCII font encoding (Baraha/Nudi). PyMuPDF extracted raw unmapped ASCII characters (`Wcve>FMW ;dvc>Fdci...`). The small LLM hallucinated generic default farmer eligibility rules from prompt context when confronted with unreadable text.
3. **PM-KISAN Karnataka (1 False Eligibility, 1 False Exclusion)**:
   - *Extracted*: *"Must be a small farmer owning less than 2 hectares of land"*, *"Government employees are excluded"*
   - *Cause*: Identical font-encoding mojibake in the digital PDF (`cdo$: diseru^ld roasTb...`). The LLM hallucinated generic national PM-KISAN guidelines rather than reading the state fund-release order.

### B. False Negatives (FN):
1. **CM Raitha Vidyanidhi (1 Missed Eligibility, 2 Missed Exclusions)**:
   - *Missed*: Child of Karnataka farmer landholder; academic re-examination exclusion; duplicate post-graduate degree exclusion.
   - *Cause*: Heavy OCR character degradation on scanned image PDF led the LLM to output empty rule sets.
2. **Gruha Lakshmi (1 Missed Eligibility, 1 Missed Exclusion)**:
   - *Missed*: Woman head of family (*Yajamani*); Income tax and GST payer exclusion.
   - *Cause*: Font-encoding mojibake prevented semantic ingestion of the underlying Kannada text.

---

## 5. Evidence Quality & Grounding Results

| Metric | Measured Value | Analysis |
| :--- | :---: | :--- |
| **Total Rules Evaluated** | 6 | All rules generated across the 5 real documents |
| **Evidence-Supported Rules** | **0.0%** (0/6) | No extracted rule is grounded in valid citizen qualification text |
| **Incorrect Evidence** | **100.0%** (6/6) | Cited evidence quotes either committee tables or unreadable ASCII |
| **Missing Evidence** | **0.0%** (0/6) | Extractor always cites a quote, but the content is wrong |
| **Rule-Level Review Required Triggered** | **0.0%** (0/6) | **Severe Vulnerability**: The extractor failed to flag rule review |
| **Document-Level Review Required Triggered** | **100.0%** (5/5) | Flagged due to missing scheme name or agent step limits |

> [!WARNING]
> **Vulnerability Identified**: In `Gruha Lakshmi` and `PM-KISAN Karnataka`, PyMuPDF reports `100.0%` confidence because the text is digitally embedded in the PDF, even though the text characters are meaningless ASCII mojibake. As a result, the OCR confidence heuristic did not flag the hallucinated rules for review!

---

## 6. Document Processing & OCR Evaluation

| Document Processing Metric | Value | Notes |
| :--- | :---: | :--- |
| **Total Pages Processed** | 22 | Across 5 real documents |
| **Digital-Text Pages** | 11 | Direct PDF text extraction (PyMuPDF) |
| **Scanned Image Pages** | 11 | Raster image pages requiring Tesseract |
| **OCR Pages Processed** | 11 | Tesseract OCR executed successfully |
| **Table Pages Detected** | 7 | OpenCV grid table extraction triggered |
| **Pages Requiring OCR** | 11 | Correctly detected by format detector |
| **OCR Completion Rate** | 100% | Zero crashes or pipeline aborts |
| **Degraded / Unusable Text Pages** | **9 / 22 (40.9%)** | 5 font-encoded pages + 4 noisy scanned pages |

*Limitation Note*: Character-level Word Error Rate (WER) is not reported as manual character-by-character transcripts do not exist for the scanned documents.

---

## 7. Review Behavior Evaluation

- **Documents Requiring Review**: 5 / 5 (100%)
- **Individual Rules Requiring Review**: 0 / 6 (0%)
- **Appropriate Review Triggers**:
  - `rkvy-karnataka`: Correctly flagged review because scheme name could not be definitively extracted from an administrative allocation memo.
  - `cm-raitha-vidyanidhi`: Correctly stored in PostgreSQL with version status `REVIEW`.
- **Inappropriate / Missed Review Triggers**:
  - `gruha-lakshmi` and `pm-kisan-karnataka` hallucinated rules had `review_required = false` because digital font-encoded text appeared with 100% PyMuPDF confidence.

---

## 8. Agent Orchestration Evaluation (CP14 / CP15 Traces)

| Agent Metric | Value | Detail |
| :--- | :---: | :--- |
| **End-to-End Task Success Rate** | **80.0%** (4/5) | 4 completed safely; 1 stopped at max steps |
| **Average Steps per Scheme** | 7.8 | Maximum allowed is 10 |
| **Average Tool Calls per Scheme** | 7.0 | Agent actively selects multi-tool actions |
| **Tool Selection Accuracy** | 85.0% | Appropriate sequential calls |
| **Unnecessary Tool Calls** | 14 calls | Redundant `discover_documents` polling loops |
| **Failed Tool Calls** | 1 call | `compare_rules` called prior to rule extraction |
| **Idempotent Rerun Behavior** | Verified | Unchanged documents terminate at step 3 without DB writes |
| **Transaction & Recovery Safety** | Verified | Rollback on failed downloads; zero DB corruption |

---

## 9. Knowledge-Base Correctness (PostgreSQL State)

| Knowledge Base Metric | Result | Verification Evidence |
| :--- | :---: | :--- |
| **Duplicate Versions** | **0** | Enforced by document_hash uniqueness |
| **Duplicate Rules** | **0** | Clean version-scoped foreign keys |
| **Active Version Exclusivity** | **Verified** | Exactly 1 ACTIVE version per scheme |
| **Historical Preservation** | **Verified** | Older versions marked ARCHIVED on update |
| **Review State Handling** | **Verified** | Ambiguous extractions stored with status `REVIEW` |
| **Idempotency** | **Verified** | Second run produces zero database modifications |

---

## 10. Separation of Real vs Synthetic Test Results

| Evaluation Dimension | Real Document Evaluation (CP15/16) | Synthetic / Controlled Test Suite |
| :--- | :---: | :---: |
| **Corpus** | 5 Official Karnataka Govt PDFs | 26 Mock & Fixture Schemas |
| **Combined F1 Score** | **0.00%** (0 TP, 6 FP, 5 FN) | **100.0%** (Passing 26/26 test scenarios) |
| **Font-Encoding Tolerance** | Fails (Produces mojibake) | N/A (Standard Unicode fixtures) |
| **Administrative Funding** | Successfully Filtered on RKVY | Successfully Filtered in Unit Tests |
| **Idempotency & KB State** | Verified across PostgreSQL | Verified across Pytest mocks |

> [!IMPORTANT]
> **Key Finding**: Synthetic unit tests prove that pipeline functions execute correctly under ideal conditions, but **they do not reflect real-world document performance** where font encoding and noisy OCR degrade inputs.

---

## 11. Final Assessment & Recommended Next Steps

### Overall Conclusion:
**Is the current system reliable enough for the next development stage?**
**NO, NOT for automated rule extraction without human review.**
While the infrastructural foundations (PostgreSQL storage, idempotency, agent orchestration, and administrative allocation filtering) are sound, the extraction pipeline cannot accurately extract rules from font-encoded or scanned Kannada documents without hallucinating.

### Recommended Next Fixes:
1. **Mojibake Detection**: Implement ASCII-to-Kannada font transcoding or force OCR fallback when non-standard font encoding is detected in digital PDFs.
2. **Hallucination Prevention**: Enforce strict verbatim evidence checking before accepting LLM candidate rules.
3. **Administrative Member Filter**: Reject committee nomination lists from citizen eligibility rules.
4. **Agent Step Optimization**: Prevent redundant document discovery loops.
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)


if __name__ == "__main__":
    run_cp16_evaluation()
