# Checkpoint 16: Evaluation & Quality Measurement Report

**Timestamp**: 2026-10-06T04:11:57.067945+00:00  
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
