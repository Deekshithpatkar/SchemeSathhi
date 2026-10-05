"""
Script to execute Checkpoint 10 on the real problematic Karnataka Government document:
data/structured/e75996bb_PM-KISANSchemeguidelinesfinal.json
Uses local Ollama with qwen2.5:7b-instruct (or configured LLM_MODEL).
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import STRUCTURED_DIR, EXTRACTED_RULES_DIR, LLM_MODEL
from app.rule_extractor import extract_scheme_rules


def main():
    target_json = STRUCTURED_DIR / "e75996bb_PM-KISANSchemeguidelinesfinal.json"
    if not target_json.exists():
        print(f"Error: {target_json} does not exist. Please run Step 9 first.")
        return

    print("=" * 70)
    print("RUNNING CHECKPOINT 10: SEMANTIC SCHEME / RULE EXTRACTION")
    print(f"Input Step 9 JSON: {target_json.name}")
    print(f"LLM Model:         {LLM_MODEL}")
    print("=" * 70)

    try:
        extraction = extract_scheme_rules(
            doc_input=target_json,
            model=LLM_MODEL,
            max_retries=2,
            output_dir=EXTRACTED_RULES_DIR
        )

        output_file = EXTRACTED_RULES_DIR / f"{target_json.stem}_rules.json"

        print("\n[SUCCESS] Semantic Extraction & Pydantic Validation Complete!")
        print(f"Saved Output: {output_file}")
        print("=" * 70)

        # Print structured summary
        print(f"\nScheme Name:         {extraction.scheme_name}")
        print(f"Department:          {extraction.department}")
        print(f"Document Type:       {extraction.document_type}")
        print(f"Document Date:       {extraction.document_date}")
        print(f"Version/GO Info:     {extraction.version_information}")
        print(f"Review Required:     {extraction.review_required}")
        print(f"Review Reasons ({len(extraction.review_reasons)}):")
        for r in extraction.review_reasons:
            print(f"  - {r}")

        print(f"\nExtracted Eligibility Rules: {len(extraction.eligibility_rules)}")
        for idx, rule in enumerate(extraction.eligibility_rules, 1):
            print(f"  {idx}. [{rule.category}] {rule.rule}")
            print(f"     Value: {rule.value} | SemConf: {rule.semantic_confidence:.2f} | Review: {rule.review_required}")
            if rule.evidence:
                ev = rule.evidence
                print(f"     Evidence: Page {ev.page_number} (OCR Conf: {ev.ocr_confidence}%) | '{ev.source_text[:50] if ev.source_text else 'None'}...'")

        print(f"\nExtracted Exclusion Rules: {len(extraction.exclusion_rules)}")
        for idx, rule in enumerate(extraction.exclusion_rules, 1):
            print(f"  {idx}. [{rule.category}] {rule.rule}")
            print(f"     Value: {rule.value} | SemConf: {rule.semantic_confidence:.2f} | Review: {rule.review_required}")
            if rule.evidence:
                ev = rule.evidence
                print(f"     Evidence: Page {ev.page_number} (OCR Conf: {ev.ocr_confidence}%) | '{ev.source_text[:50] if ev.source_text else 'None'}...'")

        print(f"\nMetadata:")
        meta = extraction.extraction_metadata
        if meta:
            print(f"  Model:           {meta.model}")
            print(f"  Pipeline Ver:    {meta.pipeline_version}")
            print(f"  Status:          {meta.validation_status}")
            print(f"  Rules Extracted: {meta.rule_count}")
            print(f"  Review Flags:    {meta.review_required_count}")

    except Exception as e:
        print(f"\n[ERROR] Semantic extraction failed: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
