# Karnataka Scheme Knowledge Update Agent

## 1. Project Overview

This project is an AI-agent workflow that automatically keeps a knowledge base of Karnataka government scheme documents up to date.

The system focuses only on the knowledge acquisition and update workflow:

1. Open configured official Karnataka government websites.
2. Discover scheme pages and relevant documents.
3. Download new or changed documents.
4. Detect document versions and changes.
5. Process webpages and PDFs.
6. Extract text directly from normal PDFs.
7. Detect scanned/image pages and use OCR when required, including Kannada OCR.
8. Extract structured scheme and eligibility rules.
9. Compare new documents and rules with previous versions.
10. Update PostgreSQL with the latest version while preserving historical versions.
11. Record the complete update history.

This project does **not** include the end-user eligibility application or user-facing RAG assistant.

---

# 2. Main Goal

The goal is to replace manual scheme-data maintenance.

### Current manual approach

```text
Open government website
        ↓
Find scheme
        ↓
Find latest PDF
        ↓
Download PDF
        ↓
Read / scan PDF
        ↓
Extract information
        ↓
Manually update scheme data
        ↓
Reload database
```

### Target automated approach

```text
Official Karnataka website
        ↓
Discovery Agent
        ↓
Document discovery
        ↓
Download
        ↓
Version detection
        ↓
Document processing
        ↓
OCR when required
        ↓
Rule extraction
        ↓
Document/rule comparison
        ↓
Knowledge base update
        ↓
PostgreSQL
```

---

# 3. Project Scope

## Included

- Karnataka government scheme sources
- Official government webpages
- Official PDFs
- Government Orders
- Notifications
- Circulars
- Guidelines
- Scanned/image-based PDFs
- Kannada text and OCR
- English text
- Document versioning
- Rule extraction
- Document comparison
- Rule comparison
- PostgreSQL
- Agent/tool orchestration
- Update history and logging

## Not Included

- End-user eligibility checking
- User accounts
- Frontend
- Voice input/output
- Other Indian states
- Hindi support
- Model fine-tuning
- User-facing RAG
- Automatic web-wide searching without configured official sources

---

# 4. Core Architecture

```text
                    OFFICIAL KARNATAKA SOURCES
                              │
                              ▼
                    ┌─────────────────────┐
                    │   Discovery Agent   │
                    └──────────┬──────────┘
                               │
                               ▼
                    Scheme / Document URLs
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Document Downloader │
                    └──────────┬──────────┘
                               │
                               ▼
                    New / Existing Document
                               │
                               ▼
                    ┌─────────────────────┐
                    │ Version Detection   │
                    └──────────┬──────────┘
                               │
                         New version?
                         /           \
                       No             Yes
                       │               │
                     Stop              ▼
                              Document Processing
                                      │
                         ┌────────────┴────────────┐
                         │                         │
                  Text-based PDF             Scanned PDF
                         │                         │
                   PyMuPDF extraction             OCR
                         │                    Kannada/English
                         │                         │
                         └────────────┬────────────┘
                                      ▼
                              Clean document text
                                      │
                                      ▼
                            ┌──────────────────┐
                            │ Rule Extraction  │
                            │      Agent       │
                            └────────┬─────────┘
                                     │
                                     ▼
                            Structured Rules
                                     │
                                     ▼
                           Compare Old vs New
                                     │
                                     ▼
                         ┌──────────────────────┐
                         │ Knowledge Base       │
                         │ Update                │
                         └──────────┬───────────┘
                                    │
                                    ▼
                                PostgreSQL
                                    │
                                    ▼
                              Update History
```

---

# 5. Agent Design

The project should not use one large function that performs everything.

The agent should have small tools/functions and decide when to call them.

### Planned tools

```text
discover_sources()
discover_scheme_pages()
discover_documents()
download_document()
detect_document_version()
extract_pdf_text()
detect_scanned_pages()
run_ocr()
clean_document_text()
extract_rules()
compare_documents()
compare_rules()
update_knowledge_base()
record_update()
```

The agent orchestrates these tools.

The tools themselves should perform deterministic work whenever possible.

---

# 6. AI vs Python Responsibilities

A major design principle is:

> Use normal Python for deterministic processing and AI for tasks that require semantic understanding or decision-making.

## Python should handle

- HTTP requests
- Website parsing
- Link discovery
- File downloads
- File hashing
- PDF extraction
- OCR execution
- Database operations
- Version storage
- Exact comparisons
- Logging
- Validation

## LLM/AI should help with

- Understanding messy government document text
- Identifying document type when metadata is ambiguous
- Extracting structured scheme rules
- Understanding Kannada/English content when required
- Identifying semantic differences between old and new documents
- Agent decision-making and tool selection

The LLM should not be responsible for basic deterministic operations that Python can perform reliably.

---

# 7. Source Registry

Do not allow the agent to search the entire internet for government information.

Maintain a registry of official sources.

Example:

```text
source_registry

id
department
source_name
official_url
source_type
active
last_checked
last_successful_check
```

Example record:

```json
{
    "department": "Example Karnataka Department",
    "source_name": "Official Schemes Page",
    "official_url": "https://official-government-site.example/schemes",
    "source_type": "scheme_page",
    "active": true
}
```

The agent starts from these trusted sources.

---

# 8. Website and Document Discovery

A government website may contain:

- Scheme pages
- PDF guidelines
- Government Orders
- Notifications
- Circulars
- Application forms
- Old documents
- Supporting documents

The discovery system must identify which links are potentially relevant.

For every discovered document, store metadata such as:

```text
document_url
source_page_url
title
document_type
scheme_name
department
published_date
discovered_at
```

Do not assume that every PDF on a government website is a scheme policy document.

---

# 9. Document Download

When a relevant document is discovered:

1. Download it.
2. Verify that the download is valid.
3. Calculate a SHA-256 content hash.
4. Store document metadata.
5. Check whether the same document already exists.

If the hash is identical to the stored document:

```text
No content change
→ do not process again
```

If the hash is different:

```text
Possible update
→ process the document
```

---

# 10. Version Detection

Version detection should use multiple signals.

Possible signals:

- Document publication date
- Effective date
- Version number
- Government Order number
- Notification number
- Document title
- URL
- File hash
- Content differences
- Language/content changes

Do not rely only on the filename.

For example:

```text
scheme_guidelines.pdf
scheme_guidelines_latest.pdf
scheme_guidelines_2026.pdf
```

The filename alone is not enough to determine which document is authoritative.

---

# 11. Historical Version Preservation

A new document must **never replace or delete the old document**.

Suppose the system discovers:

```text
2025 Guidelines
    Income <= ₹2,00,000

2026 Guidelines
    Income <= ₹2,50,000

2027 Guidelines
    Income <= ₹3,00,000
```

The database should contain all three versions.

```text
scheme_versions

id | scheme | version | status
--------------------------------
1  | X      | 2025    | ARCHIVED
2  | X      | 2026    | ARCHIVED
3  | X      | 2027    | ACTIVE
```

The old eligibility rules remain available for comparison and auditing.

The update process therefore performs:

```text
ADD NEW VERSION
```

rather than:

```text
OVERWRITE OLD VERSION
```

This is essential for reliable version comparison.

---

# 12. Document Processing

The processor must support both normal and scanned PDFs.

## 12.1 Text-based PDF

If the PDF contains actual text:

```text
PDF
 ↓
PyMuPDF
 ↓
Extract Unicode text
 ↓
Clean text
```

PyMuPDF is the primary extraction tool.

This also works for a Kannada PDF when the Kannada characters are stored properly as Unicode text inside the PDF.

Example:

```python
import pymupdf

doc = pymupdf.open("kannada_scheme.pdf")

for page in doc:
    text = page.get_text()
    print(text)
```

Possible output:

```text
ಕರ್ನಾಟಕ ಸರ್ಕಾರ
ಯೋಜನೆಯ ಅರ್ಹತಾ ಮಾನದಂಡಗಳು...
```

No OCR is required in this case.

## 12.2 Scanned/image PDF

If the PDF contains images rather than actual text:

```text
PDF
 ↓
Detect page with little/no usable text
 ↓
Render page as image
 ↓
OCR
 ↓
Kannada/English text
 ↓
Clean text
```

OCR should be a fallback, not the default for every PDF.

## 12.3 Broken text encoding

A PDF may visually contain Kannada text but have an unusable internal text encoding.

Therefore:

```text
PyMuPDF extraction
        ↓
Is extracted text usable?
       / \
     YES  NO
      │    │
      │    ▼
      │   OCR
      │
      ▼
   Continue
```

The processor should retain the original document and the extracted/OCR text for debugging.

---

# 13. Kannada OCR

Some Karnataka government documents may contain Kannada text inside scanned images.

The pipeline should support:

```text
Kannada PDF/image
        ↓
Image extraction
        ↓
Kannada OCR
        ↓
Raw Kannada text
        ↓
Cleaning
        ↓
Rule extraction
```

OCR output should be treated as potentially imperfect.

The system should retain:

- Original document
- Extracted text
- OCR text where used
- Page number
- Source URL
- Processing status

This allows us to investigate extraction errors later.

---

# 14. Rule Extraction

After document processing, the LLM extracts structured information.

Example:

```json
{
    "scheme_name": "Example Scheme",
    "eligibility": {
        "minimum_age": 18,
        "maximum_age": 35,
        "annual_income_max": 300000,
        "state": "Karnataka",
        "occupation": ["farmer"]
    },
    "benefits": "...",
    "required_documents": [
        "Aadhaar",
        "Income Certificate"
    ],
    "application_information": "...",
    "effective_from": "2026-04-01"
}
```

The exact schema should evolve based on the real Karnataka schemes processed by the system.

---

# 15. Structured Output Validation

Never directly trust raw LLM JSON.

Use Pydantic to validate the extracted structure.

```text
Government document
        ↓
LLM
        ↓
Structured JSON
        ↓
Pydantic validation
        ↓
Valid structured data
```

If validation fails:

```text
Log error
→ retry / repair extraction
→ flag for review if still invalid
```

The original document remains unchanged.

---

# 16. Document Comparison

Compare the newly downloaded document with the previous version.

Compare:

- Text
- Sections
- Dates
- Government Order numbers
- Eligibility statements
- Benefits
- Income limits
- Age limits
- Required documents
- Application procedure

There should be two levels of comparison.

## Level 1 — Deterministic comparison

Use Python for:

- File hash
- Metadata comparison
- Text differences
- Exact values

## Level 2 — Semantic comparison

Use an LLM when wording changes but the meaning may or may not have changed.

Example:

```text
OLD:
Annual income should not exceed Rs. 2,50,000.

NEW:
Annual family income must be below Rs. 3,00,000.
```

The system should identify this as a meaningful rule change.

---

# 17. Rule Comparison

Structured rules should also be compared directly.

Example:

```text
OLD
annual_income_max = 250000

NEW
annual_income_max = 300000
```

Result:

```json
{
    "field": "annual_income_max",
    "old_value": 250000,
    "new_value": 300000,
    "change_type": "modified"
}
```

Structured comparison should be preferred over relying only on an LLM-generated change summary.

---

# 18. Knowledge Base

For the current update-agent project, **embeddings are not required for the core workflow**.

The primary knowledge store is PostgreSQL.

Recommended tables:

```text
source_registry
schemes
documents
scheme_versions
eligibility_rules
update_logs
```

A simplified relationship:

```text
source_registry
      │
      ▼
   schemes
      │
      ▼
scheme_versions
      │
      └──────────► eligibility_rules
```

## Optional future component: pgvector

pgvector can be added later if the project is extended with RAG or semantic document retrieval.

For example:

```text
Document chunks
      ↓
Embeddings
      ↓
pgvector
      ↓
Semantic search
```

The current document-update pipeline does not depend on embeddings.

---

# 19. PostgreSQL Version Model

A recommended structure is:

```text
schemes
    id
    slug
    name
    department
    state

scheme_versions
    id
    scheme_id
    version_label
    document_id
    published_date
    effective_from
    effective_until
    status
    extracted_text
    created_at

documents
    id
    source_url
    source_page_url
    file_hash
    title
    document_type
    downloaded_at

eligibility_rules
    id
    scheme_version_id
    rule_data

update_logs
    id
    scheme_id
    old_version_id
    new_version_id
    changes
    detected_at
    status
```

The exact schema can be refined once we inspect the first real Karnataka sources.

---

# 20. Knowledge Base Update

When a new valid version is detected:

```text
New document
      ↓
Process
      ↓
Extract rules
      ↓
Validate
      ↓
Compare
      ↓
Create new version
      ↓
Store document
      ↓
Store rules
      ↓
Record update
```

If pgvector is later enabled for RAG:

```text
Processed document
      ↓
Chunk
      ↓
Generate embeddings
      ↓
Store in pgvector
```

The previous version remains unchanged.

---

# 21. Update Log

Every update should produce an audit record.

Example:

```text
Scheme:
Example Scheme

Previous version:
2026

New version:
2027

Detected changes:
- Income limit: ₹2,50,000 → ₹3,00,000
- Maximum age: 35 → 40

Source:
Official government document

Detected at:
2027-04-05

Status:
Updated
```

This makes the system easier to debug and demonstrate.

---

# 22. Agent Orchestration

The final system will use an AI agent to orchestrate the tools.

The agent should not itself download files, parse PDFs, or modify the database through free-form reasoning.

Instead, it calls controlled tools.

Example:

```text
Agent
  │
  ├── discover_sources()
  │
  ├── discover_documents()
  │
  ├── download_document()
  │
  ├── detect_document_version()
  │
  ├── process_document()
  │
  ├── run_ocr()              ← only when required
  │
  ├── extract_rules()
  │
  ├── compare_documents()
  │
  ├── compare_rules()
  │
  └── update_knowledge_base()
```

This gives us a real tool-using agent rather than simply putting an LLM in front of a database.

---

# 23. Possible Jev Integration

Jev can be evaluated as the **decision/routing layer** of the agent workflow.

The basic workflow should first work with a normal agent loop.

Later, Jev can potentially be used to decide which tool should be called based on the current state.

Example:

```text
PDF downloaded
      ↓
Jev / decision model
      ↓
Text extraction failed
      ↓
Decision: run OCR
```

Then:

```text
OCR completed
      ↓
Decision
      ↓
extract_rules()
```

Then:

```text
Rules extracted
      ↓
Decision
      ↓
compare_rules()
```

Jev should therefore be treated as an experimental orchestration component, not a dependency of the first implementation.

The project can later compare:

```text
Normal LLM agent
        VS
LLM + Jev decision layer
```

using metrics such as:

- Correct tool selection
- Number of unnecessary tool calls
- Failed tool calls
- Processing time
- Token/API cost
- Successful end-to-end updates

---

# 24. Folder Structure

Keep the code simple and separated by responsibility.

```text
scheme-update-agent/
│
├── .env
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
│
├── app/
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── agent.py
│   ├── discovery.py
│   ├── downloader.py
│   ├── versioning.py
│   ├── document_processor.py
│   ├── ocr.py
│   ├── extraction.py
│   ├── comparison.py
│   └── knowledge_base.py
│
├── scripts/
│   ├── setup_db.py
│   └── run_update.py
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── logs/
│
└── tests/
    ├── test_discovery.py
    ├── test_downloader.py
    ├── test_versioning.py
    ├── test_document_processor.py
    ├── test_extraction.py
    └── test_comparison.py
```

The structure can be adjusted as the project grows.

---

# 25. Environment Setup

The project will use a Python virtual environment.

### Windows

From the project folder:

```bash
python -m venv venv
```

Activate it:

```bash
venv\Scripts\activate
```

The terminal should show something similar to:

```text
(venv) C:\...\scheme-update-agent>
```

Upgrade pip:

```bash
python -m pip install --upgrade pip
```

All project packages should be installed inside this environment.

---

# 26. Initial Python Dependencies

Start with only the packages required for the first checkpoints.

Initial candidates:

```text
requests
beautifulsoup4
pymupdf
psycopg[binary]
pydantic
python-dotenv
pytest
```

Additional packages for OCR, LLMs, agent orchestration, and embeddings should be added only when their corresponding checkpoint is reached.

Do not install a large collection of libraries at the beginning.

---

# 27. Environment Variables

Create `.env`:

```text
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/scheme_agent

LLM_API_KEY=your-api-key

LLM_MODEL=your-model-name
```

If embeddings are added later:

```text
EMBEDDING_MODEL=your-embedding-model
```

Never commit `.env`.

Create `.env.example` with placeholder values.

---

# 28. PostgreSQL Setup

PostgreSQL is already installed.

Create a dedicated database:

```sql
CREATE DATABASE scheme_agent;
```

For the current update-agent workflow, PostgreSQL itself is sufficient.

If pgvector is needed later for RAG:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

There is no need to force pgvector into the first version of the project.

---

# 29. Development Checkpoints

## CP1: Environment and Project Skeleton

Create the project folder, Python virtual environment, configuration, logging, and basic project structure.

## CP2: PostgreSQL Foundation

Connect Python to PostgreSQL and create the initial source, scheme, document, version, rules, and update-log tables.

## CP3: Source Registry

Create the database structure and Python functions for registering official Karnataka government scheme sources.

## CP4: Website Discovery

Build the first working crawler that opens a registered government webpage and discovers relevant scheme and document links.

## CP5: Document Discovery

Identify relevant PDFs, notifications, circulars, guidelines, and other candidate scheme documents from discovered pages.

## CP6: Document Download

Download discovered documents safely, calculate hashes, validate files, and store their metadata.

## CP7: Version Detection

Determine whether a discovered document is unchanged, new, or a potential new version using hashes, metadata, dates, and content.

## CP8: PDF Text Processing

Extract Unicode text from normal PDFs using PyMuPDF and validate whether the extracted text is usable.

## CP9: OCR Fallback

Detect scanned or unusable PDF pages and process them with Kannada/English OCR while preserving page information.

## CP10: Rule Extraction

Use an LLM to convert processed government documents into structured, Pydantic-validated scheme rules.

## CP11: Document Comparison

Compare previous and new document versions using deterministic text comparison and semantic comparison where necessary.

## CP12: Rule Comparison

Compare structured rules and identify additions, removals, and modifications.

## CP13: Knowledge Base Update

Store new documents, versions, rules, and update history in PostgreSQL without overwriting previous versions.

## CP14: Agent Orchestration

Build the AI agent that selects and calls the discovery, download, processing, extraction, comparison, and update tools in the correct sequence.

## CP15: End-to-End Update Run

Run the complete pipeline against a real Karnataka government source and produce a complete update report.

## CP16: Testing and Evaluation

Test discovery, downloading, PDF extraction, OCR, rule extraction, version detection, comparison, and database updates using real and controlled documents.

## CP17: Scheduled Execution

Run the update workflow periodically and record successful checks, detected changes, failures, and processing history.

## CP18: Jev Experiment

Evaluate Jev as an optional decision/routing layer and compare its tool-selection performance against the baseline agent.

## CP19: Documentation and Deployment

Document the architecture, tools, agent workflow, database design, evaluation results, limitations, and deployment process.

---

# 30. Agent Workflow

The final agent should be able to perform a workflow similar to:

```text
START
  │
  ▼
Load registered sources
  │
  ▼
Open source
  │
  ▼
Discover scheme/document links
  │
  ▼
Are there new documents?
  │
 ┌┴─────────────┐
No              Yes
 │                │
STOP              ▼
          Download document
                │
                ▼
          Detect version
                │
                ▼
          Process document
                │
                ▼
        Is text usable?
           /          \
         YES           NO
          │             │
          │             ▼
          │           OCR
          │             │
          └──────┬──────┘
                 ▼
          Extract structured rules
                 │
                 ▼
          Compare with previous
                 │
                 ▼
          Changes detected?
             /        \
           No          Yes
           │            │
         Log       Create version
                        │
                        ▼
                  Update knowledge base
                        │
                        ▼
                   Record update
                        │
                        ▼
                       END
```

---

# 31. Important Engineering Rules

1. Keep functions small and focused.
2. Prefer normal Python for deterministic operations.
3. Use AI where semantic understanding is actually required.
4. Validate all LLM structured output with Pydantic.
5. Never overwrite historical documents or versions.
6. Store the original source URL for every extracted document.
7. Store page numbers where possible.
8. Calculate document hashes to avoid unnecessary processing.
9. Log every major pipeline step.
10. Do not silently ignore failures.
11. Keep raw documents separate from processed documents.
12. Keep API keys and database credentials in `.env`.
13. Do not allow the agent to invent source URLs.
14. Do not treat OCR output as automatically correct.
15. Do not automatically activate ambiguous rule changes without validation.
16. Keep the first implementation limited to a small number of real Karnataka sources.
17. Add libraries only when a checkpoint actually requires them.
18. Build and test one checkpoint at a time.
19. Do not add embeddings unless semantic retrieval/RAG requires them.
20. Preserve every previous scheme version.

---

# 32. First Implementation Target

Do not start by building the complete agent.

The first real milestone should be:

```text
Official Karnataka webpage
        ↓
Python opens webpage
        ↓
Finds relevant PDF
        ↓
Downloads PDF
        ↓
Extracts text using PyMuPDF
        ↓
Checks whether extracted text is usable
        ↓
Prints useful document information
```

Once this works reliably, add:

```text
Version detection
        ↓
OCR fallback
        ↓
Rule extraction
        ↓
Document comparison
        ↓
Rule comparison
        ↓
Database update
        ↓
Agent orchestration
        ↓
Optional Jev experiment
```

This approach lets us identify exactly which component fails instead of debugging one large agent.

---

# 33. Definition of Done

The project is considered complete when the system can take a registered official Karnataka government source and automatically:

```text
discover
    ↓
download
    ↓
detect version
    ↓
process
    ↓
OCR when necessary
    ↓
extract rules
    ↓
compare
    ↓
store new version
    ↓
record the update
```

without requiring the developer to manually search for and update scheme data.

Historical scheme versions must remain available, and every extracted rule must be traceable to its source document.
