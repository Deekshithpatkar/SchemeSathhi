"""
Checkpoint 14: AI Agent Orchestration Module.
Intelligently orchestrates discovery, downloading, document understanding,
semantic rule extraction, document/rule comparison, and PostgreSQL persistence.

Key Invariants:
1. Agent decides; registered tools execute.
2. No arbitrary code execution.
3. Early stopping on unchanged documents (avoiding redundant OCR/extraction).
4. Preserves CP13 review flags (no forced activation when uncertain).
5. Comprehensive execution trace and performance metrics.
"""

import time
import json
from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timezone

from app.config import setup_logger, LLM_MODEL
from app.llm_client import LLMClient
from app.agent_schemas import (
    AgentAction,
    AgentTraceStep,
    AgentState,
    AgentExecutionMetrics,
    AgentResult,
)
from app.agent_tools import TOOL_REGISTRY, execute_tool

logger = setup_logger("agent")

MAX_AGENT_STEPS = 15
MAX_TOOL_RETRIES = 2

AGENT_SYSTEM_PROMPT = """You are the Karnataka Government Scheme Intelligence Orchestrator Agent.
Your objective is to inspect trusted Karnataka government scheme sources, discover documents, download them, understand policies, extract candidate eligibility/exclusion rules, and persist validated updates to the knowledge base.

You have access to a specific suite of registered tools. You MUST NOT invent tool names, run raw Python/shell code, or bypass validation.

CRITICAL ORCHESTRATION RULES:
1. WORKFLOW & TOOL ORDER:
   - Call 'discover_sources' or 'get_current_rules' to retrieve official URLs and existing scheme keys. NEVER fabricate or invent URLs or scheme keys.
   - When calling 'discover_documents', always provide the official URL returned by 'discover_sources'.
   - When calling 'get_current_rules' or 'get_historical_versions', provide the scheme_key from the task or state.
2. EFFICIENCY & REASONED EARLY STOPPING:
   - If a downloaded document has the exact same SHA-256 hash as an existing active version, the document is UNCHANGED. Conclude immediately and call 'finish'. DO NOT run expensive OCR, rule extraction, or database updates on unchanged documents!
3. HUMAN REVIEW SAFETY:
   - If extraction or rule comparison indicates 'review_required' or 'uncertain' relevance, store the update with force_review=True in update_knowledge_base. DO NOT attempt to force active status.
   - When finished, summarize the review reasons clearly.
4. STRUCTURED ACTION FORMAT:
   On every turn, you MUST return a valid JSON object matching this schema:
   {
       "thought": "Your step-by-step reasoning explaining why this tool is needed or why you are finishing.",
       "action": "<tool_name>" OR "finish",
       "arguments": { "<arg_name>": <value> },
       "final_answer": "Final conclusion summary (ONLY if action is 'finish')"
   }
"""


class SchemeAgent:
    """
    Autonomous orchestration agent managing the lifecycle of Karnataka scheme updates.
    """
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        model: Optional[str] = None,
        max_steps: int = MAX_AGENT_STEPS,
    ):
        self.active_model = model or LLM_MODEL
        self.llm_client = llm_client or LLMClient(model=self.active_model)
        self.max_steps = max_steps

    def _build_tools_description(self) -> str:
        """Formats the registered tools and their parameters for LLM context."""
        lines = []
        for name, spec in TOOL_REGISTRY.items():
            lines.append(f"- **{name}**: {spec['description']}")
            params = spec.get("parameters", {})
            for p_name, p_desc in params.items():
                lines.append(f"    * `{p_name}`: {p_desc}")
        return "\n".join(lines)

    def _build_agent_prompt(
        self,
        task: str,
        state: AgentState,
        trace: List[AgentTraceStep],
    ) -> str:
        """Constructs the prompt for the next agent decision step."""
        tools_desc = self._build_tools_description()

        history_lines = []
        for step in trace:
            status_str = "SUCCESS" if step.success else f"FAILED: {step.error}"
            history_lines.append(
                f"Step {step.step_number} [{step.tool_name}] -> {status_str}\n"
                f"  Thought: {step.thought}\n"
                f"  Args: {json.dumps(step.arguments)}\n"
                f"  Result: {step.result_summary}"
            )
        history_text = "\n\n".join(history_lines) if history_lines else "No previous actions taken."

        state_summary = {
            "scheme_key": state.scheme_key,
            "source_url": state.source_url,
            "current_document_url": state.current_document_url,
            "current_document_hash": state.current_document_hash,
            "is_unchanged_document": state.is_unchanged_document,
            "processed_document_path": state.processed_document_path,
            "review_required": state.review_required,
            "review_reasons": state.review_reasons,
        }

        prompt = f"""### TASK:
{task}

### AVAILABLE TOOLS:
{tools_desc}

### CURRENT AGENT STATE:
{json.dumps(state_summary, indent=2)}

### EXECUTION HISTORY:
{history_text}

### NEXT ACTION:
Decide the next single action. Return ONLY valid JSON matching the AgentAction schema.
"""
        return prompt

    def run(
        self,
        task: str,
        initial_state: Optional[AgentState] = None,
    ) -> AgentResult:
        """
        Executes the autonomous agent loop until the objective is completed,
        an error terminates the run, or the step limit is exceeded.
        """
        logger.info(f"Agent starting task: '{task}'")
        state = initial_state or AgentState()
        trace: List[AgentTraceStep] = []

        successful_tool_calls = 0
        failed_tool_calls = 0
        unnecessary_tool_calls = 0
        tool_failure_counts: Dict[str, int] = {}

        step_count = 0
        final_answer = ""
        run_status = "completed"

        while step_count < self.max_steps and not state.completed:
            step_count += 1
            logger.info(f"--- Agent Step {step_count}/{self.max_steps} ---")

            prompt = self._build_agent_prompt(task, state, trace)

            # Invoke LLM for structured decision
            try:
                raw_decision = self.llm_client.generate_json(
                    prompt=prompt,
                    system_prompt=AGENT_SYSTEM_PROMPT,
                    temperature=0.0,
                    max_retries=2,
                )
                action = AgentAction.model_validate(raw_decision)
            except Exception as e:
                logger.error(f"Agent failed to parse action decision from LLM: {e}")
                failed_tool_calls += 1
                state.review_required = True
                state.review_reasons.append(f"LLM decision parsing failed: {e}")
                trace.append(AgentTraceStep(
                    step_number=step_count,
                    thought="Failed to produce valid structured JSON action.",
                    tool_name="llm_decision",
                    arguments={},
                    success=False,
                    execution_time_ms=0.0,
                    result_summary="Invalid JSON action decision from LLM.",
                    error=str(e),
                ))
                run_status = "failed"
                final_answer = f"Agent failed due to invalid decision parsing: {e}"
                break

            logger.info(f"Step {step_count} Decision: Action='{action.action}', Thought='{action.thought}'")

            # Case A: Agent decides task is complete
            if action.action.lower() == "finish":
                state.completed = True
                final_answer = action.final_answer or action.thought or "Task finished successfully."
                state.final_answer = final_answer
                trace.append(AgentTraceStep(
                    step_number=step_count,
                    thought=action.thought,
                    tool_name="finish",
                    arguments=action.arguments,
                    success=True,
                    execution_time_ms=0.0,
                    result_summary=final_answer,
                ))
                break

            # Case B: Unregistered tool requested
            if action.action not in TOOL_REGISTRY:
                logger.warning(f"Agent requested unregistered tool: '{action.action}'")
                failed_tool_calls += 1
                state.review_required = True
                state.review_reasons.append(f"Requested unregistered tool: '{action.action}'")
                trace.append(AgentTraceStep(
                    step_number=step_count,
                    thought=action.thought,
                    tool_name=action.action,
                    arguments=action.arguments,
                    success=False,
                    execution_time_ms=0.0,
                    result_summary=f"Unregistered tool '{action.action}'.",
                    error=f"Tool '{action.action}' is not in the central tool registry.",
                ))
                continue

            # Case C: Check for unnecessary tool calls
            # e.g., calling OCR or rule extraction after document is proven unchanged
            if state.is_unchanged_document and action.action in ("process_document", "extract_eligibility_rules", "compare_rules"):
                logger.warning(f"Unnecessary tool call detected: '{action.action}' after document proven unchanged.")
                unnecessary_tool_calls += 1

            # Case D: Execute registered tool
            tool_name = action.action
            t_start = time.perf_counter()
            tool_result = execute_tool(tool_name, action.arguments)
            t_duration_ms = round((time.perf_counter() - t_start) * 1000, 2)

            is_success = tool_result.get("status") != "failed"

            if is_success:
                successful_tool_calls += 1
                # Update structured state based on tool outputs
                self._update_state_from_tool_output(state, tool_name, action.arguments, tool_result)
                summary_text = self._summarize_tool_result(tool_name, tool_result)
                err_text = None
            else:
                failed_tool_calls += 1
                err_text = tool_result.get("error", "Unknown tool error")
                summary_text = f"Tool failed: {err_text}"
                state.review_required = True
                state.review_reasons.append(f"Tool '{tool_name}' failed: {err_text}")

                # Retry tracking
                tool_failure_counts[tool_name] = tool_failure_counts.get(tool_name, 0) + 1
                if tool_failure_counts[tool_name] > MAX_TOOL_RETRIES:
                    logger.error(f"Tool '{tool_name}' exceeded retry limit ({MAX_TOOL_RETRIES}). Aborting run.")
                    run_status = "failed"
                    final_answer = f"Agent aborted: tool '{tool_name}' exceeded retry limit (failed {tool_failure_counts[tool_name]} times)."
                    trace.append(AgentTraceStep(
                        step_number=step_count,
                        thought=action.thought,
                        tool_name=tool_name,
                        arguments=action.arguments,
                        success=False,
                        execution_time_ms=t_duration_ms,
                        result_summary=summary_text,
                        error=err_text,
                    ))
                    break

            trace.append(AgentTraceStep(
                step_number=step_count,
                thought=action.thought,
                tool_name=tool_name,
                arguments=action.arguments,
                success=is_success,
                execution_time_ms=t_duration_ms,
                result_summary=summary_text,
                error=err_text,
            ))

        # Check loop termination conditions
        if step_count >= self.max_steps and not state.completed:
            logger.warning(f"Agent reached maximum allowed steps ({self.max_steps}). Forcing stop with review required.")
            run_status = "max_steps_exceeded"
            state.review_required = True
            state.review_reasons.append(f"Execution reached maximum limit of {self.max_steps} steps without completion.")
            final_answer = f"Agent stopped: maximum step limit ({self.max_steps}) exceeded."
            state.final_answer = final_answer

        if state.review_required and run_status == "completed":
            run_status = "review_required"

        total_tool_attempts = successful_tool_calls + failed_tool_calls
        tool_call_rate = round(successful_tool_calls / total_tool_attempts, 2) if total_tool_attempts > 0 else 1.0

        metrics = AgentExecutionMetrics(
            total_steps=step_count,
            successful_tool_calls=successful_tool_calls,
            failed_tool_calls=failed_tool_calls,
            unnecessary_tool_calls=unnecessary_tool_calls,
            tool_call_rate=tool_call_rate,
            end_to_end_success=(run_status in ("completed", "review_required")),
            review_required=state.review_required,
        )

        return AgentResult(
            task=task,
            status=run_status,
            final_answer=final_answer or state.final_answer or "Agent execution finished.",
            review_required=state.review_required,
            review_reasons=list(dict.fromkeys(state.review_reasons)),
            state=state,
            metrics=metrics,
            trace=trace,
        )

    def _update_state_from_tool_output(
        self,
        state: AgentState,
        tool_name: str,
        arguments: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        """Synchronizes AgentState with verified outputs from specific tools."""
        if tool_name == "discover_sources":
            sources = result.get("sources", [])
            if sources and not state.source_url:
                state.source_url = sources[0].get("official_url")

        elif tool_name == "discover_documents":
            docs = result.get("documents", [])
            if docs and not state.current_document_url:
                state.current_document_url = docs[0].get("document_url")
                if docs[0].get("scheme_name") and not state.scheme_name:
                    state.scheme_name = docs[0]["scheme_name"]

        elif tool_name == "download_document":
            state.current_document_path = result.get("file_path")
            state.current_document_hash = result.get("file_hash")
            # If previous active version is already known, check for identical hash
            if state.previous_version_hash and state.current_document_hash:
                if state.previous_version_hash == state.current_document_hash:
                    state.is_unchanged_document = True

        elif tool_name == "process_document":
            state.processed_document_path = result.get("structured_json_path")

        elif tool_name == "extract_eligibility_rules":
            state.current_extraction = result.get("extraction_data")
            if result.get("review_required"):
                state.review_required = True
                state.review_reasons.extend(result.get("review_reasons", []))

        elif tool_name == "compare_documents":
            state.document_comparison = result.get("comparison_data")
            if result.get("hash_status") == "identical":
                state.is_unchanged_document = True
            if result.get("review_required"):
                state.review_required = True

        elif tool_name == "compare_rules":
            state.rule_comparison = result.get("comparison_data")
            if result.get("review_required") or result.get("eligibility_relevance") == "uncertain":
                state.review_required = True
                state.review_reasons.extend(result.get("review_reasons", []))

        elif tool_name == "update_knowledge_base":
            state.knowledge_base_update = result
            if result.get("kb_status") == "already_exists":
                state.is_unchanged_document = True
            if result.get("version_status") == "REVIEW" or result.get("review_required"):
                state.review_required = True

        elif tool_name == "get_current_rules":
            if result.get("scheme_name") and not state.scheme_name:
                state.scheme_name = result["scheme_name"]
            if result.get("document_hash") and not state.previous_version_hash:
                state.previous_version_hash = result["document_hash"]

        elif tool_name == "get_historical_versions":
            versions = result.get("versions", [])
            for v in versions:
                if v.get("status") == "ACTIVE" and v.get("document_hash"):
                    state.previous_version_hash = v["document_hash"]
                    break

    def _summarize_tool_result(self, tool_name: str, result: Dict[str, Any]) -> str:
        """Constructs a concise summary string for trace logging."""
        if tool_name == "discover_sources":
            return f"Found {result.get('sources_count', 0)} registered sources."
        if tool_name == "discover_documents":
            return f"Discovered {result.get('documents_count', 0)} relevant documents."
        if tool_name == "download_document":
            return f"Downloaded {result.get('file_name')} (Hash: {str(result.get('file_hash'))[:10]}..., Size: {result.get('file_size')} bytes)."
        if tool_name == "process_document":
            return f"Processed {result.get('total_pages')} pages (OCR pages: {result.get('scanned_pages_count')}, Tables: {result.get('tables_detected_count')})."
        if tool_name == "extract_eligibility_rules":
            return f"Extracted {result.get('eligibility_rules_count')} eligibility rules and {result.get('exclusion_rules_count')} exclusion rules."
        if tool_name == "compare_documents":
            return f"Comparison: Status='{result.get('overall_status')}', Relevance='{result.get('eligibility_relevance')}'."
        if tool_name == "compare_rules":
            return f"Rule comparison: {result.get('summary')} (Relevance: {result.get('eligibility_relevance')})."
        if tool_name == "update_knowledge_base":
            return f"Knowledge base: Status='{result.get('kb_status')}', Version='{result.get('version_status')}', Action='{result.get('action_taken')}'."
        if tool_name == "get_current_rules":
            if result.get("status") == "not_found":
                return result.get("message", "Scheme not found in knowledge base.")
            return f"Scheme '{result.get('scheme_key')}': Active version '{result.get('active_version')}' with {result.get('eligibility_rules_count')} eligibility rules (Hash: {str(result.get('document_hash'))[:10]}...)."
        if tool_name == "get_historical_versions":
            return f"Found {result.get('versions_count')} historical versions."
        return str(result)[:200]
