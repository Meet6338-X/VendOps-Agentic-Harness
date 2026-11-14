# VendOps Evaluation & Release Gate Metrics Specification

## 1. Overview & Core Philosophy

This document defines the formal mathematical metrics, evaluation methodologies, and threshold gates used to qualify the **VendOps** multi-agent dispute resolution harness for production release.

Evaluating enterprise financial workflows requires zero tolerance for hallucinations and rigorous tracking across multilingual code-mixed language variations, OCR noise, and edge-case dispute structures.

---

## 2. Mathematical Metric Definitions

### 2.1 Entity Word Error Rate (Entity-WER)

Entity extraction fidelity measures the accuracy with which canonical business identifiers (`INV-...`, `PO-...`, `GRN-...`, `VND-...`) and monetary dispute amounts are extracted from unstructured vendor communications.

Let $G$ denote the multiset of ground-truth (gold) entity tokens and $P$ denote the multiset of predicted entity tokens for a given test instance.

The optimal alignment between $G$ and $P$ yields:
- $C = |G \cap P|$ : Correctly extracted entities (true positives).
- $U_G = |G| - C$ : Unmatched gold entities.
- $U_P = |P| - C$ : Unmatched predicted entities.

From these, standard Levenshtein/WER components are derived:
- **Substitutions ($S$)**: Misidentified entities where a gold entity is replaced by an incorrect predicted entity:
  $$S = \min(U_G, U_P)$$
- **Deletions ($D$)**: Missed gold entities (false negatives):
  $$D = U_G - S$$
- **Insertions ($I$)**: Spurious or hallucinated entity extractions (false positives):
  $$I = U_P - S$$

The **Entity-WER** is computed as:

$$\text{Entity-WER} = \frac{S + D + I}{N}$$

where $N = |G|$ is the total number of gold entities ($N > 0$).
*Boundary condition*: If $N = 0$, $\text{Entity-WER} = 0.0$ if $I = 0$; otherwise $\text{Entity-WER} = 1.0$.

Note that:
$$S + D + I = \min(U_G, U_P) + (U_G - \min(U_G, U_P)) + (U_P - \min(U_G, U_P)) = \max(U_G, U_P)$$

#### Per-Entity-Type Entity-WER
Entity-WER is computed individually for each canonical entity domain:
1. **Invoice IDs (`invoice_ids`)**: Canonical pattern `^INV-\d{8}$`
2. **Purchase Order IDs (`po_ids`)**: Canonical pattern `^PO-\d{8}$`
3. **Goods Receipt Note IDs (`grn_ids`)**: Canonical pattern `^GRN-\d{8}$`
4. **Vendor IDs (`vendor_ids`)**: Canonical pattern `^VND-\d{6}$`
5. **Disputed Amount (`amount`)**: Floating point currency value matching within $\pm \$0.01$ tolerance.

#### Overall Corpus Entity-WER
Aggregated across all evaluated instances $i \in \{1, \dots, M\}$ and all entity types $t \in T$:

$$\text{Overall Entity-WER} = \frac{\sum_{i=1}^M \sum_{t \in T} (S_{i,t} + D_{i,t} + I_{i,t})}{\sum_{i=1}^M \sum_{t \in T} N_{i,t}}$$

**Production Gate Threshold**:
$$\text{Overall Entity-WER} \le 3.0\% \quad (0.030)$$

---

### 2.2 Task Completion Rate (TCR)

Task Completion Rate measures whether the end-to-end agent workflow reached the exact legally and contractually sound business resolution without violating policy constraints.

For case $i$:

$$\text{TCR}_i = \begin{cases}
1.0, & \text{if } a_{\text{pred}} = a_{\text{gold}} \;\land\; \text{AmountMatches}(m_{\text{pred}}, m_{\text{gold}}) \;\land\; \neg \text{PolicyViolation}_i \\
0.0, & \text{otherwise}
\end{cases}$$

Where:
- $a_{\text{pred}}, a_{\text{gold}} \in \text{ActionType}$: Must strictly match the canonical action enum (`RELEASE_PAYMENT`, `PARTIAL_PAYMENT`, `CREDIT_NOTE`, `REPLACEMENT`, `REJECT`, `ESCALATE`).
- $\text{AmountMatches}(m_{\text{pred}}, m_{\text{gold}})$:
  - If both amounts are `None` (e.g. rejection or query): `True`.
  - If both amounts are numeric: $|m_{\text{pred}} - m_{\text{gold}}| \le 0.01$.
  - Otherwise: `False`.
- $\text{PolicyViolation}_i$: Evaluates to `True` if:
  1. A hallucinated or unverified ID was submitted to an ERP tool.
  2. Free-text mutation actions were executed outside the `ActionType` enum.
  3. Release amount exceeded policy limits without required Human-in-the-Loop review.

Corpus-level TCR:
$$\text{TCR} = \frac{1}{M} \sum_{i=1}^M \text{TCR}_i$$

**Production Gate Requirement**:
$$\text{Worst-Slice TCR} \ge 85.0\% \quad (0.850)$$

---

### 2.3 Hallucinated Tool-Calls Reaching ERP

In accordance with the **VendOps Multi-Agent Operating Contract**:
- Every tool parameter passed to ERP tools (`GetInvoiceInput`, `GetPurchaseOrderInput`, `GetGRNInput`, `GetVendorInput`, `ExecuteResolutionInput`) must satisfy the **Provenance Check**:
  $$\text{ID} \in \text{MessageProvenanceIDs} \cup \text{VerifiedERPResponses}$$
- Zero hallucination policy:
  $$\text{Hallucinated Tool Calls} = 0$$

Any single tool call targeting an ungrounded ID fails the release gate immediately.

---

### 2.4 Handling-Time Reduction (%)

Calculates the operational velocity improvement dynamically using empirical manual benchmarks from `docs/BASELINE.md`.

$$\text{Reduction (\%)} = \left( \frac{\sum_{i=1}^M T_{\text{manual}}(c_i) - \sum_{i=1}^M T_{\text{auto}}(c_i)}{\sum_{i=1}^M T_{\text{manual}}(c_i)} \right) \times 100\%$$

Where:
- $T_{\text{manual}}(c_i)$ is resolved dynamically per `c_i.dispute_type` from `docs/BASELINE.md`.
- $T_{\text{auto}}(c_i)$ accounts for straight-through automation (0.25 min) vs HITL review (3.50 min) vs manual fallback (if case failed).

---

## 3. Tail-Segmented Slicing Engine

To prevent high-performing majority classes (e.g. clean English queries) from masking catastrophic failure modes in difficult distributions, results are partitioned across five orthogonal dimensions:

1. **Script**:
   - `latin`: Pure English or Roman Hinglish.
   - `devanagari`: Native Devanagari script.
   - `mixed`: Interleaved Devanagari and Latin script in a single message.
2. **Code-Mix Index (CMI)**:
   - `pure_english`: $\text{CMI} = 0.0$
   - `low_mix`: $0.0 < \text{CMI} \le 0.3$
   - `medium_mix`: $0.3 < \text{CMI} \le 0.6$
   - `high_mix`: $\text{CMI} > 0.6$
3. **Token Fertility Bucket**:
   - `low`: Token/word ratio $< 1.30$
   - `medium`: $1.30 \le \text{Token/word ratio} \le 1.80$
   - `high`: Token/word ratio $> 1.80$ (typical of morphologically rich Indic tokenization)
4. **Thread Depth**:
   - `single_turn`: 1 message turn
   - `multi_turn`: 2 to 3 message turns
   - `deep_thread`: 4 or more turns
5. **Noise & OCR Artifact Level**:
   - `clean`: No OCR noise or visual distortion
   - `low`: Occasional casing or minor punctuation variance
   - `medium`: Character substitutions (e.g. `l` $\to$ `1`, `O` $\to$ `0`, `rn` $\to$ `m`)
   - `high`: Heavy scanning noise, spacing disruptions, and OCR artifacts

### Worst-Slice Evaluation
The slicing engine computes TCR and Entity-WER independently across all slices with adequate sample support ($N \ge 5$). The release gate checks:

$$\min_{s \in \text{Slices}} \text{TCR}_s \ge 85.0\%$$
$$\max_{s \in \text{Slices}} \text{Entity-WER}_s \le 12.0\%$$

---

## 4. Context Compression Ablation Metrics

VendOps implements a `context_compress` node designed to summarize long email threads and strip non-essential conversational context prior to expensive LLM reasoning nodes.

The evaluation runner runs comparative passes (`compressed=True` vs `compressed=False`) and logs:
1. **Token Delta %**:
   $$\Delta_{\text{tokens}} = \frac{\text{Tokens}_{\text{uncompressed}} - \text{Tokens}_{\text{compressed}}}{\text{Tokens}_{\text{uncompressed}}} \times 100\%$$
2. **Latency Delta**:
   $$\Delta_{\text{latency}} = \text{Latency}_{\text{uncompressed}} - \text{Latency}_{\text{compressed}} \quad (\text{ms})$$
3. **Accuracy Parity**:
   $$\Delta_{\text{TCR}} = \text{TCR}_{\text{compressed}} - \text{TCR}_{\text{uncompressed}}$$
   *Acceptance condition*: Context compression must yield $\ge 30\%$ token reduction while maintaining $|\Delta_{\text{TCR}}| \le 2.0\%$.

---

## 5. Release Gate Summary Table

| Gate Metric | Threshold | Failure Action |
|---|---|---|
| **Overall Entity-WER** | $\le 3.0\%$ | Reject build (Exit Code 1) |
| **Worst-Slice TCR** | $\ge 85.0\%$ | Reject build (Exit Code 1) |
| **Hallucinated ERP Tool Calls** | $0$ (Zero tolerance) | Reject build (Exit Code 1) |
| **Handling Time Reduction** | $\ge 70.0\%$ | Warning alert if $< 70\%$ |
