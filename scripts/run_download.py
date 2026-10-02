"""
Run Download Script.
Demonstrates downloading an official Karnataka scheme document, verifying its SHA-256 fingerprint,
and saving metadata into PostgreSQL.

Usage:
    python scripts/run_download.py
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

from app.downloader import download_and_register

# Real Karnataka Agriculture Government Order discovered in Step 5
SAMPLE_DOC = {
    "document_url": "https://raitamitra.karnataka.gov.in/storage/pdf-files/PM-KISANSchemeguidelinesfinal.pdf",
    "title": "ಪ್ರಧಾನ ಮಂತ್ರಿ ಕಿಸಾನ್ ಯೋಜನೆ ಮಾರ್ಗಸೂಚಿ (PM-KISAN Scheme Guidelines)",
    "document_type": "guideline",
    "source_page_url": "https://raitamitra.karnataka.gov.in/127/government-order%28schemes%29/kn",
}


def main():
    print("=" * 70)
    print("Karnataka Scheme Update Agent - Step 6: Document Downloader")
    print("=" * 70)
    print(f"Target Document : {SAMPLE_DOC['title']}")
    print(f"URL             : {SAMPLE_DOC['document_url']}\n")

    print("Step 6.1: First download attempt...")
    result1 = download_and_register(SAMPLE_DOC)

    if result1["success"]:
        print(f"[OK] Status      : {result1['status'].upper()}")
        print(f"     Document ID : {result1['document_id']}")
        print(f"     SHA-256     : {result1['file_hash']}")
        print(f"     Saved Path  : {result1['file_path']}")
        print(f"     Message     : {result1['message']}")
    else:
        print(f"[ERROR] {result1['message']}")
        return

    print("\n" + "-" * 70)
    print("Step 6.2: Second download attempt (testing duplicate prevention)...")
    result2 = download_and_register(SAMPLE_DOC)

    print(f"[OK] Status      : {result2['status'].upper()}")
    print(f"     Document ID : {result2['document_id']}")
    print(f"     Message     : {result2['message']}")

    if result2["status"] == "unchanged":
        print("[SUCCESS] Duplicate prevention verified! Did not re-process unchanged file.")
    print("=" * 70)


if __name__ == "__main__":
    main()
