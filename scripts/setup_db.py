"""
Setup Database Script.
Run this script to initialize the PostgreSQL tables.

Usage:
    python scripts/setup_db.py
"""

import sys
from pathlib import Path

# Add project root to sys.path so 'app' can be imported easily
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import test_connection, init_db
from app.config import setup_logger

logger = setup_logger("setup_db")


def main():
    print("Testing connection to PostgreSQL...")
    if not test_connection():
        print("[ERROR] Could not connect to PostgreSQL. Please check your DATABASE_URL in .env file.")
        return

    print("[OK] Connected to PostgreSQL successfully!")
    print("Creating tables if they do not exist...")
    try:
        init_db()
        print("[OK] All tables (source_registry, schemes, documents, scheme_versions, eligibility_rules, update_logs) created successfully!")
    except Exception as e:
        print(f"[ERROR] Error creating tables: {e}")


if __name__ == "__main__":
    main()
