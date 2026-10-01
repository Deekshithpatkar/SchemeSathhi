"""
Database connection and initialization module.
Uses psycopg to connect to PostgreSQL and create the core tables.
"""

import psycopg
from app.config import DATABASE_URL, setup_logger

logger = setup_logger("db")

# SQL script to create the 6 core tables if they do not already exist
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
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
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
    published_date DATE,
    effective_from DATE,
    effective_until DATE,
    status TEXT DEFAULT 'ACTIVE',
    extracted_text TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 5. Structured eligibility rules extracted from documents
CREATE TABLE IF NOT EXISTS eligibility_rules (
    id SERIAL PRIMARY KEY,
    scheme_version_id INTEGER NOT NULL REFERENCES scheme_versions(id) ON DELETE CASCADE,
    rule_data JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 6. Audit logs of scheme updates and version changes
CREATE TABLE IF NOT EXISTS update_logs (
    id SERIAL PRIMARY KEY,
    scheme_id INTEGER REFERENCES schemes(id) ON DELETE SET NULL,
    old_version_id INTEGER REFERENCES scheme_versions(id) ON DELETE SET NULL,
    new_version_id INTEGER REFERENCES scheme_versions(id) ON DELETE SET NULL,
    changes JSONB,
    detected_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    status TEXT
);
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

