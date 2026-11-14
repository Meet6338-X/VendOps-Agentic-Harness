import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from evals.run_eval import execute_evaluation


def run_release_gate(
    dataset_path: Path | str = "evals/datasets/disputes_400.jsonl",
    max_entity_wer: float = 0.030,
    min_worst_slice_tcr: float = 0.850,
    max_hallucinations: int = 0,
    output_json: Path | str = "evals/results/release_gate_summary.json",
) -> int:
    """Run release gate evaluation and return exit code (0 = pass, 1 = fail)."""
    reconfigure_fn = getattr(sys.stdout, "reconfigure", None)
    if reconfigure_fn is not None:
        try:
            reconfigure_fn(encoding="utf-8")
        except (AttributeError, OSError):
            pass

    print("=" * 70)
    print("VENDOPS AGENTIC HARNESS - RELEASE GATE VERIFICATION")
    print("=" * 70)
    print(f"Dataset: {dataset_path}")
    print("Gate Thresholds:")
    print(f"  - Overall Entity-WER: <= {max_entity_wer:.2%}")
    print(f"  - Worst-Slice TCR:    >= {min_worst_slice_tcr:.2%}")
    print(f"  - Hallucinated ERP IDs: == {max_hallucinations}")
    print("-" * 70)

    report, _, _, _ = execute_evaluation(
        dataset_path=dataset_path
    )

    failures: list[str] = []

    # 1. Entity-WER Check
    if report.overall_wer > max_entity_wer:
        failures.append(
            f"Overall Entity-WER failed: {report.overall_wer:.2%} > threshold {max_entity_wer:.2%}"
        )

    # 2. Worst-Slice TCR Check
    if report.worst_slice_tcr < min_worst_slice_tcr:
        failures.append(
            f"Worst-slice TCR failed: {report.worst_slice_tcr:.2%} < threshold {min_worst_slice_tcr:.2%} "
            f"(Slice: {report.worst_tcr_slice_name})"
        )

    # 3. Hallucination Check
    if report.hallucinated_erp_tool_calls > max_hallucinations:
        failures.append(
            f"Hallucinated tool calls reaching ERP failed: {report.hallucinated_erp_tool_calls} > {max_hallucinations}"
        )

    gate_passed = len(failures) == 0

    print("RELEASE GATE RESULTS:")
    print(f"  - Total Cases:          {report.total_cases}")
    print(f"  - Overall TCR:          {report.overall_tcr:.2%}")
    print(f"  - Overall Entity-WER:   {report.overall_wer:.2%} "
          f"({'PASS' if report.overall_wer <= max_entity_wer else 'FAIL'})")
    print(f"  - Worst-Slice TCR:      {report.worst_slice_tcr:.2%} "
          f"({'PASS' if report.worst_slice_tcr >= min_worst_slice_tcr else 'FAIL'}) [{report.worst_tcr_slice_name}]")
    print(f"  - Worst-Slice WER:      {report.worst_slice_wer:.2%} [{report.worst_wer_slice_name}]")
    print(f"  - ERP Hallucinations:   {report.hallucinated_erp_tool_calls} "
          f"({'PASS' if report.hallucinated_erp_tool_calls <= max_hallucinations else 'FAIL'})")
    print(f"  - Handling Time Saved:  {report.handling_time_reduction_pct:.1f}%")
    print(f"  - Token Savings:        {report.ablation['token_reduction_pct']:.1f}%")
    print(f"  - Latency Speedup:      {report.ablation['latency_speedup_ms']:.1f} ms")
    print("-" * 70)

    summary_data = {
        "gate_passed": gate_passed,
        "failures": failures,
        "report": asdict(report),
        "thresholds": {
            "max_entity_wer": max_entity_wer,
            "min_worst_slice_tcr": min_worst_slice_tcr,
            "max_hallucinations": max_hallucinations,
        },
    }

    out_p = Path(output_json)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text(json.dumps(summary_data, indent=2), encoding="utf-8")

    if gate_passed:
        print("[SUCCESS] ALL RELEASE GATES PASSED. Qualification approved.")
        print("=" * 70)
        return 0
    else:
        print("[FAILURE] RELEASE GATE VIOLATIONS:")
        for fail_msg in failures:
            print(f"  [X] {fail_msg}")
        print("=" * 70)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="VendOps Release Gate Verification CLI")
    parser.add_argument(
        "--dataset",
        default="evals/datasets/disputes_400.jsonl",
        help="Path to evaluation dataset JSONL",
    )
    parser.add_argument(
        "--max-entity-wer",
        type=float,
        default=0.030,
        help="Maximum allowed Entity-WER (default: 0.030 / 3.0%)",
    )
    parser.add_argument(
        "--min-worst-slice-tcr",
        type=float,
        default=0.850,
        help="Minimum allowed worst-slice TCR (default: 0.850 / 85.0%)",
    )
    parser.add_argument(
        "--max-hallucinations",
        type=int,
        default=0,
        help="Maximum allowed hallucinated ERP tool calls (default: 0)",
    )
    parser.add_argument(
        "--output-json",
        default="evals/results/release_gate_summary.json",
        help="Destination path for summary JSON",
    )
    args = parser.parse_args()

    exit_code = run_release_gate(
        dataset_path=args.dataset,
        max_entity_wer=args.max_entity_wer,
        min_worst_slice_tcr=args.min_worst_slice_tcr,
        max_hallucinations=args.max_hallucinations,
        output_json=args.output_json,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
