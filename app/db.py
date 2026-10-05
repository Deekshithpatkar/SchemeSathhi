"""
Database connection and initialization module.
Uses psycopg to connect to PostgreSQL and create the core tables.
"""

import psycopg
from app.config import DATABASE_URL, setup_logger

logger = setup_logger("db")

# SQL script to create the core knowledge base tables if they do not already exist
CREATE_TABLES_SQL = """
-- 1. Official sources registry
CREATE TABLE IF NOT EXISTS source_registry (
    id SERIAL PRIMARY KEY,
    department TEXT,
    source_name TEXT NOT NULL,
    official_url TEXT NOT NULL UNIQUE,
    source_type TEXT DEFAULT 'scheme_page',
    active BOOLEAN DEFAULT TRUE,
    last_checked TIMESTAMP WITH TIME ZONE,
    last_successful_check TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. Master schemes table
CREATE TABLE IF NOT EXISTS schemes (
    id SERIAL PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    department TEXT,
    state TEXT DEFAULT 'Karnataka',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. Discovered documents (PDFs, guidelines, etc.)
CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    source_url TEXT NOT NULL,
    source_page_url TEXT,
    file_hash TEXT NOT NULL,
    file_path TEXT,
    title TEXT,
    document_type TEXT,
    downloaded_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. Historical and active scheme versions
CREATE TABLE IF NOT EXISTS scheme_versions (
    id SERIAL PRIMARY KEY,
    scheme_id INTEGER NOT NULL REFERENCES schemes(id) ON DELETE CASCADE,
    version_label TEXT NOT NULL,
    document_id INTEGER REFERENCES documents(id) ON DELETE SET NULL,
    document_hash TEXT,
    document_date DATE,
    source_url TEXT,
    published_date DATE,
    effective_from DATE,
    effective_until DATE,
    status TEXT DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE', 'ARCHIVED', 'REVIEW')),
    extracted_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Structured eligibility and exclusion rules extracted from documents
CREATE TABLE IF NOT EXISTS eligibility_rules (
    id SERIAL PRIMARY KEY,
    scheme_version_id INTEGER NOT NULL REFERENCES scheme_versions(id) ON DELETE CASCADE,
    rule TEXT,
    type TEXT DEFAULT 'eligibility' CHECK (type IN ('eligibility', 'exclusion')),
    category TEXT,
    value JSONB,
    semantic_confidence NUMERIC DEFAULT 0.85,
    review_required BOOLEAN DEFAULT FALSE,
    review_reasons JSONB DEFAULT '[]'::jsonb,
    rule_data JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. Evidence grounding for eligibility and exclusion rules
CREATE TABLE IF NOT EXISTS rule_evidence (
    id SERIAL PRIMARY KEY,
    rule_id INTEGER NOT NULL REFERENCES eligibility_rules(id) ON DELETE CASCADE,
    page_number INTEGER,
    section TEXT,
    evidence_text TEXT,
    source_url TEXT,
    ocr_confidence NUMERIC,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 7. Audit logs of scheme updates and version changes
CREATE TABLE IF NOT EXISTS update_logs (
    id SERIAL PRIMARY KEY,
    scheme_id INTEGER REFERENCES schemes(id) ON DELETE SET NULL,
    old_version_id INTEGER REFERENCES scheme_versions(id) ON DELETE SET NULL,
    new_version_id INTEGER REFERENCES scheme_versions(id) ON DELETE SET NULL,
    change_type TEXT,
    summary TEXT,
    eligibility_relevance TEXT,
    changes JSONB,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status TEXT
);

-- Backward-compatibility column migrations if tables pre-existed from earlier checkpoints
ALTER TABLE schemes ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE scheme_versions ADD COLUMN IF NOT EXISTS document_hash TEXT;
ALTER TABLE scheme_versions ADD COLUMN IF NOT EXISTS document_date DATE;
ALTER TABLE scheme_versions ADD COLUMN IF NOT EXISTS source_url TEXT;
ALTER TABLE eligibility_rules ADD COLUMN IF NOT EXISTS rule TEXT;
ALTER TABLE eligibility_rules ADD COLUMN IF NOT EXISTS type TEXT DEFAULT 'eligibility';
ALTER TABLE eligibility_rules ADD COLUMN IF NOT EXISTS category TEXT;
ALTER TABLE eligibility_rules ADD COLUMN IF NOT EXISTS value JSONB;
ALTER TABLE eligibility_rules ADD COLUMN IF NOT EXISTS semantic_confidence NUMERIC DEFAULT 0.85;
ALTER TABLE eligibility_rules ADD COLUMN IF NOT EXISTS review_required BOOLEAN DEFAULT FALSE;
ALTER TABLE eligibility_rules ADD COLUMN IF NOT EXISTS review_reasons JSONB DEFAULT '[]'::jsonb;
ALTER TABLE eligibility_rules ALTER COLUMN rule_data DROP NOT NULL;
ALTER TABLE update_logs ADD COLUMN IF NOT EXISTS change_type TEXT;
ALTER TABLE update_logs ADD COLUMN IF NOT EXISTS summary TEXT;
ALTER TABLE update_logs ADD COLUMN IF NOT EXISTS eligibility_relevance TEXT;
ALTER TABLE update_logs ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

-- Partial unique index ensuring at most one ACTIVE version per scheme
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_version_per_scheme 
ON scheme_versions (scheme_id) WHERE status = 'ACTIVE';

-- Partial unique index ensuring duplicate document hashes are not stored per scheme
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_doc_hash_per_scheme 
ON scheme_versions (scheme_id, document_hash) WHERE document_hash IS NOT NULL;
"""


def get_connection(connection_url: str = None) -> psycopg.Connection:
    """
    Creates and returns a connection to PostgreSQL.
    If no URL is provided, it uses DATABASE_URL from config.
    """
    url = connection_url or DATABASE_URL
    return psycopg.connect(url)


def test_connection() -> bool:
    """
    Checks if PostgreSQL connection is working.
    Returns True if successful, False otherwise.
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1;")
                return cur.fetchone()[0] == 1
    except Exception as e:
        logger.error(f"PostgreSQL connection failed: {e}")
        return False


def ensure_database_exists(connection_url: str = None):
    """
    Checks if the target database exists. If not, connects to default 'postgres'
    database and creates the target database automatically.
    """
    from urllib.parse import urlparse
    url = connection_url or DATABASE_URL
    parsed = urlparse(url)
    target_db = parsed.path.lstrip("/")

    if not target_db:
        return

    # Try connecting directly to target DB
    try:
        with psycopg.connect(url) as conn:
            return
    except psycopg.OperationalError as e:
        # If error is that database does not exist, connect to 'postgres' and create it
        if f'database "{target_db}" does not exist' in str(e):
            logger.info(f"Database '{target_db}' does not exist. Creating it now...")
            # Reconstruct URL pointing to default 'postgres' database
            server_url = f"{parsed.scheme}://{parsed.netloc}/postgres"
            with psycopg.connect(server_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute(f'CREATE DATABASE "{target_db}";')
            logger.info(f"Database '{target_db}' created successfully.")
        else:
            raise


def init_db(connection_url: str = None):
    """
    Creates all tables in PostgreSQL if they don't already exist.
    """
    url = connection_url or DATABASE_URL
    ensure_database_exists(url)
    logger.info("Initializing database tables...")
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            cur.execute(CREATE_TABLES_SQL)
        conn.commit()
    logger.info("Database tables initialized successfully.")

