# VendOps Automated Evaluation & Gate Report (PASSED)

## 1. Executive Summary

- **Evaluated Dispute Cases**: 420
- **Overall Task Completion Rate (TCR)**: 100.00%
- **Overall Entity-WER**: 0.60% (Gate: <= 3.00%)
- **Worst-Slice TCR**: 100.00% (Gate: >= 85.00%) [script:devanagari]
- **Worst-Slice Entity-WER**: 4.82% [noise_level:high]
- **Hallucinated ERP Tool Calls**: 0 (Gate: == 0)
- **Dynamic Handling-Time Reduction**: 97.2%
- **Release Gate Status**: **PASSED**

## 2. Context Compression Ablation Analysis

| Metric | Uncompressed Pipeline | Compressed Pipeline | Delta / Improvement |
|---|---|---|---|
| **Prompt Tokens** | 177,365 | 89,511 | -45.9% |
| **Completion Tokens** | 23,100 | 18,900 | - |
| **Total Tokens** | 200,465 | 108,411 | -45.9% |
| **Average Latency** | 49.1 ms | 24.0 ms | -25.1 ms |
| **Task Completion (TCR)** | 100.00% | 100.00% | +0.00% |

## 3. Tail-Segmented Slice Breakdown

### Slice Dimension: `script`

| Slice Value | Sample Count | Task Completion (TCR) | Entity-WER | Handling Time Reduction |
|---|---|---|---|---|
| `devanagari` | 27 | 100.00% | 0.00% | 96.2% |
| `latin` | 357 | 100.00% | 0.70% | 97.2% |
| `mixed` | 36 | 100.00% | 0.00% | 97.8% |

### Slice Dimension: `code_mix_index`

| Slice Value | Sample Count | Task Completion (TCR) | Entity-WER | Handling Time Reduction |
|---|---|---|---|---|
| `high_mix` | 84 | 100.00% | 0.00% | 96.7% |
| `low_mix` | 27 | 100.00% | 3.10% | 96.8% |
| `medium_mix` | 140 | 100.00% | 0.60% | 97.5% |
| `pure_english` | 169 | 100.00% | 0.49% | 97.2% |

### Slice Dimension: `token_fertility_bucket`

| Slice Value | Sample Count | Task Completion (TCR) | Entity-WER | Handling Time Reduction |
|---|---|---|---|---|
| `high` | 28 | 100.00% | 0.00% | 96.2% |
| `low` | 165 | 100.00% | 1.14% | 97.4% |
| `medium` | 227 | 100.00% | 0.28% | 97.1% |

### Slice Dimension: `thread_length`

| Slice Value | Sample Count | Task Completion (TCR) | Entity-WER | Handling Time Reduction |
|---|---|---|---|---|
| `deep_thread (4+)` | 71 | 100.00% | 0.86% | 96.3% |
| `multi_turn (2-3)` | 73 | 100.00% | 0.28% | 97.3% |
| `single_turn (1)` | 276 | 100.00% | 0.61% | 97.4% |

### Slice Dimension: `noise_level`

| Slice Value | Sample Count | Task Completion (TCR) | Entity-WER | Handling Time Reduction |
|---|---|---|---|---|
| `clean` | 378 | 100.00% | 0.33% | 97.2% |
| `high` | 16 | 100.00% | 4.82% | 95.5% |
| `medium` | 26 | 100.00% | 1.64% | 97.4% |

### Slice Dimension: `entity_type`

| Slice Value | Sample Count | Task Completion (TCR) | Entity-WER | Handling Time Reduction |
|---|---|---|---|---|
| `amount` | 407 | 100.00% | 0.00% | 97.2% |
| `grn_ids` | 283 | 100.00% | 0.00% | 97.2% |
| `invoice_ids` | 401 | 100.00% | 0.00% | 97.2% |
| `po_ids` | 500 | 100.00% | 0.80% | 97.2% |
| `vendor_ids` | 420 | 100.00% | 1.90% | 97.2% |
