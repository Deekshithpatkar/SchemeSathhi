"""
Seed Sources Script.
Populates the source registry with initial official Karnataka government scheme pages.

Usage:
    python scripts/seed_sources.py
"""

import sys
from pathlib import Path

# Add project root to sys.path so 'app' can be imported easily
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.registry import add_source, get_sources

INITIAL_SOURCES = [
    {
        "department": "Agriculture Department",
        "source_name": "Raitha Mitra Karnataka",
        "official_url": "https://raitamitra.karnataka.gov.in",
        "source_type": "scheme_portal",
    },
    {
        "department": "Women and Child Development Department",
        "source_name": "Gruha Lakshmi Scheme / WCD",
        "official_url": "https://wcd.karnataka.gov.in",
        "source_type": "scheme_page",
    },
    {
        "department": "Energy Department",
        "source_name": "Gruha Jyothi Scheme",
        "official_url": "https://energy.karnataka.gov.in",
        "source_type": "scheme_page",
    },
    {
        "department": "Food, Civil Supplies & Consumer Affairs",
        "source_name": "Ahara Karnataka / Anna Bhagya",
        "official_url": "https://ahara.kar.nic.in",
        "source_type": "scheme_portal",
    },
]


def main():
    print("Seeding initial Karnataka official sources...")
    for item in INITIAL_SOURCES:
        record = add_source(
            source_name=item["source_name"],
            official_url=item["official_url"],
            department=item["department"],
            source_type=item["source_type"],
        )
        print(f"[OK] Registered: {record['source_name']} (ID: {record['id']})")

    sources = get_sources(active_only=True)
    print(f"\nTotal active sources in registry: {len(sources)}")


if __name__ == "__main__":
    main()
