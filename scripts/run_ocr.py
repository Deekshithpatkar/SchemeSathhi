"""
Run OCR Script.
Demonstrates the OCR Fallback pipeline on the real scanned PM-KISAN Government Notification.

Usage:
    python scripts/run_ocr.py
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

from app.ocr import process_with_ocr_fallback


def main():
    print("=" * 70)
    print("Karnataka Scheme Update Agent - Step 9: Kannada & English OCR Fallback")
    print("=" * 70)

    # Locate the real scanned PM-KISAN PDF in data/raw
    raw_pdfs = list(Path("data/raw").glob("*PM-KISAN*.pdf"))
    if not raw_pdfs:
        print("[WARNING] PM-KISAN PDF not found in data/raw. Run 'python scripts/run_download.py' first.")
        return

    scanned_pdf = raw_pdfs[0]
    print(f"Target Scanned Document : {scanned_pdf.name}")
    print("Running OCR Fallback Pipeline (Kannada + English)...\n")

    # Run OCR Fallback pipeline
    result = process_with_ocr_fallback(scanned_pdf, languages="kan+eng")

    print(f"[OK] Total Pages   : {result['total_pages']}")
    print(f"     OCR Pages     : {result['ocr_pages_count']}")
    print(f"     OCR Triggered : {result['ocr_performed']}")
    print(f"     Saved Output  : {result['processed_file_path']}")

    print("\n" + "=" * 70)
    print("Preview of OCR-Extracted Kannada/English Text (First 400 characters):")
    print("-" * 70)
    preview = result["full_text"][:400]
    print(preview + "...\n")
    print("[SUCCESS] Scanned Kannada/English PDF successfully converted to readable text!")
    print("=" * 70)


if __name__ == "__main__":
    main()
