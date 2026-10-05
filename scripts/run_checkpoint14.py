"""
Checkpoint 14 Execution Script: AI Agent Orchestration Pipeline.
Demonstrates autonomous execution of the SchemeAgent on a real Karnataka scheme:
Task: Check Pradhan Mantri Kisan Samman Nidhi (PM-KISAN), verify knowledge base rules,
and update if any new document or rule change exists.
"""

import sys
import json
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

from app.config import LLM_MODEL, setup_logger
from app.db import init_db
from app.agent import SchemeAgent

logger = setup_logger("run_cp14")


def main():
    print("=" * 75)
    print("CHECKPOINT 14: AI AGENT ORCHESTRATION PIPELINE")
    print("=" * 75)

    # Initialize DB tables
    init_db()

    task = (
        "Check configured Karnataka government sources for the scheme 'pradhan-mantri-kisan-samman-nidhi'. "
        "Inspect the current active rules and historical versions in the knowledge base. "
        "If a new document exists, process it and update the knowledge base; if the existing active version "
        "is already up to date, conclude with a summary of the active rules."
    )

    print(f"\n[ORCHESTRATOR] Task given to agent:\n  \"{task}\"\n")
    print(f"Model configured: {LLM_MODEL}")
    print("Starting agent autonomous loop...\n")

    agent = SchemeAgent(model=LLM_MODEL, max_steps=10)
    result = agent.run(task)

    print("\n" + "=" * 75)
    print("AGENT EXECUTION RESULT")
    print("=" * 75)
    print(f"Status:          {result.status.upper()}")
    print(f"Review Required: {result.review_required}")
    if result.review_reasons:
        print(f"Review Reasons:  {result.review_reasons}")
    print(f"Final Answer:    {result.final_answer}")

    print("\n" + "-" * 75)
    print("EXECUTION METRICS")
    print("-" * 75)
    metrics = result.metrics
    print(f"  - Total Steps:            {metrics.total_steps}")
    print(f"  - Successful Tool Calls:  {metrics.successful_tool_calls}")
    print(f"  - Failed Tool Calls:      {metrics.failed_tool_calls}")
    print(f"  - Unnecessary Calls:      {metrics.unnecessary_tool_calls}")
    print(f"  - Tool Success Rate:      {metrics.tool_call_rate * 100:.1f}%")
    print(f"  - End-to-End Success:     {metrics.end_to_end_success}")

    print("\n" + "-" * 75)
    print("CHRONOLOGICAL EXECUTION TRACE")
    print("-" * 75)
    for step in result.trace:
        status_sym = "[OK]" if step.success else "[ERR]"
        print(f"Step {step.step_number} {status_sym} Tool: '{step.tool_name}' ({step.execution_time_ms} ms)")
        print(f"  Thought: {step.thought}")
        print(f"  Args:    {json.dumps(step.arguments)}")
        print(f"  Summary: {step.result_summary}\n")

    print("=" * 75)
    print("CHECKPOINT 14 EXECUTION COMPLETE")
    print("=" * 75)


if __name__ == "__main__":
    main()
