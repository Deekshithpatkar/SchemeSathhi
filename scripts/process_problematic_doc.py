"""
Script to process the problematic Karnataka Government PDF
using the newly built Step 9 Document Understanding Pipeline.
"""
import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import RAW_DIR, STRUCTURED_DIR, PROCESSED_DIR
from app.document_processor import process_document_understanding

def main():
    target_pdf = RAW_DIR / "e75996bb_PM-KISANSchemeguidelinesfinal.pdf"
    if not target_pdf.exists():
        print(f"Error: {target_pdf} does not exist.")
        return

    print("=" * 60)
    print("RUNNING STEP 9: DOCUMENT UNDERSTANDING PIPELINE")
    print(f"Target: {target_pdf.name}")
    print("=" * 60)

    # Process page 1 and 2 or all pages
    doc_result = process_document_understanding(target_pdf, source_url="https://raitamitra.karnataka.gov.in/pmkisan")

    structured_json_path = STRUCTURED_DIR / f"{target_pdf.stem}.json"
    txt_path = PROCESSED_DIR / f"{target_pdf.stem}.txt"

    print("\n[SUCCESS] Processing Complete!")
    print(f"Structured JSON: {structured_json_path}")
    print(f"Fallback Text:   {txt_path}")

    # Inspect summary
    struct = doc_result["structured_data"]
    summary = {
        "filename": struct["document"]["filename"],
        "total_pages": struct["document"]["total_pages"],
        "pages_summary": []
    }

    for page in doc_result["pages"]:
        forms = page.get("forms")
        summary["pages_summary"].append({
            "page_number": page["page_number"],
            "page_type": page["page_type"],
            "method": page["extraction_method"],
            "avg_confidence": page.get("avg_confidence"),
            "table_count": len(page.get("tables", [])),
            "table_rows": [len(t["rows"]) for t in page.get("tables", [])],
            "form_fields_count": len(forms["fields"]) if forms else 0,
            "detected_form_labels": [f["label"] for f in forms["fields"][:5]] if forms else []
        })

    print("\nProcessing Summary:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    # Print first table snippet if available
    first_table = None
    for page in doc_result["pages"]:
        if page["tables"]:
            first_table = page["tables"][0]
            print(f"\n--- First Table on Page {page['page_number']} ---")
            print(f"Table BBox: {first_table['bbox']}")
            print(f"Total Rows: {len(first_table['rows'])}")
            for r_idx, row in enumerate(first_table["rows"][:5]):
                row_texts = [f"Col {c.get('column')} ({c.get('confidence', 0):.0f}%): {c.get('text', '')[:25]}" for c in row["cells"]]
                print(f"  Row {r_idx}: {' | '.join(row_texts)}")
            break

if __name__ == "__main__":
    main()
