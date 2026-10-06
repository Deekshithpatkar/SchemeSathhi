import sys
import json
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
from app.llm_client import LLMClient

client = LLMClient()


def extract_page_candidate_rules(page_text, page_num):
    prompt = f"""PAGE {page_num} TEXT FROM KARNATAKA GOVERNMENT SCHEME DOCUMENT:
{page_text}

TASK:
Extract candidate eligibility rules (who qualifies as a citizen beneficiary) and exclusion rules (who is disqualified).

GUIDELINES:
- Understand Kannada terms:
  * Eligibility: 'ಅರ್ಹತೆ', 'ಅರ್ಹ ಫಲಾನುಭವಿ', 'ಯೋಜನೆಯ ಸೌಲಭ್ಯ', 'ಯಜಮಾನಿ ಮಹಿಳೆ', 'ರೈತರ ಮಕ್ಕಳು', 'ಅರ್ಹರಾಗಿರುತ್ತಾರೆ'
  * Exclusion: 'ಅನರ್ಹ', 'ಅರ್ಹರಾಗಿರುವುದಿಲ್ಲ', 'ಅನ್ವಯಿಸುವುದಿಲ್ಲ', 'ತೆರಿಗೆ ಪಾವತಿದಾರರು', 'ಅನುತ್ತೀರ್ಣ'
- State rules in clear English.
- Evidence MUST be the exact verbatim quote from the text above.
- IGNORE committee members ('nominated by government'), administrative procedures, and macro funding allocations.
- If NO citizen eligibility or exclusion criteria are stated on this page, return empty lists:
  "eligibility_rules": [], "exclusion_rules": []

Return JSON with:
- eligibility_rules: [{{"rule": "...", "type": "eligibility", "evidence": "exact quote"}}]
- exclusion_rules: [{{"rule": "...", "type": "exclusion", "evidence": "exact quote"}}]
"""
    return client.generate_json(
        prompt=prompt,
        system_prompt="You extract citizen eligibility and exclusion rules from Karnataka government documents.",
        temperature=0.0,
    )


# Test on Gruha Lakshmi Page 1 and 2
with open("data/structured/30af3c4d_GruhaLaxmiGO.json", "r", encoding="utf-8") as f:
    gl = json.load(f)

for p in gl["pages"][:2]:
    p_num = p["page_number"]
    txt = "\n".join(b.get("text", "") for b in p.get("blocks", []))
    print(f"Testing Gruha Lakshmi Page {p_num}...")
    res = extract_page_candidate_rules(txt, p_num)
    print(f"Page {p_num} Result:\n", json.dumps(res, indent=2, ensure_ascii=False))
