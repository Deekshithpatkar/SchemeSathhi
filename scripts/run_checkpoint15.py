"""
Checkpoint 15 Execution Script: End-to-End Multi-Scheme Evaluation.
Runs the real SchemeAgent across 5 diverse, authentic Karnataka government schemes
representing digital text, scanned Kannada OCR, table structures, and genuine policy extensions.

Produces:
- data/evaluations/checkpoint15_report.json
- data/evaluations/checkpoint15_report.md
"""

import sys
import json
import time
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.config import LLM_MODEL, setup_logger
from app.db import init_db
from app.registry import add_source
from app.agent import SchemeAgent
from app.evaluation import (
    EVALUATION_SCHEMES,
    run_single_evaluation,
    run_idempotency_evaluation,
    run_failure_evaluation,
    calculate_batch_metrics,
    generate_evaluation_report,
)

logger = setup_logger("run_cp15")


def seed_evaluation_sources():
    """Ensures official Karnataka sources for evaluated schemes are present in source_registry."""
    sources = [
        ("Raitha Mitra Karnataka", "https://raitamitra.karnataka.gov.in", "Agriculture Department", "scheme_portal"),
        ("Raitha Mitra Scheme Orders", "https://raitamitra.karnataka.gov.in/127/government-order%28schemes%29/kn", "Agriculture Department", "scheme_portal"),
        ("Gruha Lakshmi Scheme / WCD", "https://wcd.karnataka.gov.in", "Women and Child Development Department", "scheme_page"),
        ("Gruha Jyothi Scheme", "https://energy.karnataka.gov.in", "Energy Department", "scheme_page"),
        ("Ahara Karnataka / Anna Bhagya", "https://ahara.kar.nic.in", "Food, Civil Supplies & Consumer Affairs", "scheme_portal"),
    ]
    for s_name, s_url, s_dept, s_type in sources:
        try:
            add_source(source_name=s_name, official_url=s_url, department=s_dept, source_type=s_type)
        except Exception as e:
            logger.warning(f"Error seeding source {s_name}: {e}")


def main():
    print("=" * 80)
    print("CHECKPOINT 15: END-TO-END MULTI-SCHEME EVALUATION")
    print("=" * 80)
    print(f"Model: {LLM_MODEL}")
    print(f"Date:  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)

    # 1. Initialize DB and seed registry
    init_db()
    seed_evaluation_sources()

    results = []
    print(f"\nEvaluating {len(EVALUATION_SCHEMES)} Genuine Karnataka Government Schemes...\n")

    # 2. Run real agent on each scheme
    for i, cfg in enumerate(EVALUATION_SCHEMES, 1):
        print("-" * 80)
        print(f"[{i}/{len(EVALUATION_SCHEMES)}] SCHEME: {cfg.scheme_name} ({cfg.scheme_key})")
        print(f"  Category:        {cfg.evaluation_category.upper()}")
        print(f"  Department:      {cfg.department}")
        print(f"  Official Source: {cfg.official_source_url}")
        print(f"  Document Target: {cfg.document_url}")
        print(f"  Characteristics: {cfg.expected_characteristics}")
        print("-" * 80)

        agent = SchemeAgent(model=LLM_MODEL, max_steps=10)
        res = run_single_evaluation(cfg, agent=agent)
        results.append(res)

        print(f"  -> Outcome:     {res.status.upper()}")
        print(f"  -> Steps Taken: {res.steps_taken} (Tool calls: {res.tool_calls_count}, Rate: {res.tool_call_rate * 100:.1f}%)")
        print(f"  -> OCR Used:    {res.ocr_performed} | Tables: {res.tables_detected}")
        print(f"  -> Rules:       Eligibility: {res.eligibility_rules_count}, Exclusion: {res.exclusion_rules_count}")
        print(f"  -> KB Status:   {res.kb_status} (Version: {res.version_status})")
        print(f"  -> Runtime:     {res.execution_time_seconds:.1f}s")
        print(f"  -> Answer:      {res.final_answer}\n")

    # 3. Run Idempotency Test on PM-KISAN
    print("=" * 80)
    print("RUNNING IDEMPOTENCY EVALUATION (Same document executed twice)")
    print("=" * 80)
    target_idemp_cfg = EVALUATION_SCHEMES[0]  # secondary-agriculture (clean unchanged early stop)
    idemp_result = run_idempotency_evaluation(target_idemp_cfg)
    print(f"  Scheme:              {idemp_result['scheme_key']}")
    print(f"  Idempotency Result:  {'PASSED' if idemp_result['idempotency_verified'] else 'FAILED'}")
    print(f"  No Duplicate Hashes: {idemp_result['no_duplicate_hashes_in_db']}")
    print(f"  Unnecessary Calls:   {idemp_result['unnecessary_calls_second_run']}")
    print(f"  Summary:             {idemp_result['message']}\n")

    # 4. Run Controlled Failure Test
    print("=" * 80)
    print("RUNNING CONTROLLED FAILURE TEST (Unreachable remote URL)")
    print("=" * 80)
    fail_result = run_failure_evaluation()
    print(f"  Outcome:             {fail_result['status'].upper()}")
    print(f"  Review Required:     {fail_result['review_required']}")
    print(f"  Failed Tool Calls:   {fail_result['failed_tool_calls']}")
    print(f"  DB Safe Integrity:   {fail_result['db_integrity_preserved']}")
    print(f"  Safety Verified:     {'PASSED' if fail_result['safe_failure_verified'] else 'FAILED'}\n")

    # 5. Calculate Batch Metrics
    summary = calculate_batch_metrics(results)

    # 6. Generate JSON and Markdown Reports
    report_paths = generate_evaluation_report(
        summary=summary,
        idempotency_result=idemp_result,
        failure_result=fail_result,
        output_dir=Path("data/evaluations"),
    )

    print("=" * 80)
    print("EVALUATION MATRIX SUMMARY")
    print("=" * 80)
    print(f"{'Scheme':<32} {'Category':<15} {'Status':<12} {'Rules (El/Ex)':<14} {'Review':<8} {'KB Update'}")
    print("-" * 80)
    for r in summary.results:
        rules_str = f"{r.eligibility_rules_count}/{r.exclusion_rules_count}"
        rev_str = "YES" if r.review_required else "No"
        print(f"{r.scheme_name[:30]:<32} {r.category:<15} {r.status.upper():<12} {rules_str:<14} {rev_str:<8} {r.kb_status}")

    print("\n" + "=" * 80)
    print("OVERALL METRICS")
    print("=" * 80)
    print(f"  Total Schemes Evaluated:   {summary.total_schemes_tested}")
    print(f"  Successful Schemes:        {summary.successful_schemes}")
    print(f"  Failed Schemes:            {summary.failed_schemes}")
    print(f"  Review Required Cases:     {summary.review_required_schemes}")
    print(f"  Average Steps Taken:       {summary.average_steps}")
    print(f"  Average Tool Calls:        {summary.average_tool_calls}")
    print(f"  Total Unnecessary Calls:   {summary.total_unnecessary_calls}")
    print(f"  Overall Success Rate:      {summary.overall_success_rate * 100:.1f}%")
    print(f"\nReports saved to:")
    print(f"  JSON: {report_paths['json']}")
    print(f"  MD:   {report_paths['md']}")
    print("=" * 80)
    print("CHECKPOINT 15 COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    main()
