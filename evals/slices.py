from dataclasses import asdict, dataclass
from typing import Any

from evals.metrics import (
    calculate_handling_time_reduction,
    calculate_overall_entity_wer,
)


@dataclass
class SliceMetrics:
    slice_dimension: str
    slice_value: str
    sample_count: int
    tcr: float
    entity_wer: float
    handling_time_reduction_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def bucket_code_mix_index(cmi: float) -> str:
    """Bucket continuous Code-Mix Index into discrete evaluation categories."""
    if cmi <= 0.001:
        return "pure_english"
    if cmi <= 0.30:
        return "low_mix"
    if cmi <= 0.60:
        return "medium_mix"
    return "high_mix"


def bucket_thread_length(length: int) -> str:
    """Bucket thread length into turn depth categories."""
    if length <= 1:
        return "single_turn (1)"
    if length <= 3:
        return "multi_turn (2-3)"
    return "deep_thread (4+)"


def compute_slice_metrics(
    eval_results: list[dict[str, Any]],
) -> dict[str, list[SliceMetrics]]:
    """Compute tail-segmented metrics across all required slices:

    - script (latin, devanagari, mixed)
    - code_mix_index (pure_english, low_mix, medium_mix, high_mix)
    - token_fertility_bucket (low, medium, high)
    - thread_length (single_turn, multi_turn, deep_thread)
    - noise_level (clean, low, medium, high)
    - entity_type (invoice_ids, po_ids, grn_ids, vendor_ids, amount)
    """
    slices: dict[str, dict[str, list[dict[str, Any]]]] = {
        "script": {},
        "code_mix_index": {},
        "token_fertility_bucket": {},
        "thread_length": {},
        "noise_level": {},
    }

    for res in eval_results:
        gold = res.get("gold", {})
        script = str(gold.get("script", "latin"))
        cmi_val = float(gold.get("code_mix_index", 0.0))
        cmi_bucket = bucket_code_mix_index(cmi_val)
        fertility = str(gold.get("token_fertility_bucket", "low"))
        t_len = int(gold.get("thread_length", 1))
        t_bucket = bucket_thread_length(t_len)
        noise = str(gold.get("noise_level", "clean"))

        slices["script"].setdefault(script, []).append(res)
        slices["code_mix_index"].setdefault(cmi_bucket, []).append(res)
        slices["token_fertility_bucket"].setdefault(fertility, []).append(res)
        slices["thread_length"].setdefault(t_bucket, []).append(res)
        slices["noise_level"].setdefault(noise, []).append(res)

    results_by_dimension: dict[str, list[SliceMetrics]] = {}

    for dimension, buckets in slices.items():
        dim_metrics: list[SliceMetrics] = []
        for bucket_name, bucket_cases in buckets.items():
            count = len(bucket_cases)
            if count == 0:
                continue

            # TCR
            tcr_sum = sum(float(c.get("tcr", 0.0)) for c in bucket_cases)
            avg_tcr = tcr_sum / count

            # Entity-WER
            g_entities = [c.get("gold", {}).get("gold_entities", {}) for c in bucket_cases]
            p_entities = [c.get("pred_entities", {}) for c in bucket_cases]
            wer, _ = calculate_overall_entity_wer(g_entities, p_entities)

            # Handling-Time Reduction
            reduction = calculate_handling_time_reduction(bucket_cases)

            dim_metrics.append(
                SliceMetrics(
                    slice_dimension=dimension,
                    slice_value=bucket_name,
                    sample_count=count,
                    tcr=round(avg_tcr, 4),
                    entity_wer=round(wer, 4),
                    handling_time_reduction_pct=round(reduction, 2),
                )
            )
        # Sort by slice value for stable reporting
        dim_metrics.sort(key=lambda m: m.slice_value)
        results_by_dimension[dimension] = dim_metrics

    # Entity-Type Dimension Slicing
    all_g_entities = [c.get("gold", {}).get("gold_entities", {}) for c in eval_results]
    all_p_entities = [c.get("pred_entities", {}) for c in eval_results]
    _, overall_summary = calculate_overall_entity_wer(all_g_entities, all_p_entities)
    per_type_wer = overall_summary.get("per_type_wer", {})
    per_type_counts = overall_summary.get("per_type_counts", {})

    entity_metrics: list[SliceMetrics] = []
    for entity_type, wer_val in per_type_wer.items():
        g_cnt = per_type_counts.get(entity_type, {}).get("gold_count", 0)
        entity_metrics.append(
            SliceMetrics(
                slice_dimension="entity_type",
                slice_value=entity_type,
                sample_count=g_cnt,
                tcr=round(sum(float(c.get("tcr", 0.0)) for c in eval_results) / max(1, len(eval_results)), 4),
                entity_wer=round(float(wer_val), 4),
                handling_time_reduction_pct=round(calculate_handling_time_reduction(eval_results), 2),
            )
        )
    entity_metrics.sort(key=lambda m: m.slice_value)
    results_by_dimension["entity_type"] = entity_metrics

    return results_by_dimension


def get_worst_slices(
    slice_metrics: dict[str, list[SliceMetrics]],
    min_samples: int = 5,
) -> tuple[SliceMetrics, SliceMetrics]:
    """Identify the worst slice by Task Completion Rate (minimum TCR)

    and the worst slice by Entity-WER (maximum WER) among slices with >= min_samples.
    """
    candidates: list[SliceMetrics] = []
    for dim, metrics in slice_metrics.items():
        # Exclude entity_type from worst TCR slice calculation since entity_type is an entity-level slice
        if dim == "entity_type":
            continue
        for m in metrics:
            if m.sample_count >= min_samples:
                candidates.append(m)

    if not candidates:
        fallback = SliceMetrics(
            slice_dimension="all",
            slice_value="none",
            sample_count=0,
            tcr=1.0,
            entity_wer=0.0,
            handling_time_reduction_pct=100.0,
        )
        return fallback, fallback

    worst_tcr = min(candidates, key=lambda m: m.tcr)
    worst_wer = max(candidates, key=lambda m: m.entity_wer)
    return worst_tcr, worst_wer
