# Mathematical Metric Definitions & Evaluation Standards

This document establishes the formal definitions, formulas, and evaluation methodology for benchmarked metrics in **VendOps**.

---

## 1. Entity Word Error Rate (Entity-WER)

Entity-WER measures extraction fidelity specifically across canonical enterprise entities (Invoice IDs, Purchase Order IDs, Goods Receipt Note IDs, Vendor IDs, and monetary amounts). Unlike standard sentence-level WER, Entity-WER evaluates the set of extracted entities against the gold annotated entities.

### Mathematical Definition

$$\text{Entity-WER} = \frac{S + D + I}{N_{\text{gold}}}$$

Where:
- $S$: **Substitutions** — an extracted entity that partially matches a gold entity but has transcription or OCR character corruption.
- $D$: **Deletions** — a gold entity present in the message that was completely omitted by the extraction system.
- $I$: **Insertions** — a hallucinated or non-existent entity extracted by the system that has no gold counterpart.
- $N_{\text{gold}}$: Total count of gold entities in the reference annotation ($N_{\text{gold}} = \sum (\text{INV} + \text{PO} + \text{GRN} + \text{VND} + \text{Amount})$).

### Target Threshold
$$\text{Overall Entity-WER} \le 3.0\%$$

---

## 2. Task Completion Rate (TCR)

Task Completion Rate evaluates end-to-end operational accuracy for the resolved dispute.

### Definition
For each evaluation sample $i \in \{1, \dots, M\}$:

$$\text{TCR}_i = \begin{cases} 
1.0 & \text{if } \text{Action}_i = \text{Action}_{\text{gold}, i} \land |\text{Amount}_i - \text{Amount}_{\text{gold}, i}| \le \epsilon \land \text{Violations}_i = 0 \\
0.0 & \text{otherwise}
\end{cases}$$

$$\text{TCR} = \frac{1}{M} \sum_{i=1}^M \text{TCR}_i$$

Where:
- $\epsilon = 0.01$ (monetary tolerance for floating-point rounding).
- $\text{Violations}_i = 0$: No unauthorized tool calls, no ERP provenance violations, and no unapproved executions over `HIGH_VALUE_THRESHOLD`.

---

## 3. Tail-Segmented Analysis

A global average obscures catastrophic failures on minority code-mix dialects. VendOps evaluates performance segmented across 6 tail slices:

1. **Script**:
   - `en` (Pure English / Latin)
   - `hi-Latn` (Roman-script Hinglish)
   - `hi-Deva` (Devanagari script)
   - `mixed` (Mixed Devanagari + Latin)
2. **Code-Mix Index (CMI)**:
   - Low ($CMI < 0.2$)
   - Medium ($0.2 \le CMI \le 0.5$)
   - High ($CMI > 0.5$)
3. **Token Fertility**:
   - Low ($< 1.5$ tokens/word)
   - High ($\ge 1.5$ tokens/word, typical in phonetic Hinglish)
4. **Thread Length**:
   - Single turn ($1$ turn)
   - Multi-turn ($2\text{--}5$ turns)
   - Long thread ($> 5$ turns, triggers context compression)
5. **Entity Density**:
   - Sparse ($1\text{--}2$ entities)
   - Dense ($\ge 3$ distinct entities)
6. **Noise Level**:
   - Clean
   - OCR / Typographical noise

### Release Gate Rule
The release gate verifies both **Overall** metrics and the **Worst-Slice** floor:
- $\text{Overall Entity-WER} \le 3.0\%$
- $\min_{\text{slice}} \text{TCR}_{\text{slice}} \ge 80.0\%$
- $\text{Hallucinated Tool Calls Reaching ERP} = 0$
