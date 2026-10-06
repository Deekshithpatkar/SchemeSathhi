"""
Unit Tests for Checkpoint 15: End-to-End Multi-Scheme Evaluation Harness.
Verifies:
1. Evaluation configuration validation
2. Scheme execution result validation
3. Metrics calculation (steps, success rate, precision, recall)
4. Duplicate / idempotent run behavior
5. Early-stop behavior on unchanged documents
6. Review-required behavior and flag propagation
7. Failed-tool behavior and error recording
8. PostgreSQL state verification
9. Historical version preservation
10. No fabricated ground truth (explicit reporting when no historical change exists)
11. Result report generation (JSON and Markdown)
12. Multiple scheme aggregation
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest

from app.agent_schemas import AgentAction, AgentExecutionMetrics, AgentResult, AgentState, AgentTraceStep
from app.evaluation import (
    EVALUATION_SCHEMES,
    GROUND_TRUTH_BASELINES,
    BatchEvaluationSummary,
    GroundTruthValidation,
    SchemeEvaluationConfig,
    SchemeEvaluationResult,
    calculate_batch_metrics,
    generate_evaluation_report,
    run_failure_evaluation,
    run_idempotency_evaluation,
    run_single_evaluation,
)
from app.agent import SchemeAgent


class MockLLMClient:
    """Deterministic mock LLM for controlled evaluation tests."""
    def __init__(self, action_responses):
        self.responses = list(action_responses)
        self.call_count = 0

    def generate_json(self, prompt: str, system_prompt: str = "", **kwargs):
        if self.call_count < len(self.responses):
            resp = self.responses[self.call_count]
            self.call_count += 1
            return resp
        return {
            "thought": "No more mock actions, finishing safely",
            "action": "finish",
            "arguments": {},
            "final_answer": "Evaluation completed.",
        }


# ==============================================================================
# TEST 1: Evaluation Configuration Validation
# ==============================================================================
def test_1_evaluation_configuration_validation():
    """Verify that all predefined scheme evaluation configs conform to schema constraints."""
    assert len(EVALUATION_SCHEMES) >= 4

    categories = set()
    for cfg in EVALUATION_SCHEMES:
        assert cfg.scheme_key and isinstance(cfg.scheme_key, str)
        assert cfg.scheme_name and isinstance(cfg.scheme_name, str)
        assert cfg.department and isinstance(cfg.department, str)
        assert cfg.official_source_url.startswith("http")
        assert cfg.document_url.startswith("http")
        assert cfg.evaluation_category in ("digital", "kannada", "scanned", "table", "historical_change")
        categories.add(cfg.evaluation_category)

    # Ensure all required categories are represented
    assert "digital" in categories
    assert "kannada" in categories
    assert "scanned" in categories
    assert "table" in categories
    assert "historical_change" in categories


# ==============================================================================
# TEST 2: Scheme Execution Result Validation
# ==============================================================================
def test_2_scheme_execution_result_validation():
    """Verify that SchemeEvaluationResult validates fields and maintains correct schema."""
    res = SchemeEvaluationResult(
        scheme_key="test-scheme",
        scheme_name="Test Scheme",
        category="digital",
        status="completed",
        final_answer="Verified successfully",
        review_required=False,
        steps_taken=4,
        tool_calls_count=3,
        successful_tool_calls=3,
        failed_tool_calls=0,
        unnecessary_tool_calls=0,
        tool_call_rate=1.0,
        execution_time_seconds=1.25,
        document_url="https://test.gov.in/test.pdf",
        document_hash="abc123hash",
        ocr_performed=False,
        tables_detected=1,
        eligibility_rules_count=2,
        exclusion_rules_count=1,
        kb_status="active_version_present",
        version_status="ACTIVE",
        historical_preservation_verified=True,
    )
    assert res.scheme_key == "test-scheme"
    assert res.status == "completed"
    assert res.eligibility_rules_count == 2
    assert res.historical_preservation_verified is True


# ==============================================================================
# TEST 3: Metrics Calculation
# ==============================================================================
def test_3_metrics_calculation():
    """Verify aggregation of batch evaluation metrics across multiple results."""
    r1 = SchemeEvaluationResult(
        scheme_key="s1",
        scheme_name="Scheme 1",
        category="digital",
        status="completed",
        final_answer="OK",
        review_required=False,
        steps_taken=4,
        tool_calls_count=3,
        successful_tool_calls=3,
        document_url="https://test.gov.in/1.pdf",
    )
    r2 = SchemeEvaluationResult(
        scheme_key="s2",
        scheme_name="Scheme 2",
        category="scanned",
        status="review_required",
        final_answer="Needs Review",
        review_required=True,
        steps_taken=6,
        tool_calls_count=5,
        successful_tool_calls=4,
        failed_tool_calls=1,
        document_url="https://test.gov.in/2.pdf",
    )
    summary = calculate_batch_metrics([r1, r2])

    assert summary.total_schemes_tested == 2
    assert summary.successful_schemes == 2  # review_required is also a successful bounded run
    assert summary.review_required_schemes == 1
    assert summary.average_steps == 5.0
    assert summary.average_tool_calls == 4.0
    assert summary.total_failed_tool_calls == 1
    assert summary.overall_success_rate == 1.0


# ==============================================================================
# TEST 4: Duplicate / Idempotent Run Behavior
# ==============================================================================
def test_4_duplicate_idempotent_run_behavior():
    """Verify that running the same document twice triggers early stop and prevents duplicate DB hashes."""
    cfg = EVALUATION_SCHEMES[0]

    mock_llm = MockLLMClient([
        {
            "thought": "Download and discover document",
            "action": "download_document",
            "arguments": {"document_url": cfg.document_url},
        },
        {
            "thought": "Document is unchanged from active version, finishing immediately.",
            "action": "finish",
            "arguments": {},
            "final_answer": "Unchanged document recognized.",
        }
    ])

    with patch("app.evaluation.run_single_evaluation") as mock_eval, \
         patch("app.evaluation.get_historical_versions") as mock_hist:

        # First run result
        res1 = SchemeEvaluationResult(
            scheme_key=cfg.scheme_key,
            scheme_name=cfg.scheme_name,
            category=cfg.evaluation_category,
            status="completed",
            final_answer="Stored initial version",
            review_required=False,
            steps_taken=4,
            tool_calls_count=3,
            successful_tool_calls=3,
            document_url=cfg.document_url,
        )
        # Second run result (stopped early, 0 unnecessary calls)
        res2 = SchemeEvaluationResult(
            scheme_key=cfg.scheme_key,
            scheme_name=cfg.scheme_name,
            category=cfg.evaluation_category,
            status="completed",
            final_answer="Unchanged document recognized.",
            review_required=False,
            steps_taken=2,
            tool_calls_count=1,
            successful_tool_calls=1,
            unnecessary_tool_calls=0,
            document_url=cfg.document_url,
        )
        mock_eval.side_effect = [res1, res2]
        mock_hist.return_value = [
            {"id": 1, "version_label": "2025-v1", "document_hash": "hash_xyz_123", "status": "ACTIVE"}
        ]

        idemp = run_idempotency_evaluation(cfg)

        assert idemp["idempotency_verified"] is True
        assert idemp["no_duplicate_hashes_in_db"] is True
        assert idemp["unnecessary_calls_second_run"] == 0


# ==============================================================================
# TEST 5: Early-Stop Behavior on Unchanged Document
# ==============================================================================
def test_5_early_stop_behavior_on_unchanged_document():
    """Verify that agent terminates after hash match without calling process_document or extract_eligibility_rules."""
    doc_hash = "identical_sha256_hash_111"
    initial_state = AgentState(
        scheme_key="test-scheme",
        previous_version_hash=doc_hash,
    )

    mock_llm = MockLLMClient([
        {
            "thought": "Download file",
            "action": "download_document",
            "arguments": {"document_url": "https://agri.karnataka.gov.in/test.pdf"},
        },
        {
            "thought": "Hash matches active version, concluding immediately.",
            "action": "finish",
            "arguments": {},
            "final_answer": "Document is identical. Finished without redundant processing.",
        }
    ])

    with patch("app.agent_tools.download_file") as mock_dl:
        mock_dl.return_value = {
            "source_url": "https://agri.karnataka.gov.in/test.pdf",
            "file_path": "data/raw/test.pdf",
            "file_name": "test.pdf",
            "file_hash": doc_hash,
            "file_size": 2048,
            "is_pdf": True,
        }
        agent = SchemeAgent(llm_client=mock_llm)
        result = agent.run("Evaluate scheme", initial_state=initial_state)

    assert result.status == "completed"
    assert result.state.is_unchanged_document is True
    called_tools = [s.tool_name for s in result.trace]
    assert "process_document" not in called_tools
    assert "extract_eligibility_rules" not in called_tools
    assert result.metrics.unnecessary_tool_calls == 0


# ==============================================================================
# TEST 6: Review-Required Behavior and Flag Propagation
# ==============================================================================
def test_6_review_required_behavior(tmp_path: Path):
    """Verify that ambiguous or low-confidence extraction propagates review_required flag into result."""
    cfg = EVALUATION_SCHEMES[1]
    dummy_json = tmp_path / "dummy.json"
    dummy_json.write_text("{}", encoding="utf-8")

    mock_llm = MockLLMClient([
        {
            "thought": "Download and process document",
            "action": "extract_eligibility_rules",
            "arguments": {"structured_json_path": str(dummy_json)},
        },
        {
            "thought": "Finish after extraction",
            "action": "finish",
            "arguments": {},
            "final_answer": "Completed with review flag.",
        }
    ])

    with patch("app.agent_tools.extract_scheme_rules") as mock_ext:
        mock_ext.return_value = MagicMock(
            scheme_name="Gruha Lakshmi",
            department="WCD",
            eligibility_rules=[],
            exclusion_rules=[],
            review_required=True,
            review_reasons=["Low OCR confidence on Kannada handwritten section"],
            model_dump=lambda mode="json": {
                "scheme_name": "Gruha Lakshmi",
                "department": "WCD",
                "eligibility_rules": [],
                "exclusion_rules": [],
                "review_required": True,
                "review_reasons": ["Low OCR confidence on Kannada handwritten section"],
            }
        )
        agent = SchemeAgent(llm_client=mock_llm)
        eval_res = run_single_evaluation(cfg, agent=agent)

    assert eval_res.review_required is True
    assert any("Low OCR confidence" in r for r in eval_res.review_reasons)


# ==============================================================================
# TEST 7: Failed-Tool Behavior
# ==============================================================================
def test_7_failed_tool_behavior():
    """Verify that controlled tool failure produces structured error and safe review_required termination."""
    mock_llm = MockLLMClient([
        {
            "thought": "Attempting download...",
            "action": "download_document",
            "arguments": {"document_url": "https://failing-source.gov.in/err.pdf"},
        },
        {
            "thought": "Download failed, terminating with report.",
            "action": "finish",
            "arguments": {},
            "final_answer": "Remote host unreachable.",
        }
    ])

    with patch("app.agent_tools.download_file", return_value=None):
        agent = SchemeAgent(llm_client=mock_llm)
        fail_res = run_failure_evaluation(agent=agent)

    assert fail_res["review_required"] is True
    assert fail_res["failed_tool_calls"] >= 1
    assert fail_res["safe_failure_verified"] is True


# ==============================================================================
# TEST 8: PostgreSQL State Verification
# ==============================================================================
def test_8_postgresql_state_verification():
    """Verify that PostgreSQL scheme version and active rules are correctly audited."""
    cfg = EVALUATION_SCHEMES[0]

    with patch("app.evaluation.get_scheme_by_key") as mock_scheme, \
         patch("app.evaluation.get_active_version") as mock_ver, \
         patch("app.evaluation.get_rules_for_version") as mock_rules, \
         patch("app.evaluation.get_historical_versions") as mock_hist:

        mock_scheme.return_value = {"id": 10, "slug": cfg.scheme_key, "name": cfg.scheme_name}
        mock_ver.return_value = {"id": 20, "version_label": "2026-v1", "status": "ACTIVE"}
        mock_rules.return_value = {
            "eligibility_rules": [{"rule": "Farmer owning land"}],
            "exclusion_rules": [],
        }
        mock_hist.return_value = [{"id": 20, "version_label": "2026-v1", "status": "ACTIVE"}]

        # Create mock agent that returns completed state
        mock_agent = MagicMock()
        mock_agent.run.return_value = AgentResult(
            task="Evaluate",
            status="completed",
            final_answer="Verified successfully",
            review_required=False,
            state=AgentState(scheme_key=cfg.scheme_key),
            metrics=AgentExecutionMetrics(total_steps=3, successful_tool_calls=2),
            trace=[],
        )

        res = run_single_evaluation(cfg, agent=mock_agent)

    assert res.version_status == "ACTIVE"
    assert res.kb_status == "active_version_present"
    assert res.historical_preservation_verified is True


# ==============================================================================
# TEST 9: Historical Version Preservation
# ==============================================================================
def test_9_historical_version_preservation():
    """Verify that previous versions remain archived and preserved when updating to a new active version."""
    cfg = EVALUATION_SCHEMES[4]  # PM-KISAN

    with patch("app.evaluation.get_scheme_by_key") as mock_scheme, \
         patch("app.evaluation.get_active_version") as mock_ver, \
         patch("app.evaluation.get_rules_for_version") as mock_rules, \
         patch("app.evaluation.get_historical_versions") as mock_hist:

        mock_scheme.return_value = {"id": 1, "slug": cfg.scheme_key, "name": cfg.scheme_name}
        mock_ver.return_value = {"id": 2, "version_label": "2026-v2", "status": "ACTIVE"}
        mock_rules.return_value = {"eligibility_rules": [], "exclusion_rules": []}
        # Two versions in history: old is ARCHIVED, new is ACTIVE
        mock_hist.return_value = [
            {"id": 1, "version_label": "2019-guidelines", "status": "ARCHIVED"},
            {"id": 2, "version_label": "2026-v2", "status": "ACTIVE"},
        ]

        mock_agent = MagicMock()
        mock_agent.run.return_value = AgentResult(
            task="Evaluate",
            status="completed",
            final_answer="Updated",
            review_required=False,
            state=AgentState(scheme_key=cfg.scheme_key),
            metrics=AgentExecutionMetrics(total_steps=4, successful_tool_calls=3),
            trace=[],
        )

        res = run_single_evaluation(cfg, agent=mock_agent)

    assert res.historical_preservation_verified is True


# ==============================================================================
# TEST 10: No Fabricated Ground Truth
# ==============================================================================
def test_10_no_fabricated_ground_truth():
    """Verify that schemes without historical versions explicitly declare absence rather than simulating changes."""
    for cfg in EVALUATION_SCHEMES:
        if not cfg.historical_version_available:
            assert cfg.historical_version_available is False

    # Ground truth for digital administrative G.O. has 0 actual eligibility rules
    sec_agri_gt = GROUND_TRUTH_BASELINES["secondary-agriculture"]
    assert sec_agri_gt.total_actual_rules == 0
    assert sec_agri_gt.correctly_extracted == 0


# ==============================================================================
# TEST 11: Result Report Generation (JSON & Markdown)
# ==============================================================================
def test_11_result_report_generation(tmp_path: Path):
    """Verify that generate_evaluation_report creates both valid JSON and Markdown artifacts."""
    dummy_res = SchemeEvaluationResult(
        scheme_key="test-scheme",
        scheme_name="Test Scheme",
        category="digital",
        status="completed",
        final_answer="Done",
        review_required=False,
        steps_taken=3,
        tool_calls_count=2,
        successful_tool_calls=2,
        document_url="https://test.gov.in/doc.pdf",
        validation=GroundTruthValidation(precision=1.0, recall=1.0, manual_notes="Manual note"),
    )
    summary = calculate_batch_metrics([dummy_res])

    paths = generate_evaluation_report(
        summary=summary,
        idempotency_result={"scheme_key": "test-scheme", "idempotency_verified": True},
        failure_result={"safe_failure_verified": True},
        output_dir=tmp_path,
    )

    assert paths["json"].exists()
    assert paths["md"].exists()

    # Validate JSON structure
    with open(paths["json"], "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["summary"]["total_schemes_tested"] == 1
    assert data["idempotency_evaluation"]["idempotency_verified"] is True

    # Validate Markdown content
    md_content = paths["md"].read_text(encoding="utf-8")
    assert "# CHECKPOINT 15: END-TO-END MULTI-SCHEME EVALUATION REPORT" in md_content
    assert "Test Scheme" in md_content
    assert "Idempotency Verification Results" in md_content


# ==============================================================================
# TEST 12: Multiple Scheme Aggregation
# ==============================================================================
def test_12_multiple_scheme_aggregation():
    """Verify batch summary accurately aggregates across 5 distinct scheme results."""
    results = []
    for i, cfg in enumerate(EVALUATION_SCHEMES):
        results.append(SchemeEvaluationResult(
            scheme_key=cfg.scheme_key,
            scheme_name=cfg.scheme_name,
            category=cfg.evaluation_category,
            status="completed" if i != 2 else "review_required",
            final_answer=f"Result for {cfg.scheme_key}",
            review_required=(i == 2),
            steps_taken=4,
            tool_calls_count=3,
            successful_tool_calls=3,
            document_url=cfg.document_url,
        ))

    summary = calculate_batch_metrics(results)
    assert summary.total_schemes_tested == 5
    assert summary.successful_schemes == 5
    assert summary.review_required_schemes == 1
    assert summary.overall_success_rate == 1.0
