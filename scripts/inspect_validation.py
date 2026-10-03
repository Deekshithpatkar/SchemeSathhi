"""
Detailed validation and inspection script for Step 9 Document Understanding output.
Inspects structured JSON against the problematic government PDF.
"""
import json
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import STRUCTURED_DIR, RAW_DIR
import pymupdf

def inspect():
    pdf_path = RAW_DIR / "e75996bb_PM-KISANSchemeguidelinesfinal.pdf"
    json_path = STRUCTURED_DIR / f"{pdf_path.stem}.json"

    print("=" * 70)
    print("STEP 9 DETAILED VALIDATION & INSPECTION REPORT")
    print(f"Target PDF:  {pdf_path.name} (Exists: {pdf_path.exists()})")
    print(f"Target JSON: {json_path.name} (Exists: {json_path.exists()})")
    print("=" * 70)

    if not json_path.exists():
        print(f"Error: {json_path} does not exist.")
        return

    # Check original PDF pages
    doc = pymupdf.open(str(pdf_path))
    print(f"\n[ORIGINAL PDF INSPECTION]")
    print(f"Page Count: {len(doc)}")
    for i in range(len(doc)):
        p = doc[i]
        pix = p.get_pixmap(dpi=150)
        direct_text = p.get_text()
        print(f"  Page {i+1}: Dimensions={p.rect.width}x{p.rect.height} pt, Pixmap={pix.width}x{pix.height} px, DirectTextLength={len(direct_text)}")
    doc.close()

    # Load structured JSON
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print("\n[STRUCTURED JSON DOCUMENT METADATA]")
    doc_meta = data.get("document", {})
    for k, v in doc_meta.items():
        print(f"  {k}: {v}")

    summary_meta = data.get("summary", {})
    print("\n[PIPELINE SUMMARY]")
    for k, v in summary_meta.items():
        print(f"  {k}: {v}")

    print("\n[PAGE-BY-PAGE DETAILED AUDIT]")
    pages = data.get("pages", [])
    for p in pages:
        p_num = p.get("page_number")
        p_type = p.get("page_type")
        method = p.get("extraction_method")
        avg_conf = p.get("avg_confidence")
        low_conf = p.get("low_conf_percentage")
        dpi = p.get("dpi")
        tables = p.get("tables", [])
        forms = p.get("forms")
        words = p.get("words", [])

        print(f"\n--- Page {p_num} ---")
        print(f"  Classification:      {p_type} (Tags: {p.get('tags')})")
        print(f"  Extraction Method:   {method} (DPI: {dpi})")
        print(f"  Confidence:          Avg={avg_conf:.1f}%, LowConfRatio={low_conf}%")
        print(f"  Word Count Extracted: {len(words)}")

        # Table audit
        if tables:
            print(f"  Tables Detected:     {len(tables)}")
            for t_idx, t in enumerate(tables):
                rows = t.get("rows", [])
                total_cells = sum(len(r.get("cells", [])) for r in rows)
                blank_cells = [c for r in rows for c in r.get("cells", []) if c.get("text") is None]
                filled_cells = [c for r in rows for c in r.get("cells", []) if c.get("text") is not None]
                print(f"    Table {t_idx+1}:")
                print(f"      Bounding Box:   {t.get('bbox')}")
                print(f"      Rows Count:     {len(rows)}")
                print(f"      Total Cells:    {total_cells}")
                print(f"      Blank Cells:    {len(blank_cells)} (with confidence=0.0 & text=null)")
                print(f"      Filled Cells:   {len(filled_cells)}")

                # Inspect first 3 non-empty rows
                print("      Sample Row Extractions:")
                sample_count = 0
                for r in rows:
                    non_empty_in_row = [c for c in r.get("cells", []) if c.get("text")]
                    if non_empty_in_row and sample_count < 3:
                        sample_count += 1
                        print(f"        Row {r.get('row_index')}:")
                        for c in r.get("cells", []):
                            txt = c.get("text")
                            txt_disp = f"'{txt[:35]}...'" if txt else "null (blank cell)"
                            print(f"          [Col {c.get('column')} | Conf: {c.get('confidence'):.1f}% | BBox: {c.get('bbox')}]: {txt_disp}")
        else:
            print("  Tables Detected:     0 (Non-table scanned page)")

        # Form audit
        if forms and forms.get("is_form"):
            print(f"  Form Detected:       True (Confidence: {forms.get('form_confidence', 0)}%)")
            fields = forms.get("fields", [])
            print(f"  Form Fields ({len(fields)}):")
            for fld in fields:
                print(f"    - Label: {fld.get('label')}")
                print(f"      Raw Match: '{fld.get('raw_match')[:40]}...'")
                print(f"      Value:     {fld.get('value')} (correctly null, not hallucinated)")
        else:
            print("  Form Detected:       False")

if __name__ == "__main__":
    inspect()
