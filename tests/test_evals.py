import sys
from pathlib import Path
from types import SimpleNamespace

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from evals.dataset_gen import (
    generate_400_disputes,
    load_dataset_jsonl,
    save_dataset_jsonl,
)
from evals.langsmith_eval import (
    entity_wer_evaluator,
    provenance_evaluator,
    sync_and_evaluate,
    tcr_evaluator,
)
from evals.metrics import (
    calculate_amount_wer,
    calculate_case_tcr,
    calculate_entity_wer,
    calculate_entity_wer_by_type,
    calculate_handling_time_reduction,
    calculate_overall_entity_wer,
    load_baseline_constants,
)
from evals.run_eval import execute_evaluation
from evals.slices import (
    SliceMetrics,
    bucket_code_mix_index,
    bucket_thread_length,
    compute_slice_metrics,
    get_worst_slices,
)
from scripts.release_gate import run_release_gate
from vendops.contracts.enums import ActionType, DisputeType
from vendops.contracts.ids import (
    is_valid_grn_id,
    is_valid_invoice_id,
    is_valid_po_id,
    is_valid_vendor_id,
)

# -----------------------------------------------------------------------------
# 1. Entity-WER Mathematical Tests
# -----------------------------------------------------------------------------


def test_entity_wer_perfect_match() -> None:
    gold = ["INV-20240001", "PO-20240001"]
    pred = ["INV-20240001", "PO-20240001"]
    wer, counts = calculate_entity_wer(gold, pred)
    assert wer == 0.0
    assert counts["substitutions"] == 0
    assert counts["deletions"] == 0
    assert counts["insertions"] == 0
    assert counts["gold_count"] == 2


def test_entity_wer_boundary_empty() -> None:
    # Both empty
    wer, counts = calculate_entity_wer([], [])
    assert wer == 0.0
    assert counts["total_errors"] == 0

    # Gold empty, Pred has insertion
    wer, counts = calculate_entity_wer([], ["INV-20240001"])
    assert wer == 1.0
    assert counts["insertions"] == 1
    assert counts["gold_count"] == 0

    # Pred empty, Gold has deletion
    wer, counts = calculate_entity_wer(["INV-20240001"], [])
    assert wer == 1.0
    assert counts["deletions"] == 1
    assert counts["gold_count"] == 1


def test_entity_wer_substitutions_and_insertions() -> None:
    # 1 common, 1 substitution, 1 insertion
    gold = ["INV-20240001", "PO-20240001"]
    pred = ["INV-20240001", "PO-20249999", "GRN-20240001"]
    wer, counts = calculate_entity_wer(gold, pred)
    # common: INV-20240001
    # unmatched gold: PO-20240001 (1)
    # unmatched pred: PO-20249999, GRN-20240001 (2)
    # substitutions = min(1, 2) = 1
    # deletions = 1 - 1 = 0
    # insertions = 2 - 1 = 1
    # total errors = 1 + 0 + 1 = 2
    # gold count = 2 -> WER = 2 / 2 = 1.0
    assert counts["substitutions"] == 1
    assert counts["deletions"] == 0
    assert counts["insertions"] == 1
    assert wer == 1.0


def test_entity_wer_id_normalization() -> None:
    gold = ["INV-20240001"]
    pred = [" inv-20240001 "]
    wer, counts = calculate_entity_wer(gold, pred)
    assert wer == 0.0
    assert counts["total_errors"] == 0


def test_amount_wer_calculation() -> None:
    # Exact amount match
    wer, counts = calculate_amount_wer(1500.50, 1500.50)
    assert wer == 0.0

    # Within tolerance ($0.01)
    wer, counts = calculate_amount_wer(1500.50, 1500.505)
    assert wer == 0.0

    # Mismatch amount -> substitution
    wer, counts = calculate_amount_wer(1500.50, 1800.00)
    assert wer == 1.0
    assert counts["substitutions"] == 1

    # Both None -> match
    wer, counts = calculate_amount_wer(None, None)
    assert wer == 0.0

    # Gold float, Pred None -> deletion
    wer, counts = calculate_amount_wer(500.0, None)
    assert wer == 1.0
    assert counts["deletions"] == 1

    # Gold None, Pred float -> insertion
    wer, counts = calculate_amount_wer(None, 500.0)
    assert wer == 1.0
    assert counts["insertions"] == 1


def test_entity_wer_by_type() -> None:
    gold = {
        "invoice_ids": ["INV-20240001"],
        "po_ids": ["PO-20240001"],
        "grn_ids": ["GRN-20240001"],
        "vendor_ids": ["VND-000001"],
        "amount": 2500.00,
    }
    pred = {
        "invoice_ids": ["INV-20240001"],
        "po_ids": ["PO-20249999"],  # substitution
        "grn_ids": ["GRN-20240001"],
        "vendor_ids": ["VND-000001"],
        "amount": 2500.00,
    }
    by_type = calculate_entity_wer_by_type(gold, pred)
    assert by_type["invoice_ids"] == 0.0
    assert by_type["po_ids"] == 1.0
    assert by_type["grn_ids"] == 0.0
    assert by_type["vendor_ids"] == 0.0
    assert by_type["amount"] == 0.0


def test_overall_entity_wer_aggregation() -> None:
    case1_gold = {
        "invoice_ids": ["INV-20240001"],
        "po_ids": ["PO-20240001"],
        "grn_ids": [],
        "vendor_ids": ["VND-000001"],
        "amount": 100.0,
    }
    case1_pred = {
        "invoice_ids": ["INV-20240001"],
        "po_ids": ["PO-20240001"],
        "grn_ids": [],
        "vendor_ids": ["VND-000001"],
        "amount": 100.0,
    }
    case2_gold = {
        "invoice_ids": ["INV-20240002"],
        "po_ids": [],
        "grn_ids": [],
        "vendor_ids": ["VND-000002"],
        "amount": None,
    }
    case2_pred = {
        "invoice_ids": ["INV-20249999"],  # substitution
        "po_ids": [],
        "grn_ids": [],
        "vendor_ids": ["VND-000002"],
        "amount": None,
    }
    overall_wer, summary = calculate_overall_entity_wer(
        [case1_gold, case2_gold], [case1_pred, case2_pred]
    )
    # Total gold entities:
    # Case 1: 1 inv + 1 po + 0 grn + 1 vnd + 1 amt = 4
    # Case 2: 1 inv + 0 po + 0 grn + 1 vnd + 0 amt = 2
    # Total gold count = 6.
    # Total errors = 1 substitution on invoice_ids in Case 2.
    # Overall WER = 1 / 6 = 0.1667
    assert summary["total_gold_count"] == 6
    assert summary["total_errors"] == 1
    assert round(overall_wer, 4) == 0.1667


# -----------------------------------------------------------------------------
# 2. Task Completion Rate (TCR) Tests
# -----------------------------------------------------------------------------


def test_case_tcr_success() -> None:
    tcr = calculate_case_tcr(
        pred_action=ActionType.RELEASE_PAYMENT,
        gold_action=ActionType.RELEASE_PAYMENT,
        pred_amount=5000.0,
        gold_amount=5000.0,
        policy_violation=False,
    )
    assert tcr == 1.0


def test_case_tcr_failures() -> None:
    # Wrong action
    tcr1 = calculate_case_tcr(
        pred_action=ActionType.PARTIAL_PAYMENT,
        gold_action=ActionType.RELEASE_PAYMENT,
        pred_amount=5000.0,
        gold_amount=5000.0,
    )
    assert tcr1 == 0.0

    # Wrong amount
    tcr2 = calculate_case_tcr(
        pred_action=ActionType.RELEASE_PAYMENT,
        gold_action=ActionType.RELEASE_PAYMENT,
        pred_amount=4000.0,
        gold_amount=5000.0,
    )
    assert tcr2 == 0.0

    # Policy violation
    tcr3 = calculate_case_tcr(
        pred_action=ActionType.RELEASE_PAYMENT,
        gold_action=ActionType.RELEASE_PAYMENT,
        pred_amount=5000.0,
        gold_amount=5000.0,
        policy_violation=True,
    )
    assert tcr3 == 0.0

    # Amount expected None but provided
    tcr4 = calculate_case_tcr(
        pred_action=ActionType.REJECT,
        gold_action=ActionType.REJECT,
        pred_amount=100.0,
        gold_amount=None,
    )
    assert tcr4 == 0.0


# -----------------------------------------------------------------------------
# 3. Handling-Time Reduction Dynamic Tests
# -----------------------------------------------------------------------------


def test_dynamic_handling_time_reduction_calculation() -> None:
    baseline = load_baseline_constants()
    assert "manual_baseline_minutes" in baseline
    assert "automated_baseline_minutes" in baseline

    # All cases resolved with straight-through automation (0.25 min vs ~18-32 min manual)
    cases = [
        {"dispute_type": DisputeType.PAYMENT_DELAY.value, "tcr": 1.0, "hitl_required": False},
        {"dispute_type": DisputeType.PRICE_MISMATCH.value, "tcr": 1.0, "hitl_required": False},
    ]
    reduction = calculate_handling_time_reduction(cases)
    # Manual: 18 + 32 = 50 min. Automated: 0.25 + 0.25 = 0.50 min.
    # Reduction = (50 - 0.5) / 50 * 100 = 99.0%
    assert reduction == 99.0

    # One case fails and falls back to full manual handling time
    cases_with_fail = [
        {"dispute_type": DisputeType.PAYMENT_DELAY.value, "tcr": 1.0, "hitl_required": False},
        {"dispute_type": DisputeType.PRICE_MISMATCH.value, "tcr": 0.0, "hitl_required": False},
    ]
    reduction_fail = calculate_handling_time_reduction(cases_with_fail)
    # Manual: 50 min. Automated: 0.25 + 32 = 32.25 min.
    # Reduction = (50 - 32.25) / 50 * 100 = 35.5%
    assert reduction_fail == 35.5


# -----------------------------------------------------------------------------
# 4. Dataset Generation & Slicing Tests
# -----------------------------------------------------------------------------


def test_dataset_generation_volume_and_distributions() -> None:
    cases = generate_400_disputes(total_cases=420, seed=42)
    assert len(cases) == 420

    scripts = [c.script for c in cases]
    noise_levels = [c.noise_level for c in cases]
    cmis = [c.code_mix_index for c in cases]

    # Verify distributions:
    # Latin (English + Hinglish + OCR) ~85%
    assert scripts.count("latin") >= 350
    # Devanagari / Mixed ~15%
    assert (scripts.count("devanagari") + scripts.count("mixed")) >= 60

    # Noise level distribution (clean vs medium/high)
    assert (noise_levels.count("medium") + noise_levels.count("high")) >= 40

    # Pure English (cmi == 0.0) >= 35%
    pure_en = sum(1 for cmi in cmis if cmi == 0.0)
    assert pure_en >= 150

    # High-value cases (> $25,000)
    high_val = sum(
        1
        for c in cases
        if c.gold_entities["amount"] is not None
        and c.gold_entities["amount"] > 25000.0
    )
    assert high_val >= 40

    # Multi-entity cases (>= 2 POs or multiple entities)
    multi_po = sum(1 for c in cases if len(c.gold_entities.get("po_ids", [])) > 1)
    assert multi_po >= 30

    # Verify canonical contract ID formats
    for c in cases:
        for inv_id in c.gold_entities["invoice_ids"]:
            assert is_valid_invoice_id(inv_id), f"Invalid Invoice ID: {inv_id}"
        for po_id in c.gold_entities["po_ids"]:
            assert is_valid_po_id(po_id), f"Invalid PO ID: {po_id}"
        for grn_id in c.gold_entities["grn_ids"]:
            assert is_valid_grn_id(grn_id), f"Invalid GRN ID: {grn_id}"
        for vnd_id in c.gold_entities["vendor_ids"]:
            assert is_valid_vendor_id(vnd_id), f"Invalid Vendor ID: {vnd_id}"


def test_dataset_jsonl_roundtrip(tmp_path: Path) -> None:
    cases = generate_400_disputes(total_cases=10, seed=42)
    out_file = tmp_path / "test_disputes.jsonl"
    save_dataset_jsonl(cases, out_file)
    loaded = load_dataset_jsonl(out_file)
    assert len(loaded) == 10
    assert loaded[0]["id"] == cases[0].id
    assert loaded[0]["gold_action"] == cases[0].gold_action


def test_slicing_helpers() -> None:
    assert bucket_code_mix_index(0.0) == "pure_english"
    assert bucket_code_mix_index(0.15) == "low_mix"
    assert bucket_code_mix_index(0.45) == "medium_mix"
    assert bucket_code_mix_index(0.75) == "high_mix"

    assert bucket_thread_length(1) == "single_turn (1)"
    assert bucket_thread_length(2) == "multi_turn (2-3)"
    assert bucket_thread_length(3) == "multi_turn (2-3)"
    assert bucket_thread_length(5) == "deep_thread (4+)"


def test_slice_metrics_and_worst_slice_selection() -> None:
    sample_cases = [
        {
            "gold": {
                "script": "latin",
                "code_mix_index": 0.0,
                "token_fertility_bucket": "low",
                "thread_length": 1,
                "noise_level": "clean",
                "gold_entities": {"invoice_ids": ["INV-20240001"]},
            },
            "pred_entities": {"invoice_ids": ["INV-20240001"]},
            "tcr": 1.0,
            "policy_violation": False,
        }
    ]
    computed = compute_slice_metrics(sample_cases)
    assert "script" in computed
    assert computed["script"][0].tcr == 1.0

    metrics = {
        "script": [
            SliceMetrics("script", "latin", 100, 0.95, 0.02, 90.0),
            SliceMetrics("script", "devanagari", 50, 0.88, 0.05, 85.0),
        ],
        "noise_level": [
            SliceMetrics("noise_level", "clean", 120, 0.98, 0.01, 95.0),
            SliceMetrics("noise_level", "high", 30, 0.86, 0.08, 80.0),
        ],
    }
    worst_tcr, worst_wer = get_worst_slices(metrics, min_samples=5)
    assert worst_tcr.slice_value == "high"
    assert worst_tcr.tcr == 0.86
    assert worst_wer.slice_value == "high"
    assert worst_wer.entity_wer == 0.08


# -----------------------------------------------------------------------------
# 5. Full Evaluation & Release Gate Verification
# -----------------------------------------------------------------------------


def test_execute_evaluation_ablation_and_gate_pass() -> None:
    report, slice_metrics, comp_ablation, uncomp_ablation = execute_evaluation(
        max_cases=50
    )
    assert report.total_cases == 50
    assert report.overall_tcr >= 0.85
    assert report.overall_wer <= 0.030
    assert report.hallucinated_erp_tool_calls == 0
    assert report.gate_passed is True
    assert "script" in slice_metrics
    assert "noise_level" in slice_metrics

    # Context compression ablation checks
    assert comp_ablation.total_tokens < uncomp_ablation.total_tokens
    assert report.ablation["token_reduction_pct"] >= 30.0
    assert report.ablation["latency_speedup_ms"] >= 0.0


def test_release_gate_cli_pass_and_fail(tmp_path: Path) -> None:
    summary_path = tmp_path / "summary.json"

    # 1. Normal pass
    exit_code_pass = run_release_gate(
        max_entity_wer=0.030,
        min_worst_slice_tcr=0.850,
        max_hallucinations=0,
        output_json=summary_path,
    )
    assert exit_code_pass == 0

    # 2. Forced failure on WER threshold
    exit_code_wer_fail = run_release_gate(
        max_entity_wer=0.0001,  # Unrealistically strict to force gate failure
        output_json=summary_path,
    )
    assert exit_code_wer_fail == 1

    # 3. Forced failure on TCR threshold
    exit_code_tcr_fail = run_release_gate(
        min_worst_slice_tcr=1.05,  # Impossible threshold
        output_json=summary_path,
    )
    assert exit_code_tcr_fail == 1


# -----------------------------------------------------------------------------
# 6. LangSmith Offline Evaluators Tests
# -----------------------------------------------------------------------------


def test_langsmith_offline_dry_run() -> None:
    res = sync_and_evaluate(max_cases=5)
    assert res["status"] in ("dry_run", "success")


def test_langsmith_evaluators() -> None:
    example = SimpleNamespace(
        inputs={"message": "Inquiry on INV-20240001 and PO-20240001 for $500.00"},
        outputs={
            "gold_entities": {"invoice_ids": ["INV-20240001"], "po_ids": ["PO-20240001"]},
            "gold_action": "RELEASE_PAYMENT",
            "gold_amount": 500.0,
        },
    )
    run_success = SimpleNamespace(
        outputs={
            "pred_entities": {"invoice_ids": ["INV-20240001"], "po_ids": ["PO-20240001"]},
            "pred_action": "RELEASE_PAYMENT",
            "pred_amount": 500.0,
            "policy_violation": False,
        }
    )

    wer_eval = entity_wer_evaluator(run_success, example)
    assert wer_eval["key"] == "entity_wer"
    assert wer_eval["score"] == 0.0

    tcr_eval = tcr_evaluator(run_success, example)
    assert tcr_eval["key"] == "tcr"
    assert tcr_eval["score"] == 1.0

    prov_eval = provenance_evaluator(run_success, example)
    assert prov_eval["key"] == "provenance_check"
    assert prov_eval["score"] == 1.0

    # Hallucinated tool ID provenance failure
    run_hallucinated = SimpleNamespace(
        outputs={
            "pred_entities": {"invoice_ids": ["INV-20249999"]},  # Not in input message!
            "pred_action": "RELEASE_PAYMENT",
            "pred_amount": 500.0,
        }
    )
    prov_fail = provenance_evaluator(run_hallucinated, example)
    assert prov_fail["score"] == 0.0
