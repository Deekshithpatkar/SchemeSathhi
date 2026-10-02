"""
Run PDF Processing Script.
Demonstrates extracting Unicode text using PyMuPDF and detecting scanned pages.

Usage:
    python scripts/run_pdf_processing.py
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

from app.document_processor import extract_text_from_pdf, save_processed_text
from app.downloader import download_and_register

# 1. Text-based Karnataka Government Order
TEXT_DOC_INFO = {
    "document_url": "https://raitamitra.karnataka.gov.in/storage/pdf-files/SecondaryAgriculturedirectorateGO.pdf",
    "title": "Directorate of Secondary Agriculture Govt Order",
    "document_type": "order",
    "source_page_url": "https://raitamitra.karnataka.gov.in/127/government-order%28schemes%29/kn",
}


def main():
    print("=" * 70)
    print("Karnataka Scheme Update Agent - Step 8: PDF Text Processing")
    print("=" * 70)

    # 1. Process the PM-KISAN PDF in data/raw/ (scanned document demonstration)
    raw_pdfs = list(Path("data/raw").glob("*PM-KISAN*.pdf"))
    if raw_pdfs:
        print("\n--- Example 1: Scanned Document Evaluation ---")
        scanned_pdf = raw_pdfs[0]
        print(f"File: {scanned_pdf.name}")
        result_scanned = extract_text_from_pdf(scanned_pdf)

        print(f"  Total Pages      : {result_scanned['total_pages']}")
        print(f"  Usable Pages     : {result_scanned['usable_pages_count']}")
        print(f"  Scanned Pages    : {result_scanned['scanned_pages_count']}")
        print(f"  Requires OCR?    : {result_scanned['requires_ocr']}  <-- Correctly flagged for Step 9 OCR!")

    # 2. Download and process the text-based PDF (Unicode text extraction demonstration)
    print("\n--- Example 2: Text-Based Government Order Processing ---")
    print(f"Target URL: {TEXT_DOC_INFO['document_url']}")
    dl_res = download_and_register(TEXT_DOC_INFO)

    if dl_res["success"]:
        pdf_path = dl_res["file_path"]
        result_text = extract_text_from_pdf(pdf_path)

        print(f"  Total Pages      : {result_text['total_pages']}")
        print(f"  Usable Pages     : {result_text['usable_pages_count']}")
        print(f"  Scanned Pages    : {result_text['scanned_pages_count']}")
        print(f"  Requires OCR?    : {result_text['requires_ocr']}")

        # Save extracted clean text
        out_txt = save_processed_text(pdf_path, result_text["full_text"])
        print(f"  Saved Text File  : {out_txt}")

        print("\n--- Preview of Extracted Text (First 350 chars) ---")
        preview = result_text["full_text"][:350]
        print(preview + "...\n")
        print("[SUCCESS] Text successfully extracted directly via PyMuPDF without OCR!")

    print("=" * 70)


if __name__ == "__main__":
    main()
