# Karnataka Scheme Knowledge Update Agent

An automated system to keep track of Karnataka government schemes and documents.

## Step 1: Environment Setup

This project uses Python with a virtual environment (`venv`).

### How to activate the virtual environment (Windows PowerShell)

```powershell
.\venv\Scripts\Activate.ps1
```

### How to run tests

```powershell
.\venv\Scripts\pytest.exe -v
```

## Step 2: PostgreSQL Setup

Initialize the database tables:

```powershell
.\venv\Scripts\python.exe scripts/setup_db.py
```

## Step 3: Source Registry

Seed initial official Karnataka sources:

```powershell
.\venv\Scripts\python.exe scripts/seed_sources.py
```

## Step 4: Website Discovery

Scan registered portals for scheme pages and document links:

```powershell
.\venv\Scripts\python.exe scripts/run_discovery.py
```

## Step 5: Document Discovery

Extract, classify, and filter scheme PDFs, guidelines, and Government Orders from discovered pages:

```powershell
.\venv\Scripts\python.exe scripts/run_document_discovery.py
```

## Step 6: Document Downloader

Download discovered scheme documents, verify SHA-256 fingerprints, and store metadata in PostgreSQL:

```powershell
.\venv\Scripts\python.exe scripts/run_download.py
```

## Step 7: Version Detection

Detect document versions, identify changes, and preserve historical scheme versions in PostgreSQL:

```powershell
.\venv\Scripts\python.exe scripts/run_versioning.py
```






