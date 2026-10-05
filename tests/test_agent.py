"""
Comprehensive Test Suite for Checkpoint 14: AI Agent Orchestration.
Covers all 15 required scenarios:
1. Correct tool selection
2. Correct tool sequence
3. Unchanged document stops early
4. New document continues through pipeline
5. Review-required result stops activation
6. Tool failure handling
7. Retry limit
8. Maximum agent steps
9. Invalid tool requested by LLM
10. Invalid tool arguments
11. Correct state propagation
12. Final structured result
13. OCR/document-processing tool is actually reachable
14. Agent does not bypass CP13
15. Agent does not execute arbitrary code
"""

import pytest
import json
from typing import Dict, Any, List, Optional
from unittest.mock import patch, MagicMock

from app.llm_client import LLMClient
from app.agent_schemas import AgentAction, AgentState, AgentResult
from app.agent_tools import TOOL_REGISTRY, execute_tool
from app.agent import SchemeAgent, AGENT_SYSTEM_PROMPT


class MockLLMClient(LLMClient):
    """Mock LLM client returning predetermined JSON payloads for controlled agent testing."""
    def __init__(self, responses: Optional[List[Dict[str, Any]]] = None):
        super().__init__(base_url="http://mock-llm:11434", model="mock-model")
        self.responses = list(responses or [])
        self.call_count = 0

    def _request_raw(self, payload: Dict[str, Any]) -> str:
        self.call_count += 1
        if not self.responses:
            raise ValueError("No mock responses left in queue.")
        resp = self.responses.pop(0)
        if isinstance(resp, Exception):
            raise resp
        if isinstance(resp, str):
            return resp
        return json.dumps(resp)


# ==============================================================================
# TEST 1: Correct Tool Selection
# ==============================================================================
def test_1_correct_tool_selection():
    mock_llm = MockLLMClient([
        {
            "thought": "I need to check configured Karnataka sources first.",
            "action": "discover_sources",
            "arguments": {"active_only": True},
        },
        {
            "thought": "I have found the sources, finishing now.",
            "action": "finish",
            "arguments": {},
            "final_answer": "Discovered trusted government sources.",
        }
    ])
    agent = SchemeAgent(llm_client=mock_llm)
    result = agent.run("Check official scheme sources.")

    assert result.status == "completed"
    assert len(result.trace) == 2
    assert result.trace[0].tool_name == "discover_sources"
    assert result.trace[0].success is True
    assert result.trace[1].tool_name == "finish"


# ==============================================================================
# TEST 2: Correct Tool Sequence
# ==============================================================================
def test_2_correct_tool_sequence():
    mock_llm = MockLLMClient([
        {
            "thought": "Step 1: find sources",
            "action": "discover_sources",
            "arguments": {},
        },
        {
            "thought": "Step 2: get current rules",
            "action": "get_current_rules",
            "arguments": {"scheme_key": "pradhan-mantri-kisan-samman-nidhi"},
        },
        {
            "thought": "Step 3: finish task",
            "action": "finish",
            "arguments": {},
            "final_answer": "Retrieved current rules successfully.",
        }
    ])
    agent = SchemeAgent(llm_client=mock_llm)
    result = agent.run("Inspect scheme rules sequence.")

    assert result.status == "completed"
    tools_called = [step.tool_name for step in result.trace]
    assert tools_called == ["discover_sources", "get_current_rules", "finish"]


# ==============================================================================
# TEST 3: Unchanged Document Stops Early
# ==============================================================================
def test_3_unchanged_document_stops_early():
    doc_hash = "unchanged_hash_12345678"
    initial_state = AgentState(
        scheme_key="pm-kisan",
        previous_version_hash=doc_hash,
    )

    mock_llm = MockLLMClient([
        {
            "thought": "Download the document from URL",
            "action": "download_document",
            "arguments": {"document_url": "https://agri.karnataka.gov.in/test.pdf"},
        },
        {
            "thought": "Document hash matches previous version. No changes detected, concluding without OCR.",
            "action": "finish",
            "arguments": {},
            "final_answer": "Document is unchanged. No OCR or extraction required.",
        }
    ])

    with patch("app.agent_tools.download_file") as mock_dl:
        mock_dl.return_value = {
            "source_url": "https://agri.karnataka.gov.in/test.pdf",
            "file_path": "data/raw/test.pdf",
            "file_name": "test.pdf",
            "file_hash": doc_hash,
            "file_size": 1024,
            "is_pdf": True,
        }
        agent = SchemeAgent(llm_client=mock_llm)
        result = agent.run("Update scheme if changed.", initial_state=initial_state)

    assert result.status == "completed"
    assert result.state.is_unchanged_document is True
    # Verify no OCR or rule extraction tool was called
    called_tools = [s.tool_name for s in result.trace]
    assert "process_document" not in called_tools
    assert "extract_eligibility_rules" not in called_tools
    assert result.metrics.unnecessary_tool_calls == 0


# ==============================================================================
# TEST 4: New Document Continues Through Pipeline
# ==============================================================================
def test_4_new_document_continues_through_pipeline(tmp_path):
    dummy_pdf = tmp_path / "new.pdf"
    dummy_pdf.write_bytes(b"%PDF-1.4 dummy")
    dummy_json = tmp_path / "new.json"
    dummy_json.write_text("{}", encoding="utf-8")

    mock_llm = MockLLMClient([
        {
            "thought": "Download new document",
            "action": "download_document",
            "arguments": {"document_url": "https://agri.karnataka.gov.in/new.pdf"},
        },
        {
            "thought": "Process document layout & OCR",
            "action": "process_document",
            "arguments": {"file_path": str(dummy_pdf)},
        },
        {
            "thought": "Extract eligibility rules",
            "action": "extract_eligibility_rules",
            "arguments": {"structured_json_path": str(dummy_json)},
        },
        {
            "thought": "Update knowledge base",
            "action": "update_knowledge_base",
            "arguments": {
                "scheme_key": "test-farmer-new",
                "scheme_name": "New Farmer Scheme",
                "document_hash": "new_hash_9999",
                "version_label": "2025-v1",
            },
        },
        {
            "thought": "Finish pipeline run",
            "action": "finish",
            "arguments": {},
            "final_answer": "New document processed and persisted.",
        }
    ])

    with patch("app.agent_tools.download_file") as mock_dl, \
         patch("app.agent_tools.process_document_understanding") as mock_proc, \
         patch("app.agent_tools.extract_scheme_rules") as mock_ext, \
         patch("app.agent_tools.apply_knowledge_update") as mock_kb:

        mock_dl.return_value = {
            "source_url": "https://agri.karnataka.gov.in/new.pdf",
            "file_path": str(dummy_pdf),
            "file_name": "new.pdf",
            "file_hash": "new_hash_9999",
            "file_size": 2048,
            "is_pdf": True,
        }
        mock_proc.return_value = {
            "file_name": "new.pdf",
            "total_pages": 1,
            "usable_pages_count": 1,
            "scanned_pages_count": 0,
            "ocr_performed": False,
            "tables_detected_count": 0,
            "structured_json_path": str(dummy_json),
            "full_text": "Sample text",
        }
        mock_ext.return_value = MagicMock(
            model_dump=lambda mode="json": {
                "scheme_name": "New Farmer Scheme",
                "eligibility_rules": [{"rule": "Income under 2L"}],
                "exclusion_rules": [],
                "review_required": False,
                "review_reasons": [],
            }
        )
        mock_kb.return_value = {
            "status": "activated",
            "version_id": 101,
            "version_status": "ACTIVE",
            "action_taken": "activated_new_version",
            "rules_stored": 1,
            "review_required": False,
            "message": "Activated new version",
        }

        agent = SchemeAgent(llm_client=mock_llm)
        result = agent.run("Process new scheme guidelines.")

    assert result.status == "completed"
    assert result.state.current_document_hash == "new_hash_9999"
    assert result.state.processed_document_path == str(dummy_json)
    assert result.metrics.successful_tool_calls == 4


# ==============================================================================
# TEST 5: Review-Required Result Stops Activation
# ==============================================================================
def test_5_review_required_result_stops_activation(tmp_path):
    dummy_json = tmp_path / "ambiguous.json"
    dummy_json.write_text("{}", encoding="utf-8")

    mock_llm = MockLLMClient([
        {
            "thought": "Extract rules from structured document",
            "action": "extract_eligibility_rules",
            "arguments": {"structured_json_path": str(dummy_json)},
        },
        {
            "thought": "Extraction flagged review. Updating KB with force_review=True.",
            "action": "update_knowledge_base",
            "arguments": {
                "scheme_key": "test-ambiguous-scheme",
                "scheme_name": "Ambiguous Scheme",
                "document_hash": "hash_ambig_111",
                "version_label": "2025-review",
                "force_review": True,
            },
        },
        {
            "thought": "Version stored for review. Reporting to user.",
            "action": "finish",
            "arguments": {},
            "final_answer": "Scheme version stored as REVIEW. Human review required.",
        }
    ])

    with patch("app.agent_tools.extract_scheme_rules") as mock_ext, \
         patch("app.agent_tools.apply_knowledge_update") as mock_kb:

        mock_ext.return_value = MagicMock(
            model_dump=lambda mode="json": {
                "scheme_name": "Ambiguous Scheme",
                "eligibility_rules": [{"rule": "Ambiguous discretionary rule"}],
                "exclusion_rules": [],
                "review_required": True,
                "review_reasons": ["Discretionary wording without objective threshold."],
            }
        )
        mock_kb.return_value = {
            "status": "review_stored",
            "version_id": 202,
            "version_status": "REVIEW",
            "action_taken": "stored_for_review",
            "rules_stored": 1,
            "review_required": True,
            "message": "Stored for review",
        }

        agent = SchemeAgent(llm_client=mock_llm)
        result = agent.run("Process ambiguous scheme rules.")

    assert result.status == "review_required"
    assert result.review_required is True
    assert any("Discretionary" in r for r in result.review_reasons)


# ==============================================================================
# TEST 6: Tool Failure Handling
# ==============================================================================
def test_6_tool_failure_handling():
    mock_llm = MockLLMClient([
        {
            "thought": "Attempt to download corrupt URL",
            "action": "download_document",
            "arguments": {"document_url": "https://invalid-host-404.gov.in/missing.pdf"},
        },
        {
            "thought": "Download failed, finishing with error report",
            "action": "finish",
            "arguments": {},
            "final_answer": "Failed to download document from remote source.",
        }
    ])

    with patch("app.agent_tools.download_file", return_value=None):
        agent = SchemeAgent(llm_client=mock_llm)
        result = agent.run("Download scheme file.")

    assert result.review_required is True
    assert result.metrics.failed_tool_calls >= 1
    assert any("Failed to download" in r for r in result.review_reasons)


# ==============================================================================
# TEST 7: Retry Limit
# ==============================================================================
def test_7_retry_limit():
    # Model repeatedly requests the failing tool
    fail_action = {
        "thought": "Retrying download...",
        "action": "download_document",
        "arguments": {"document_url": "https://failing-source.gov.in/err.pdf"},
    }
    mock_llm = MockLLMClient([fail_action, fail_action, fail_action, fail_action])

    with patch("app.agent_tools.download_file", return_value=None):
        agent = SchemeAgent(llm_client=mock_llm)
        result = agent.run("Retry download.")

    assert result.status == "failed"
    assert result.review_required is True
    assert "exceeded retry limit" in result.final_answer


# ==============================================================================
# TEST 8: Maximum Agent Steps
# ==============================================================================
def test_8_maximum_agent_steps():
    # Loop continuously requesting discover_sources without finishing
    mock_llm = MockLLMClient([
        {
            "thought": f"Loop step {i}",
            "action": "discover_sources",
            "arguments": {},
        }
        for i in range(10)
    ])

    agent = SchemeAgent(llm_client=mock_llm, max_steps=3)
    result = agent.run("Continuous loop task.")

    assert result.status == "max_steps_exceeded"
    assert result.review_required is True
    assert len(result.trace) == 3
    assert any("maximum limit of 3 steps" in r for r in result.review_reasons)


# ==============================================================================
# TEST 9: Invalid Tool Requested by LLM
# ==============================================================================
def test_9_invalid_tool_requested_by_llm():
    mock_llm = MockLLMClient([
        {
            "thought": "Try executing an unregistered tool",
            "action": "run_arbitrary_shell_command",
            "arguments": {"cmd": "rm -rf /"},
        },
        {
            "thought": "Unregistered tool was rejected, finishing safely.",
            "action": "finish",
            "arguments": {},
            "final_answer": "Avoided unregistered tool execution.",
        }
    ])

    agent = SchemeAgent(llm_client=mock_llm)
    result = agent.run("Run command task.")

    assert result.review_required is True
    assert any("unregistered tool" in r.lower() for r in result.review_reasons)
    assert result.trace[0].success is False


# ==============================================================================
# TEST 10: Invalid Tool Arguments
# ==============================================================================
def test_10_invalid_tool_arguments():
    # Pass incorrect argument type/name to a tool
    mock_llm = MockLLMClient([
        {
            "thought": "Call tool with bad argument types",
            "action": "download_document",
            "arguments": {"unsupported_param": 123},  # missing required 'document_url'
        },
        {
            "thought": "Finish after bad argument caught",
            "action": "finish",
            "arguments": {},
            "final_answer": "Handled bad arguments gracefully.",
        }
    ])

    agent = SchemeAgent(llm_client=mock_llm)
    result = agent.run("Test invalid arguments.")

    assert result.review_required is True
    assert result.trace[0].success is False
    assert "Invalid arguments" in result.trace[0].error or "required" in result.trace[0].error


# ==============================================================================
# TEST 11: Correct State Propagation
# ==============================================================================
def test_11_correct_state_propagation():
    state = AgentState()
    # Execute tool directly through execute_tool to verify state update logic
    with patch("app.agent_tools.download_file") as mock_dl:
        mock_dl.return_value = {
            "source_url": "https://portal.karnataka.gov.in/doc.pdf",
            "file_path": "data/raw/doc.pdf",
            "file_name": "doc.pdf",
            "file_hash": "hash_propagated_555",
            "file_size": 4096,
            "is_pdf": True,
        }
        res = execute_tool("download_document", {"document_url": "https://portal.karnataka.gov.in/doc.pdf"})

    agent = SchemeAgent()
    agent._update_state_from_tool_output(state, "download_document", {}, res)

    assert state.current_document_path == "data/raw/doc.pdf"
    assert state.current_document_hash == "hash_propagated_555"


# ==============================================================================
# TEST 12: Final Structured Result
# ==============================================================================
def test_12_final_structured_result():
    mock_llm = MockLLMClient([
        {
            "thought": "Immediate completion",
            "action": "finish",
            "arguments": {},
            "final_answer": "All tasks verified.",
        }
    ])
    agent = SchemeAgent(llm_client=mock_llm)
    res = agent.run("Verify completion schema.")

    assert isinstance(res, AgentResult)
    assert res.task == "Verify completion schema."
    assert res.status == "completed"
    assert res.final_answer == "All tasks verified."
    assert isinstance(res.metrics.total_steps, int)
    assert isinstance(res.trace, list)


# ==============================================================================
# TEST 13: OCR / Document-Processing Tool is Actually Reachable
# ==============================================================================
def test_13_ocr_document_processing_tool_is_actually_reachable():
    assert "process_document" in TOOL_REGISTRY
    tool_spec = TOOL_REGISTRY["process_document"]
    assert callable(tool_spec["function"])
    assert "file_path" in tool_spec["parameters"]
    assert "OCR" in tool_spec["description"]


# ==============================================================================
# TEST 14: Agent Does Not Bypass CP13
# ==============================================================================
def test_14_agent_does_not_bypass_cp13():
    # Calling update_knowledge_base must route to CP13 apply_knowledge_update
    with patch("app.agent_tools.apply_knowledge_update") as mock_apply:
        mock_apply.return_value = {
            "status": "activated",
            "version_id": 99,
            "version_status": "ACTIVE",
            "action_taken": "activated_new_version",
            "rules_stored": 0,
            "review_required": False,
            "message": "CP13 update succeeded",
        }
        res = execute_tool(
            "update_knowledge_base",
            {
                "scheme_key": "test-cp13-routing",
                "scheme_name": "CP13 Routing Test",
                "document_hash": "hash_route_123",
                "version_label": "v1",
            }
        )

    assert res["status"] == "success"
    assert res["kb_status"] == "activated"
    assert mock_apply.called


# ==============================================================================
# TEST 15: Agent Does Not Execute Arbitrary Code
# ==============================================================================
def test_15_agent_does_not_execute_arbitrary_code():
    res1 = execute_tool("__import__('os').system('dir')", {})
    assert res1["status"] == "failed"
    assert "not a registered tool" in res1["error"]

    res2 = execute_tool("eval", {"expression": "1 + 1"})
    assert res2["status"] == "failed"
    assert "not a registered tool" in res2["error"]
