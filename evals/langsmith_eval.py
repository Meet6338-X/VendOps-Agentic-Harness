import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from evals.dataset_gen import ensure_dataset, load_dataset_jsonl
from evals.metrics import (
    calculate_case_tcr,
    calculate_overall_entity_wer,
)
from evals.run_eval import run_single_case_offline
from vendops.contracts.ids import extract_all_ids

logger = logging.getLogger(__name__)


def is_langsmith_configured() -> bool:
    """Check if LangSmith environment variables are present."""
    return bool(
        os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY")
    )


def entity_wer_evaluator(run: Any, example: Any) -> dict[str, Any]:
    """Custom LangSmith evaluator for Entity-WER."""
    gold_entities = example.outputs.get("gold_entities", {})
    pred_entities = run.outputs.get("pred_entities", {})
    wer, _ = calculate_overall_entity_wer([gold_entities], [pred_entities])
    return {
        "key": "entity_wer",
        "score": round(wer, 4),
        "comment": f"Entity-WER: {wer:.2%}",
    }


def tcr_evaluator(run: Any, example: Any) -> dict[str, Any]:
    """Custom LangSmith evaluator for Task Completion Rate (TCR)."""
    gold_action = example.outputs.get("gold_action")
    gold_amount = example.outputs.get("gold_amount")
    pred_action = run.outputs.get("pred_action")
    pred_amount = run.outputs.get("pred_amount")
    policy_violation = bool(run.outputs.get("policy_violation", False))

    tcr = calculate_case_tcr(
        pred_action=pred_action,
        gold_action=gold_action,
        pred_amount=pred_amount,
        gold_amount=gold_amount,
        policy_violation=policy_violation,
    )
    return {
        "key": "tcr",
        "score": tcr,
        "comment": "Task completed successfully" if tcr == 1.0 else "Task failed or policy breach",
    }


def provenance_evaluator(run: Any, example: Any) -> dict[str, Any]:
    """Custom LangSmith evaluator ensuring zero tool-call hallucination."""
    raw_message = example.inputs.get("message", "")
    provenance = extract_all_ids(raw_message)
    provenance_all = set(
        provenance["invoice_ids"]
        + provenance["po_ids"]
        + provenance["grn_ids"]
        + provenance["vendor_ids"]
    )

    pred_entities = run.outputs.get("pred_entities", {})
    all_pred_ids = (
        pred_entities.get("invoice_ids", [])
        + pred_entities.get("po_ids", [])
        + pred_entities.get("grn_ids", [])
        + pred_entities.get("vendor_ids", [])
    )

    hallucinations = [pid for pid in all_pred_ids if pid not in provenance_all]
    has_zero_hallucinations = len(hallucinations) == 0

    return {
        "key": "provenance_check",
        "score": 1.0 if has_zero_hallucinations else 0.0,
        "comment": "Provenance verified" if has_zero_hallucinations else f"Hallucinated IDs: {hallucinations}",
    }


def sync_and_evaluate(
    dataset_path: Path | str = "evals/datasets/disputes_400.jsonl",
    project_name: str = "vendops",
    dataset_name: str = "vendops_disputes_400",
    max_cases: int | None = 20,
) -> dict[str, Any]:
    """Sync dataset and run evaluation with custom evaluators on LangSmith.

    If LangSmith credentials are not configured, runs in dry-run mode offline.
    """
    p = ensure_dataset(dataset_path)
    cases = load_dataset_jsonl(p)
    if max_cases is not None:
        cases = cases[:max_cases]

    if not is_langsmith_configured():
        logger.info(
            "LangSmith API key (LANGCHAIN_API_KEY / LANGSMITH_API_KEY) not found. "
            "Running in local dry-run mode."
        )
        dry_run_results = [run_single_case_offline(c) for c in cases]
        tcr_avg = sum(r["tcr"] for r in dry_run_results) / len(dry_run_results)
        return {
            "status": "dry_run",
            "message": "LangSmith credentials not set. Evaluated locally.",
            "total_cases": len(cases),
            "local_tcr": round(tcr_avg, 4),
        }

    try:
        from langsmith import Client

        client = Client()

        # Check or create dataset
        if not client.has_dataset(dataset_name=dataset_name):
            ds = client.create_dataset(
                dataset_name=dataset_name,
                description="VendOps 400+ multi-agent dispute dataset across English, Hinglish, Devanagari, and OCR noise.",
            )
            for c in cases:
                client.create_example(
                    inputs={"message": c["message"], "id": c["id"]},
                    outputs={
                        "gold_entities": c["gold_entities"],
                        "gold_action": c["gold_action"],
                        "gold_amount": c["gold_amount"],
                        "gold_dispute_type": c["gold_dispute_type"],
                    },
                    dataset_id=ds.id,
                )
            logger.info("Created LangSmith dataset '%s' with %d examples.", dataset_name, len(cases))

        # Target runner function for LangSmith evaluate
        def target_pipeline(inputs: dict[str, Any]) -> dict[str, Any]:
            case_id = inputs.get("id")
            case_match = next((c for c in cases if c["id"] == case_id), {"message": inputs.get("message", "")})
            res = run_single_case_offline(case_match)
            return {
                "pred_entities": res["pred_entities"],
                "pred_action": res["pred_action"],
                "pred_amount": res["pred_amount"],
                "policy_violation": res["policy_violation"],
            }

        from langsmith import evaluate

        results = evaluate(
            target_pipeline,
            data=dataset_name,
            evaluators=[entity_wer_evaluator, tcr_evaluator, provenance_evaluator],
            experiment_prefix=f"{project_name}-eval",
        )

        return {
            "status": "success",
            "project_name": project_name,
            "dataset_name": dataset_name,
            "results": str(results),
        }
    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        logger.warning("LangSmith remote sync encountered exception: %s", exc)
        return {
            "status": "error",
            "error": str(exc),
        }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser(description="VendOps LangSmith Dataset Sync & Evaluator")
    parser.add_argument("--dataset", default="evals/datasets/disputes_400.jsonl")
    parser.add_argument("--project", default="vendops")
    parser.add_argument("--max-cases", type=int, default=20)
    args = parser.parse_args()

    res = sync_and_evaluate(
        dataset_path=args.dataset,
        project_name=args.project,
        max_cases=args.max_cases,
    )
    print(res)


if __name__ == "__main__":
    main()
