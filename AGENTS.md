# AGENTS.md - VendOps Multi-Agent Operating Contract

This document governs the engineering standards, file boundaries, and behavioral rules for all agents and subagents working in the **VendOps** repository.

---

## 1. Non-Negotiable Ground Rules

1. **Frozen Contracts**:
   - `src/vendops/contracts/` is **FROZEN**.
   - No subagent is permitted to edit files in `src/vendops/contracts/` without explicit authorization from the Staff Orchestrator.
   - If your stream requires a schema change, report the request in your output report; do not modify contracts directly.

2. **Zero Tool-Call Hallucination**:
   - Every tool call parameter must strictly validate against Pydantic models with `extra="forbid"`.
   - Every ID (`INV-...`, `PO-...`, `GRN-...`, `VND-...`) passed to an ERP tool must satisfy the **Provenance Check**: it must exist in either the user dispute message or an earlier verified tool response.
   - Invented or guessed IDs are strictly rejected.
   - Write tools accept **only** the `ActionType` enum (`CREDIT_NOTE`, `REPLACEMENT`, `PARTIAL_PAYMENT`, `RELEASE_PAYMENT`, `REJECT`, `ESCALATE`). Free-text mutation actions are strictly forbidden.

3. **Secrets & Security**:
   - Never print, echo, log, or commit `.env` or any API keys.
   - Use `python-dotenv` and read environment variables only via `pydantic-settings` or `os.environ`.
   - All external inputs must be validated at the system boundary.

4. **Environment & Tooling (Windows 11 / PowerShell)**:
   - Use `uv run poe <task>` rather than `make`.
   - Use `pathlib.Path` for all file operations (no hardcoded `/` or `\` string paths).
   - Python code must pass `ruff check .` and `mypy --strict src`.
   - All tests must pass with `uv run pytest`.

5. **Offline & Deterministic Execution**:
   - All unit tests and CI workflows must execute 100% offline using `FakeLLM` or recorded fixtures.
   - Live external model API calls must implement jittered exponential backoff for rate limit (429) resilience.

---

## 2. Stream File Ownership & Boundaries

Every subagent works in an isolated Git worktree on its assigned branch and is restricted to its owned directories:

| Subagent Stream | Branch | Owned Directories / Files | Read-Only Dependencies |
|---|---|---|---|
| **Stream 1: ERP-MCP** | `feat/erp-mcp` | `src/vendops/erp/**`<br>`src/vendops/mcp_server/**`<br>`tests/test_erp_mcp.py` | `src/vendops/contracts/**`<br>`vendor/mcp-python-sdk/**` |
| **Stream 2: GRAPH** | `feat/graph-core` | `src/vendops/graph/**`<br>`src/vendops/guard/**`<br>`tests/test_graph.py`<br>`tests/test_guard.py` | `src/vendops/contracts/**`<br>`vendor/indic-transliteration/**` |
| **Stream 3: RAG-API** | `feat/rag-api` | `src/vendops/rag/**`<br>`src/vendops/api/**`<br>`tests/test_rag.py`<br>`tests/test_api.py` | `src/vendops/contracts/**`<br>`vendor/fastapi-langgraph-agent/**` |
| **Stream 4: EVALS** | `feat/evals-gate` | `evals/**`<br>`scripts/**`<br>`.github/workflows/**`<br>`tests/test_evals.py` | `src/vendops/contracts/**` |
| **Stream 5: RED-TEAM** | `feat/red-team` | `tests/adversarial/**` | All codebase (read-only) |

---

## 3. Subagent Deliverable Requirements

When completing a task, each subagent must provide a concise report containing:
1. **Status**: What was implemented and what remains.
2. **Verification Command**: The exact `uv run ...` command executed and its output.
3. **Contracts Used**: Schemas and enums referenced from `src/vendops/contracts/`.
4. **Open Risks**: Edge cases or integration concerns for the Orchestrator.
