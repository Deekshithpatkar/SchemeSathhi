"""
Document Downloader module.
Safely downloads discovered scheme PDFs, calculates SHA-256 fingerprints,
verifies file validity, and stores metadata in PostgreSQL.
"""

import os
import hashlib
import re
from pathlib import Path
from typing import Optional, Dict, Any
from urllib.parse import urlparse, unquote
import requests
from psycopg.rows import dict_row

from app.config import RAW_DIR, setup_logger
from app.db import get_connection

logger = setup_logger("downloader")

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36 SchemeWatcher/1.0"
    ),
    "Accept": "application/pdf,application/octet-stream,*/*",
}


def calculate_sha256(content: bytes) -> str:
    """Calculates the SHA-256 hash of byte content."""
    return hashlib.sha256(content).hexdigest()


def get_safe_filename(url: str, file_hash: str) -> str:
    """
    Creates a clean, safe filename using the first 8 characters of the hash
    and the original filename from the URL.
    Example: 'a1b2c3d4_krishi_bhagya_guidelines.pdf'
    """
    # Extract filename from URL
    path = unquote(urlparse(url).path)
    base_name = os.path.basename(path)

    # Clean characters that are invalid in Windows filenames: \ / : * ? " < > |
    clean_name = re.sub(r'[\\/*?:"<>| ]', "_", base_name)
    if not clean_name.lower().endswith(".pdf"):
        clean_name += ".pdf"

    # Prefix with the first 8 chars of SHA-256 to ensure uniqueness and clarity
    return f"{file_hash[:8]}_{clean_name}"


def is_valid_pdf_content(content: bytes) -> bool:
    """Checks if downloaded content starts with standard PDF magic bytes '%PDF'."""
    if len(content) < 4:
        return False
    # Standard PDF files start with %PDF
    return content.startswith(b"%PDF")


def download_file(url: str, output_dir: Path = RAW_DIR, timeout: int = 30) -> Optional[Dict[str, Any]]:
    """
    Downloads a document from a URL and saves it to output_dir.
    Calculates SHA-256 hash and checks that the file is non-empty.
    Returns download metadata dictionary or None if download fails.
    """
    try:
        logger.info(f"Downloading: {url}")
        response = requests.get(url, headers=DEFAULT_HEADERS, timeout=timeout, stream=True)
        response.raise_for_status()

        content = response.content
        if not content:
            logger.error(f"Downloaded 0 bytes from {url}")
            return None

        # Calculate unique content fingerprint
        file_hash = calculate_sha256(content)
        file_size = len(content)

        # Generate safe filename and save to data/raw/
        filename = get_safe_filename(url, file_hash)
        output_dir.mkdir(parents=True, exist_ok=True)
        save_path = output_dir / filename

        with open(save_path, "wb") as f:
            f.write(content)

        is_pdf = is_valid_pdf_content(content)
        logger.info(f"Saved: {save_path.name} ({file_size} bytes, PDF: {is_pdf}, Hash: {file_hash[:8]}...)")

        return {
            "source_url": url,
            "file_path": str(save_path),
            "file_name": filename,
            "file_hash": file_hash,
            "file_size": file_size,
            "is_pdf": is_pdf,
        }

    except requests.RequestException as e:
        logger.error(f"Failed to download {url}: {e}")
        return None


def get_existing_document_by_hash(file_hash: str) -> Optional[Dict[str, Any]]:
    """Checks if a document with the exact same content hash already exists in PostgreSQL."""
    sql = "SELECT * FROM documents WHERE file_hash = %s ORDER BY id DESC LIMIT 1;"
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (file_hash,))
            return cur.fetchone()


def get_existing_document_by_url(source_url: str) -> Optional[Dict[str, Any]]:
    """Checks if a document with the same source URL already exists in PostgreSQL."""
    sql = "SELECT * FROM documents WHERE source_url = %s ORDER BY id DESC LIMIT 1;"
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (source_url,))
            return cur.fetchone()


def register_document(
    source_url: str,
    file_hash: str,
    file_path: str,
    title: Optional[str] = None,
    document_type: Optional[str] = "guideline",
    source_page_url: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Saves document metadata into the PostgreSQL 'documents' table.
    Returns the created database record.
    """
    sql = """
    INSERT INTO documents (source_url, source_page_url, file_hash, file_path, title, document_type)
    VALUES (%s, %s, %s, %s, %s, %s)
    RETURNING id, source_url, source_page_url, file_hash, file_path, title, document_type, downloaded_at;
    """
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, (source_url, source_page_url, file_hash, file_path, title, document_type))
            record = cur.fetchone()
        conn.commit()

    logger.info(f"Registered document in database: ID {record['id']} ('{record['title']}')")
    return record


def delete_document(document_id: int) -> bool:
    """Deletes a document record from PostgreSQL."""
    sql = "DELETE FROM documents WHERE id = %s;"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (document_id,))
            deleted = cur.rowcount > 0
        conn.commit()
    return deleted


def download_and_register(doc_info: Dict[str, Any], output_dir: Path = RAW_DIR) -> Dict[str, Any]:
    """
    High-level helper:
    1. Downloads the file
    2. Checks if content hash already exists in DB (avoids duplicate processing)
    3. If new or updated, stores in PostgreSQL
    """
    source_url = doc_info["document_url"]
    download_res = download_file(url=source_url, output_dir=output_dir)

    if not download_res:
        return {
            "success": False,
            "status": "download_failed",
            "source_url": source_url,
            "message": "Failed to download file.",
        }

    file_hash = download_res["file_hash"]

    # Check if identical file already exists in DB
    existing_by_hash = get_existing_document_by_hash(file_hash)
    if existing_by_hash:
        logger.info(f"Document already exists with same hash (ID: {existing_by_hash['id']}). Skipping.")
        return {
            "success": True,
            "status": "unchanged",
            "document_id": existing_by_hash["id"],
            "file_hash": file_hash,
            "file_path": existing_by_hash["file_path"],
            "title": existing_by_hash["title"],
            "message": "Document is unchanged (hash matches existing record).",
        }

    # Register new document in database
    db_record = register_document(
        source_url=source_url,
        file_hash=file_hash,
        file_path=download_res["file_path"],
        title=doc_info.get("title", ""),
        document_type=doc_info.get("document_type", "guideline"),
        source_page_url=doc_info.get("source_page_url"),
    )

    return {
        "success": True,
        "status": "new",
        "document_id": db_record["id"],
        "file_hash": file_hash,
        "file_path": db_record["file_path"],
        "title": db_record["title"],
        "message": "New document successfully downloaded and registered.",
    }
