"""
Run Document Discovery Script.
Demonstrates extracting and classifying actual scheme documents (PDFs) from a government scheme page.

Usage:
    python scripts/run_document_discovery.py
"""

import sys
from pathlib import Path

# Enable UTF-8 encoding for Windows console so Kannada characters print properly
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add project root to sys.path so 'app' can be imported easily
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.document_discovery import discover_documents_from_page


def main():
    print("=" * 70)
    print("Karnataka Scheme Update Agent - Step 5: Document Discovery")
    print("=" * 70)

    # Real Karnataka Scheme Orders Page discovered in Step 4
    scheme_page_url = "https://raitamitra.karnataka.gov.in/127/government-order%28schemes%29/kn"
    print(f"Scanning Scheme Page: {scheme_page_url}\n")

    # Discover and classify all scheme documents
    docs = discover_documents_from_page(
        page_url=scheme_page_url,
        scheme_name="Karnataka Agriculture Schemes",
        department="Agriculture Department",
        scheme_only=True,
    )

    print(f"[OK] Found {len(docs)} genuine scheme document(s):\n")
    for i, doc in enumerate(docs, 1):
        print(f"--- Document #{i} ---")
        print(f"  Title     : {doc['title']}")
        print(f"  Type      : {doc['document_type'].upper()}")
        print(f"  Date      : {doc['published_date'] or 'N/A'}")
        print(f"  URL       : {doc['document_url']}")

    print("=" * 70)


if __name__ == "__main__":
    main()
