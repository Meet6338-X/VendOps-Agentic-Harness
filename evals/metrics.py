import json
import logging
import re
from collections import Counter
from pathlib import Path
from typing import Any

from vendops.contracts.enums import ActionType, DisputeType
from vendops.contracts.ids import normalize_id

logger = logging.getLogger(__name__)

# Default baseline fallback if docs/BASELINE.md is missing or unparseable
DEFAULT_MANUAL_BASELINE_MINUTES: dict[str, float] = {
    DisputeType.PAYMENT_DELAY.value: 18.0,
    DisputeType.SHORT_PAYMENT.value: 28.0,
    DisputeType.DUPLICATE_INVOICE.value: 16.0,
    DisputeType.PRICE_MISMATCH.value: 32.0,
    DisputeType.QTY_MISMATCH.value: 26.0,
    DisputeType.MISSING_GRN.value: 24.0,
    DisputeType.OTHER.value: 20.0,
}

DEFAULT_AUTOMATED_BASELINE_MINUTES: dict[str, float] = {
    "stp_time": 0.25,
    "hitl_review_time": 3.50,
}


def load_baseline_constants(
    baseline_path: Path | str | None = None,
) -> dict[str, Any]:
    """Dynamically load baseline constants from docs/BASELINE.md or return defaults."""
    if baseline_path is None:
        # Search relative to current repository root
        candidate = Path("docs") / "BASELINE.md"
    else:
        candidate = Path(baseline_path)

    if candidate.exists():
        try:
            content = candidate.read_text(encoding="utf-8")
            # Extract JSON block between ```json and ```
            match = re.search(r"```json\s*(\{.*?\})\s*```", content, re.DOTALL)
            if match:
                parsed = json.loads(match.group(1))
                if isinstance(parsed, dict) and "manual_baseline_minutes" in parsed:
                    return parsed
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            logger.debug("Could not parse baseline file %s: %s", candidate, exc)

    return {
        "manual_baseline_minutes": DEFAULT_MANUAL_BASELINE_MINUTES,
        "automated_baseline_minutes": DEFAULT_AUTOMATED_BASELINE_MINUTES,
    }


def calculate_entity_wer(
    gold_entities: list[str],
    pred_entities: list[str],
) -> tuple[float, dict[str, int]]:
    """Compute exact mathematical Entity-WER for a list of string entity IDs.

    WER = (Substitutions + Deletions + Insertions) / Total Gold Entities.

    Returns:
        tuple of (wer_float, counts_dict) where counts_dict contains
        'substitutions', 'deletions', 'insertions', 'gold_count'.
    """
    norm_gold = [normalize_id(e) for e in gold_entities if e]
    norm_pred = [normalize_id(e) for e in pred_entities if e]

    gold_counts = Counter(norm_gold)
    pred_counts = Counter(norm_pred)

    all_keys = set(gold_counts.keys()) | set(pred_counts.keys())
    matched = sum(min(gold_counts[k], pred_counts[k]) for k in all_keys)

    total_gold = len(norm_gold)
    total_pred = len(norm_pred)

    unmatched_gold = total_gold - matched
    unmatched_pred = total_pred - matched

    substitutions = min(unmatched_gold, unmatched_pred)
    deletions = unmatched_gold - substitutions
    insertions = unmatched_pred - substitutions

    total_errors = substitutions + deletions + insertions

    if total_gold == 0:
        wer = 0.0 if total_pred == 0 else 1.0
    else:
        wer = total_errors / total_gold

    counts = {
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "gold_count": total_gold,
        "pred_count": total_pred,
        "total_errors": total_errors,
    }
    return wer, counts


def calculate_amount_wer(
    gold_amount: float | None,
    pred_amount: float | None,
    tolerance: float = 0.01,
) -> tuple[float, dict[str, int]]:
    """Compute Entity-WER specifically for monetary amounts."""
    substitutions = 0
    deletions = 0
    insertions = 0

    if gold_amount is not None:
        gold_count = 1
        if pred_amount is not None:
            if abs(gold_amount - pred_amount) <= tolerance:
                pass  # Correct match
            else:
                substitutions = 1
        else:
            deletions = 1
    else:
        gold_count = 0
        if pred_amount is not None:
            insertions = 1

    total_errors = substitutions + deletions + insertions
    if gold_count == 0:
        wer = 0.0 if insertions == 0 else 1.0
    else:
        wer = total_errors / gold_count

    counts = {
        "substitutions": substitutions,
        "deletions": deletions,
        "insertions": insertions,
        "gold_count": gold_count,
        "pred_count": 1 if pred_amount is not None else 0,
        "total_errors": total_errors,
    }
    return wer, counts


def calculate_entity_wer_by_type(
    gold_entities: dict[str, Any],
    pred_entities: dict[str, Any],
) -> dict[str, float]:
    """Calculate Entity-WER individually for each entity type:

    invoice_ids, po_ids, grn_ids, vendor_ids, amount.
    """
    results: dict[str, float] = {}

    for key in ("invoice_ids", "po_ids", "grn_ids", "vendor_ids"):
        g_list = gold_entities.get(key, []) or []
        p_list = pred_entities.get(key, []) or []
        wer, _ = calculate_entity_wer(g_list, p_list)
        results[key] = wer

    g_amt = gold_entities.get("amount")
    p_amt = pred_entities.get("amount")
    amt_wer, _ = calculate_amount_wer(g_amt, p_amt)
    results["amount"] = amt_wer

    return results


def calculate_overall_entity_wer(
    cases_gold: list[dict[str, Any]],
    cases_pred: list[dict[str, Any]],
) -> tuple[float, dict[str, Any]]:
    """Calculate the overall corpus-wide Entity-WER across all entities and all cases.

    Returns:
        tuple of (overall_wer, summary_stats)
    """
    total_substitutions = 0
    total_deletions = 0
    total_insertions = 0
    total_gold_count = 0

    per_type_counts: dict[str, dict[str, int]] = {
        "invoice_ids": {"substitutions": 0, "deletions": 0, "insertions": 0, "gold_count": 0},
        "po_ids": {"substitutions": 0, "deletions": 0, "insertions": 0, "gold_count": 0},
        "grn_ids": {"substitutions": 0, "deletions": 0, "insertions": 0, "gold_count": 0},
        "vendor_ids": {"substitutions": 0, "deletions": 0, "insertions": 0, "gold_count": 0},
        "amount": {"substitutions": 0, "deletions": 0, "insertions": 0, "gold_count": 0},
    }

    for g_case, p_case in zip(cases_gold, cases_pred, strict=False):
        for key in ("invoice_ids", "po_ids", "grn_ids", "vendor_ids"):
            g_list = g_case.get(key, []) or []
            p_list = p_case.get(key, []) or []
            _, counts = calculate_entity_wer(g_list, p_list)
            for metric_k in ("substitutions", "deletions", "insertions", "gold_count"):
                per_type_counts[key][metric_k] += counts[metric_k]
            total_substitutions += counts["substitutions"]
            total_deletions += counts["deletions"]
            total_insertions += counts["insertions"]
            total_gold_count += counts["gold_count"]

        # Amount
        g_amt = g_case.get("amount")
        p_amt = p_case.get("amount")
        _, amt_counts = calculate_amount_wer(g_amt, p_amt)
        for metric_k in ("substitutions", "deletions", "insertions", "gold_count"):
            per_type_counts["amount"][metric_k] += amt_counts[metric_k]
        total_substitutions += amt_counts["substitutions"]
        total_deletions += amt_counts["deletions"]
        total_insertions += amt_counts["insertions"]
        total_gold_count += amt_counts["gold_count"]

    total_errors = total_substitutions + total_deletions + total_insertions
    overall_wer = total_errors / total_gold_count if total_gold_count > 0 else 0.0

    per_type_wer: dict[str, float] = {}
    for t_name, t_counts in per_type_counts.items():
        g_c = t_counts["gold_count"]
        t_err = t_counts["substitutions"] + t_counts["deletions"] + t_counts["insertions"]
        per_type_wer[t_name] = (t_err / g_c) if g_c > 0 else (0.0 if t_counts["insertions"] == 0 else 1.0)

    summary = {
        "overall_wer": overall_wer,
        "total_errors": total_errors,
        "total_substitutions": total_substitutions,
        "total_deletions": total_deletions,
        "total_insertions": total_insertions,
        "total_gold_count": total_gold_count,
        "per_type_wer": per_type_wer,
        "per_type_counts": per_type_counts,
    }
    return overall_wer, summary


def calculate_case_tcr(
    pred_action: str | ActionType | None,
    gold_action: str | ActionType,
    pred_amount: float | None,
    gold_amount: float | None,
    policy_violation: bool = False,
    amount_tolerance: float = 0.01,
) -> float:
    """Task Completion Rate for a single case.

    Returns 1.0 if correct action, correct amount, no policy violation; 0.0 otherwise.
    """
    if policy_violation:
        return 0.0

    if pred_action is None:
        return 0.0

    # Normalize action
    norm_pred_action = (
        pred_action.value if isinstance(pred_action, ActionType) else str(pred_action)
    )
    norm_gold_action = (
        gold_action.value if isinstance(gold_action, ActionType) else str(gold_action)
    )

    if norm_pred_action.upper() != norm_gold_action.upper():
        return 0.0

    # Amount check
    if gold_amount is None:
        if pred_amount is not None:
            # Gold expects no amount authorized/mutated, but agent specified one
            return 0.0
    else:
        if pred_amount is None:
            return 0.0
        if abs(pred_amount - gold_amount) > amount_tolerance:
            return 0.0

    return 1.0


def calculate_handling_time_reduction(
    cases_results: list[dict[str, Any]],
    baseline_path: Path | str | None = None,
) -> float:
    """Calculate percentage handling time reduction dynamically using baseline constants.

    Formula:
        Reduction % = ((Total Manual Baseline - Total Automated Time) / Total Manual Baseline) * 100
    """
    baseline = load_baseline_constants(baseline_path)
    manual_times = baseline.get("manual_baseline_minutes", DEFAULT_MANUAL_BASELINE_MINUTES)
    auto_times = baseline.get("automated_baseline_minutes", DEFAULT_AUTOMATED_BASELINE_MINUTES)

    stp_time = float(auto_times.get("stp_time", 0.25))
    hitl_time = float(auto_times.get("hitl_review_time", 3.50))
    default_manual = float(manual_times.get(DisputeType.OTHER.value, 20.0))

    total_manual = 0.0
    total_auto = 0.0

    for case in cases_results:
        dispute_type = str(case.get("dispute_type", DisputeType.OTHER.value))
        manual_time = float(manual_times.get(dispute_type, default_manual))
        total_manual += manual_time

        # If policy violation or failed resolution, fall back to manual handling time
        if case.get("policy_violation", False) or case.get("tcr", 0.0) < 1.0:
            total_auto += manual_time
        elif case.get("hitl_required", False):
            total_auto += stp_time + hitl_time
        else:
            total_auto += stp_time

    if total_manual <= 0.0:
        return 0.0

    reduction = ((total_manual - total_auto) / total_manual) * 100.0
    return max(0.0, reduction)
