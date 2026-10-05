"""
Comprehensive Test Suite for Checkpoint 11: Document Comparison.
Covers all 14 required comparison scenarios:
1. Identical files -> unchanged
2. Different hash but identical extracted text -> possible file-level difference but no semantic text change
3. Added page
4. Removed page
5. Modified non-eligibility text
6. Modified eligibility text
7. Modified exclusion text
8. Income threshold changed
9. Age threshold changed
10. Landholding threshold changed
11. Administrative instruction changed -> NOT eligibility change
12. Notification/amendment statement changed -> NOT eligibility change
13. OCR noise difference -> uncertain/review
14. Completely different documents -> review required
"""

import pytest
import json
from pathlib import Path
from typing import Dict, Any, Optional

from app.comparison_schemas import (
    DocumentComparison,
    PageComparison,
    TextChange,
    MetadataChange,
    SemanticChangeItem,
)
from app.comparison import (
    deterministic_compare,
    semantic_compare,
    compare_documents,
    detect_ocr_noise,
    filter_and_validate_semantic_changes,
)
from app.llm_client import LLMClient


class MockLLMClient(LLMClient):
    """Mock LLM client returning predetermined JSON payloads for controlled testing."""
    def __init__(self, responses: Optional[list] = None):
        super().__init__(base_url="http://mock-llm:11434", model="mock-model")
        self.responses = responses or []
        self.call_count = 0

    def _request_raw(self, payload: Dict[str, Any]) -> str:
        self.call_count += 1
        if not self.responses:
            raise ValueError("No mock responses left.")
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        if isinstance(resp, str):
            return resp
        return json.dumps(resp)


# ---------------------------------------------------------------------------
# Test Scenario 1: Identical files -> unchanged
# ---------------------------------------------------------------------------
def test_scenario_1_identical_files_unchanged():
    """Scenario 1: Bit-for-bit identical files by SHA-256 hash return unchanged without LLM call."""
    doc = {
        "filename": "pm_kisan_2026.pdf",
        "sha256": "1111222233334444555566667777888899990000111122223333444455556666",
        "pages": [{"page_number": 1, "text": "Government of Karnataka Agriculture Department."}]
    }

    result = deterministic_compare(doc, doc)
    assert result.hash_status == "identical"
    assert result.overall_status == "unchanged"
    assert result.semantic_comparison_required is False
    assert result.eligibility_relevance == "none"
    assert result.review_required is False
    assert len(result.text_changes) == 0


# ---------------------------------------------------------------------------
# Test Scenario 2: Different hash but identical extracted text
# ---------------------------------------------------------------------------
def test_scenario_2_different_hash_identical_text():
    """Scenario 2: Different SHA-256 but identical extracted text -> no semantic change, no LLM call."""
    doc_old = {
        "filename": "scheme_v1.pdf",
        "sha256": "aaaa000000000000000000000000000000000000000000000000000000000000",
        "pages": [{"page_number": 1, "text": "Small and marginal farmers are eligible."}]
    }
    doc_new = {
        "filename": "scheme_v1_reencoded.pdf",
        "sha256": "bbbb000000000000000000000000000000000000000000000000000000000000",
        "pages": [{"page_number": 1, "text": "Small and marginal farmers are eligible."}]
    }

    result = deterministic_compare(doc_old, doc_new)
    assert result.hash_status == "different"
    assert result.overall_status == "unchanged"
    assert result.semantic_comparison_required is False
    assert result.eligibility_relevance == "none"
    assert result.review_required is False
    assert len(result.text_changes) == 0


# ---------------------------------------------------------------------------
# Test Scenario 3: Added page
# ---------------------------------------------------------------------------
def test_scenario_3_added_page():
    """Scenario 3: New document has an extra page -> detected as added page."""
    doc_old = {
        "filename": "guidelines_2pages.pdf",
        "sha256": "hash_old",
        "pages": [
            {"page_number": 1, "text": "Page 1 Content"},
            {"page_number": 2, "text": "Page 2 Content"},
        ]
    }
    doc_new = {
        "filename": "guidelines_3pages.pdf",
        "sha256": "hash_new",
        "pages": [
            {"page_number": 1, "text": "Page 1 Content"},
            {"page_number": 2, "text": "Page 2 Content"},
            {"page_number": 3, "text": "Page 3 Annexure with new conditions"},
        ]
    }

    result = deterministic_compare(doc_old, doc_new)
    assert result.hash_status == "different"
    assert result.comparison_metadata.pages_added == 1
    assert result.comparison_metadata.pages_removed == 0
    assert result.semantic_comparison_required is True

    added_page = next((p for p in result.page_comparisons if p.page_number == 3), None)
    assert added_page is not None
    assert added_page.status == "added"


# ---------------------------------------------------------------------------
# Test Scenario 4: Removed page
# ---------------------------------------------------------------------------
def test_scenario_4_removed_page():
    """Scenario 4: New document has one fewer page -> detected as removed page."""
    doc_old = {
        "filename": "guidelines_3pages.pdf",
        "sha256": "hash_old",
        "pages": [
            {"page_number": 1, "text": "Page 1 Content"},
            {"page_number": 2, "text": "Page 2 Content"},
            {"page_number": 3, "text": "Page 3 Obsolete conditions"},
        ]
    }
    doc_new = {
        "filename": "guidelines_2pages.pdf",
        "sha256": "hash_new",
        "pages": [
            {"page_number": 1, "text": "Page 1 Content"},
            {"page_number": 2, "text": "Page 2 Content"},
        ]
    }

    result = deterministic_compare(doc_old, doc_new)
    assert result.hash_status == "different"
    assert result.comparison_metadata.pages_removed == 1
    assert result.comparison_metadata.pages_added == 0
    assert result.semantic_comparison_required is True

    removed_page = next((p for p in result.page_comparisons if p.page_number == 3), None)
    assert removed_page is not None
    assert removed_page.status == "removed"


# ---------------------------------------------------------------------------
# Test Scenario 5: Modified non-eligibility text
# ---------------------------------------------------------------------------
def test_scenario_5_modified_non_eligibility_text(tmp_path):
    """Scenario 5: Preamble or header wording changed -> non-eligibility formatting change."""
    doc_old = {
        "filename": "doc_v1.pdf",
        "sha256": "h1",
        "pages": [{"page_number": 1, "text": "Welcome to the Department Portal 2024.\nFarmers are eligible."}]
    }
    doc_new = {
        "filename": "doc_v2.pdf",
        "sha256": "h2",
        "pages": [{"page_number": 1, "text": "Welcome to the Official Karnataka Department Portal 2026.\nFarmers are eligible."}]
    }

    mock_llm = MockLLMClient([{
        "semantic_summary": "Greeting and portal header wording updated.",
        "eligibility_relevance": "none",
        "changes": [{
            "category": "formatting",
            "description": "Portal greeting title rephrased",
            "eligibility_relevance": "none",
            "affected_attribute": None,
            "old_evidence": "Welcome to the Department Portal 2024.",
            "new_evidence": "Welcome to the Official Karnataka Department Portal 2026."
        }]
    }])

    result = compare_documents(doc_old, doc_new, llm_client=mock_llm, output_dir=tmp_path)
    assert result.eligibility_relevance == "none"
    assert result.semantic_changes[0].category == "formatting"


# ---------------------------------------------------------------------------
# Test Scenario 6: Modified eligibility text
# ---------------------------------------------------------------------------
def test_scenario_6_modified_eligibility_text(tmp_path):
    """Scenario 6: Residency criteria modified -> clearly relevant eligibility change."""
    doc_old = {
        "filename": "doc_v1.pdf",
        "sha256": "h1",
        "pages": [{"page_number": 1, "text": "Applicant must be a resident of Karnataka."}]
    }
    doc_new = {
        "filename": "doc_v2.pdf",
        "sha256": "h2",
        "pages": [{"page_number": 1, "text": "Applicant must be a resident of Karnataka and must have resided in the state for at least 5 years."}]
    }

    mock_llm = MockLLMClient([{
        "semantic_summary": "Introduced a mandatory 5-year minimum residency duration requirement.",
        "eligibility_relevance": "clearly_relevant",
        "changes": [{
            "category": "eligibility_related",
            "description": "Added 5-year minimum residency requirement",
            "eligibility_relevance": "clearly_relevant",
            "affected_attribute": "residency",
            "old_evidence": "Applicant must be a resident of Karnataka.",
            "new_evidence": "Applicant must be a resident of Karnataka and must have resided in the state for at least 5 years."
        }]
    }])

    result = compare_documents(doc_old, doc_new, llm_client=mock_llm, output_dir=tmp_path)
    assert result.eligibility_relevance == "clearly_relevant"
    assert result.semantic_changes[0].category == "eligibility_related"
    assert result.semantic_changes[0].affected_attribute == "residency"


# ---------------------------------------------------------------------------
# Test Scenario 7: Modified exclusion text
# ---------------------------------------------------------------------------
def test_scenario_7_modified_exclusion_text(tmp_path):
    """Scenario 7: Exclusion of government servants added -> clearly relevant exclusion change."""
    doc_old = {
        "filename": "doc_v1.pdf",
        "sha256": "h1",
        "pages": [{"page_number": 1, "text": "All farmers owning cultivable land qualify."}]
    }
    doc_new = {
        "filename": "doc_v2.pdf",
        "sha256": "h2",
        "pages": [{"page_number": 1, "text": "All farmers owning cultivable land qualify. Government servants and pensioners are strictly excluded."}]
    }

    mock_llm = MockLLMClient([{
        "semantic_summary": "Added explicit disqualification for government servants and pensioners.",
        "eligibility_relevance": "clearly_relevant",
        "changes": [{
            "category": "exclusion_related",
            "description": "Government servants and pensioners disqualified",
            "eligibility_relevance": "clearly_relevant",
            "affected_attribute": "government_employee",
            "old_evidence": None,
            "new_evidence": "Government servants and pensioners are strictly excluded."
        }]
    }])

    result = compare_documents(doc_old, doc_new, llm_client=mock_llm, output_dir=tmp_path)
    assert result.eligibility_relevance == "clearly_relevant"
    assert result.semantic_changes[0].category == "exclusion_related"


# ---------------------------------------------------------------------------
# Test Scenario 8: Income threshold changed
# ---------------------------------------------------------------------------
def test_scenario_8_income_threshold_changed(tmp_path):
    """Scenario 8: Income limit increased from 2.5L to 3.0L -> clearly relevant eligibility change."""
    doc_old = {
        "filename": "income_v1.pdf",
        "sha256": "h1",
        "pages": [{"page_number": 1, "text": "Annual family income shall not exceed Rs. 2,50,000."}]
    }
    doc_new = {
        "filename": "income_v2.pdf",
        "sha256": "h2",
        "pages": [{"page_number": 1, "text": "Annual family income shall not exceed Rs. 3,00,000."}]
    }

    mock_llm = MockLLMClient([{
        "semantic_summary": "Income threshold ceiling raised from Rs. 2,50,000 to Rs. 3,00,000.",
        "eligibility_relevance": "clearly_relevant",
        "changes": [{
            "category": "eligibility_related",
            "description": "Annual income ceiling raised to Rs. 3,00,000",
            "eligibility_relevance": "clearly_relevant",
            "affected_attribute": "income",
            "old_evidence": "Annual family income shall not exceed Rs. 2,50,000.",
            "new_evidence": "Annual family income shall not exceed Rs. 3,00,000."
        }]
    }])

    result = compare_documents(doc_old, doc_new, llm_client=mock_llm, output_dir=tmp_path)
    assert result.eligibility_relevance == "clearly_relevant"
    assert result.semantic_changes[0].affected_attribute == "income"


# ---------------------------------------------------------------------------
# Test Scenario 9: Age threshold changed
# ---------------------------------------------------------------------------
def test_scenario_9_age_threshold_changed(tmp_path):
    """Scenario 9: Age requirement changed from 18-60 to 21-65 years -> clearly relevant."""
    doc_old = {
        "filename": "age_v1.pdf",
        "sha256": "h1",
        "pages": [{"page_number": 1, "text": "Applicant must be aged between 18 and 60 years."}]
    }
    doc_new = {
        "filename": "age_v2.pdf",
        "sha256": "h2",
        "pages": [{"page_number": 1, "text": "Applicant must be aged between 21 and 65 years."}]
    }

    mock_llm = MockLLMClient([{
        "semantic_summary": "Age eligibility bracket revised from 18-60 to 21-65 years.",
        "eligibility_relevance": "clearly_relevant",
        "changes": [{
            "category": "eligibility_related",
            "description": "Age eligibility bracket changed to 21-65 years",
            "eligibility_relevance": "clearly_relevant",
            "affected_attribute": "age",
            "old_evidence": "Applicant must be aged between 18 and 60 years.",
            "new_evidence": "Applicant must be aged between 21 and 65 years."
        }]
    }])

    result = compare_documents(doc_old, doc_new, llm_client=mock_llm, output_dir=tmp_path)
    assert result.eligibility_relevance == "clearly_relevant"
    assert result.semantic_changes[0].affected_attribute == "age"


# ---------------------------------------------------------------------------
# Test Scenario 10: Landholding threshold changed
# ---------------------------------------------------------------------------
def test_scenario_10_landholding_threshold_changed(tmp_path):
    """Scenario 10: Land limit expanded from 2.0 Ha to 5.0 Ha -> clearly relevant."""
    doc_old = {
        "filename": "land_v1.pdf",
        "sha256": "h1",
        "pages": [{"page_number": 1, "text": "Eligible farmers owning cultivable land up to 2.0 hectares."}]
    }
    doc_new = {
        "filename": "land_v2.pdf",
        "sha256": "h2",
        "pages": [{"page_number": 1, "text": "Eligible farmers owning cultivable land up to 5.0 hectares."}]
    }

    mock_llm = MockLLMClient([{
        "semantic_summary": "Cultivable land ceiling increased from 2.0 to 5.0 hectares.",
        "eligibility_relevance": "clearly_relevant",
        "changes": [{
            "category": "eligibility_related",
            "description": "Cultivable land ceiling raised to 5.0 hectares",
            "eligibility_relevance": "clearly_relevant",
            "affected_attribute": "landholding",
            "old_evidence": "cultivable land up to 2.0 hectares.",
            "new_evidence": "cultivable land up to 5.0 hectares."
        }]
    }])

    result = compare_documents(doc_old, doc_new, llm_client=mock_llm, output_dir=tmp_path)
    assert result.eligibility_relevance == "clearly_relevant"
    assert result.semantic_changes[0].affected_attribute == "landholding"


# ---------------------------------------------------------------------------
# Test Scenario 11: Administrative instruction changed -> NOT eligibility change
# ---------------------------------------------------------------------------
def test_scenario_11_administrative_instruction_changed(tmp_path):
    """Scenario 11: Application submission office changed -> administrative/procedural, NOT eligibility."""
    doc_old = {
        "filename": "admin_v1.pdf",
        "sha256": "h1",
        "pages": [{"page_number": 1, "text": "Applications shall be submitted to the Assistant Director."}]
    }
    doc_new = {
        "filename": "admin_v2.pdf",
        "sha256": "h2",
        "pages": [{"page_number": 1, "text": "Applications shall be submitted through the designated Taluk office."}]
    }

    # Even if LLM attempted to mark it eligibility_related, quality control overrides to procedural
    mock_llm = MockLLMClient([{
        "semantic_summary": "Application submission office changed to Taluk office.",
        "eligibility_relevance": "none",
        "changes": [{
            "category": "procedural",
            "description": "Application submission location changed",
            "eligibility_relevance": "none",
            "affected_attribute": None,
            "old_evidence": "Applications shall be submitted to the Assistant Director.",
            "new_evidence": "Applications shall be submitted through the designated Taluk office."
        }]
    }])

    result = compare_documents(doc_old, doc_new, llm_client=mock_llm, output_dir=tmp_path)
    assert result.eligibility_relevance == "none"
    assert result.semantic_changes[0].category in ("administrative", "procedural")


# ---------------------------------------------------------------------------
# Test Scenario 12: Notification / amendment statement changed -> NOT eligibility change
# ---------------------------------------------------------------------------
def test_scenario_12_notification_amendment_statement_changed(tmp_path):
    """Scenario 12: Notification status statement updated -> document_status, NOT eligibility."""
    doc_old = {
        "filename": "notif_v1.pdf",
        "sha256": "h1",
        "pages": [{"page_number": 1, "text": "ಉಳಿದಂತೆ ಸದರಿ ಅಧಿಸೂಚನೆಯಲ್ಲಿ ಯಾವುದೇ ಬದಲಾವಣೆ ಇರುವುದಿಲ್ಲ."}]
    }
    doc_new = {
        "filename": "notif_v2.pdf",
        "sha256": "h2",
        "pages": [{"page_number": 1, "text": "ತಿದ್ದುಪಡಿ ಅಧಿಸೂಚನೆ ಹೊರಡಿಸಲಾಗಿದೆ."}]
    }

    mock_llm = MockLLMClient([{
        "semantic_summary": "Notification status updated to indicate amendment issued.",
        "eligibility_relevance": "none",
        "changes": [{
            "category": "document_status",
            "description": "Notification amendment issued statement updated",
            "eligibility_relevance": "none",
            "affected_attribute": None,
            "old_evidence": "ಉಳಿದಂತೆ ಸದರಿ ಅಧಿಸೂಚನೆಯಲ್ಲಿ ಯಾವುದೇ ಬದಲಾವಣೆ ಇರುವುದಿಲ್ಲ.",
            "new_evidence": "ತಿದ್ದುಪಡಿ ಅಧಿಸೂಚನೆ ಹೊರಡಿಸಲಾಗಿದೆ."
        }]
    }])

    result = compare_documents(doc_old, doc_new, llm_client=mock_llm, output_dir=tmp_path)
    assert result.eligibility_relevance == "none"
    assert result.semantic_changes[0].category == "document_status"


# ---------------------------------------------------------------------------
# Test Scenario 13: OCR noise difference -> uncertain/review
# ---------------------------------------------------------------------------
def test_scenario_13_ocr_noise_difference_uncertain_review():
    """Scenario 13: Minor scanning character artifacts -> marked as OCR noise, uncertain/review, no LLM call."""
    doc_old = {
        "filename": "scanned_p1.pdf",
        "sha256": "hash1",
        "pages": [{"page_number": 1, "text": "Karnataka Agriculture Scheme. Small and marginal farmers qualify."}]
    }
    doc_new = {
        "filename": "scanned_p1_rescan.pdf",
        "sha256": "hash2",
        "pages": [{"page_number": 1, "text": "Karnataka Agriculture Scheme.. Small and marginal farmers qualify."}]
    }

    result = deterministic_compare(doc_old, doc_new)
    assert result.hash_status == "different"
    assert result.semantic_comparison_required is False
    assert result.review_required is True
    assert result.eligibility_relevance == "uncertain"
    assert any("OCR scanning noise" in r for r in result.review_reasons)


# ---------------------------------------------------------------------------
# Test Scenario 14: Completely different documents -> review required
# ---------------------------------------------------------------------------
def test_scenario_14_completely_different_documents_review_required():
    """Scenario 14: Comparing unrelated schemes -> flagged as different_document, review required."""
    doc_a = {
        "filename": "pm_kisan_guidelines.pdf",
        "sha256": "hash_a",
        "metadata": {"scheme_name": "PM KISAN Scheme"},
        "pages": [{"page_number": 1, "text": "Pradhan Mantri Kisan Samman Nidhi guidelines for landholding farmers."}]
    }
    doc_b = {
        "filename": "ganga_kalyana_guidelines.pdf",
        "sha256": "hash_b",
        "metadata": {"scheme_name": "Ganga Kalyana Scheme"},
        "pages": [{"page_number": 1, "text": "Irrigation borewell drilling subsidy for minority backward class beneficiaries."}]
    }

    result = deterministic_compare(doc_a, doc_b)
    assert result.overall_status == "different_document"
    assert result.review_required is True
    assert result.eligibility_relevance == "uncertain"
    assert any("completely different" in r for r in result.review_reasons)
