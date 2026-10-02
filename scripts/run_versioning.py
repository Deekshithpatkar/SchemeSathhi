"""
Run Versioning Script.
Demonstrates version detection and historical version preservation in PostgreSQL.

Usage:
    python scripts/run_versioning.py
"""

import sys
from pathlib import Path

# Enable UTF-8 encoding for Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to sys.path so 'app' can be imported easily
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.downloader import get_existing_document_by_url
from app.versioning import detect_and_register_version, get_scheme_versions, get_or_create_scheme


def main():
    print("=" * 70)
    print("Karnataka Scheme Update Agent - Step 7: Version Detection")
    print("=" * 70)

    # 1. Lookup the PM-KISAN document downloaded in Step 6
    doc_url = "https://raitamitra.karnataka.gov.in/storage/pdf-files/PM-KISANSchemeguidelinesfinal.pdf"
    doc = get_existing_document_by_url(doc_url)

    if not doc:
        print("[WARNING] PM-KISAN document not found in database. Run 'python scripts/run_download.py' first.")
        return

    scheme_name = "Pradhan Mantri Kisan Samman Nidhi"
    department = "Agriculture Department"

    print(f"Target Scheme : {scheme_name}")
    print(f"Document ID   : {doc['id']}")
    print(f"File Hash     : {doc['file_hash'][:12]}...")
    print("-" * 70)

    # Run Version Detection
    print("\nDetecting and registering version...")
    res = detect_and_register_version(
        scheme_name=scheme_name,
        document_id=doc["id"],
        file_hash=doc["file_hash"],
        document_title=doc["title"],
        document_url=doc["source_url"],
        published_date="04-07-2019",
        department=department,
    )

    print(f"[OK] Detection Status : {res['status']}")
    print(f"     Version Label    : {res.get('version_label')}")
    print(f"     Scheme ID        : {res['scheme_id']}")
    print(f"     Message          : {res['message']}")

    # Display all versions currently stored in PostgreSQL for this scheme
    print("\n" + "=" * 70)
    print(f"PostgreSQL Version History for '{scheme_name}':")
    versions = get_scheme_versions(res["scheme_id"])
    for v in versions:
        print(f"  - Version: {v['version_label']:<10} | Status: {v['status']:<10} | Published: {v['published_date']} | Created: {v['created_at']}")
    print("=" * 70)


if __name__ == "__main__":
    main()
