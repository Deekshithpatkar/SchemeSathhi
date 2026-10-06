import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
from app.llm_client import LLMClient
from app.rule_extractor import format_document_context

client = LLMClient()

with open("data/structured/30af3c4d_GruhaLaxmiGO.json", "r", encoding="utf-8") as f:
    gl_doc = json.load(f)

ctx = format_document_context(gl_doc)

json_skeleton = {
    "scheme_name": "Official Scheme Name or null",
    "department": "Government Department or null",
    "document_type": "government_order",
    "eligibility_rules": [
        {
            "rule": "Exact eligibility condition in English (e.g. Woman head of household in BPL/APL cards)",
            "type": "eligibility",
            "category": "family_head / land_ownership / income / other",
            "evidence": {
                "page_number": 1,
                "source_text": "Verbatim quote in Kannada from document",
                "ocr_confidence": 85.0
            }
        }
    ],
    "exclusion_rules": [
        {
            "rule": "Exact disqualification condition in English (e.g. Income tax payers excluded)",
            "type": "exclusion",
            "category": "taxpayer / employment / other",
            "evidence": {
                "page_number": 2,
                "source_text": "Verbatim quote in Kannada from document",
                "ocr_confidence": 85.0
            }
        }
    ]
}

bilingual_prompt = f"""DOCUMENT CONTENT FOR EXTRACTION:
{ctx}

TARGET JSON FORMAT SPECIFICATION:
{json.dumps(json_skeleton, indent=2)}

TASK:
Extract citizen candidate eligibility rules (who qualifies) and exclusion rules (who is disqualified).

KANNADA LANGUAGE GUIDELINES:
- Understand Kannada terms:
  * Eligibility: 'ಅರ್ಹತೆ', 'ಅರ್ಹ ಫಲಾನುಭವಿ' (eligible beneficiary), 'ಯೋಜನೆಯ ಸೌಲಭ್ಯ' (scheme benefit), 'ಕುಟುಂಬದ ಯಜಮಾನಿ ಮಹಿಳೆ' (woman head of family), 'ರೈತರ ಮಕ್ಕಳು' (farmers' children), 'ಅರ್ಹರಾಗಿರುತ್ತಾರೆ' (are eligible)
  * Exclusion: 'ಅನರ್ಹ' (ineligible), 'ಅರ್ಹರಾಗಿರುವುದಿಲ್ಲ' (are not eligible), 'ಅನ್ವಯಿಸುವುದಿಲ್ಲ' (does not apply), 'ತೆರಿಗೆ ಪಾವತಿದಾರರು' (tax payers), 'ಅನುತ್ತೀರ್ಣ' (failed/repeating exam)
- Formulate each rule in clear English.
- The 'source_text' in evidence MUST BE THE EXACT VERBATIM KANNADA QUOTE from the document. Do NOT replace Kannada evidence with English.

CRITICAL ANTI-HALLUCINATION RULES:
- Statements describing macro funding allocations, central/state funding shares, or committee member nominations ('to be nominated by government') MUST BE IGNORED.
- DO NOT invent rules from outside knowledge. Extract ONLY conditions physically stated in this document.
- If the document contains NO citizen qualification rules, return empty lists:
  "eligibility_rules": [], "exclusion_rules": []
"""

system_prompt = "You are an expert Karnataka Government Scheme Rule Extraction Specialist proficient in Kannada and English."

print("Calling qwen3-vl:4b-instruct with bilingual full-document prompt on Gruha Lakshmi...")
res = client.generate_json(prompt=bilingual_prompt, system_prompt=system_prompt, temperature=0.0)
print("Gruha Lakshmi Result:\n", json.dumps(res, indent=2, ensure_ascii=False))
