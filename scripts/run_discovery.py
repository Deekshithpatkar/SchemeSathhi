"""
Run Discovery Script.
Demonstrates website discovery by scanning registered official sources or a given URL.

Usage:
    python scripts/run_discovery.py
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

from app.registry import get_sources, record_source_check
from app.discovery import discover_from_url


def main():
    print("=" * 60)
    print("Karnataka Scheme Update Agent - Step 4: Website Discovery")
    print("=" * 60)

    # 1. Fetch active sources from the registry
    sources = get_sources(active_only=True)
    if not sources:
        print("[WARNING] No active sources found in database. Run 'python scripts/seed_sources.py' first.")
        return

    print(f"Found {len(sources)} active source(s) in registry.\n")

    # 2. Check the first source as a live demonstration
    source = sources[0]
    print(f"Checking Source: {source['source_name']}")
    print(f"URL: {source['official_url']}")
    print("-" * 60)

    result = discover_from_url(source["official_url"])

    if result["success"]:
        print(f"[OK] Successfully fetched page! Total links scanned: {result['all_links_count']}")
        print(f"Direct Document Links found: {len(result['document_links'])}")
        for doc in result["document_links"][:5]:  # Show up to 5 documents
            print(f"  - [DOC] {doc['text'] or 'Document'}: {doc['url']}")

        print(f"\nScheme Page Links found: {len(result['scheme_page_links'])}")
        for page in result["scheme_page_links"][:5]:  # Show up to 5 scheme pages
            print(f"  - [PAGE] {page['text'] or 'Scheme Page'}: {page['url']}")

        # Record successful check in database
        record_source_check(source["id"], success=True)
        print("\n[OK] Updated source last_checked timestamp in PostgreSQL.")
    else:
        print(f"[ERROR] Could not fetch {source['official_url']} (site might be slow or down).")
        record_source_check(source["id"], success=False)

    print("=" * 60)


if __name__ == "__main__":
    main()
