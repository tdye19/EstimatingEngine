# PATCH-1-AGENT-2-HARD-FAIL

Safety refactor: Agent 2 hard-fail + Agent 2B lifecycle promotion.

---

## What Changed

### A. Agent 2 regex fallback removed (hard-fail)

**File:** `apex/backend/agents/agent_2_spec_parser.py`

- Removed `regex_parse_spec_sections` from all imports and call sites.
- Added two explicit exception classes at the top of the module:
  - `Agent2ProviderUnavailableError(RuntimeError)` — raised when the LLM provider cannot be initialised or fails its health check.
  - `Agent2LLMParseFailure(RuntimeError)` — raised when the provider is reachable but its response cannot be parsed into valid SpecSection data.
- `_parse_document()` now has a single LLM path. Any non-billing exception from the LLM call is wrapped in `Agent2LLMParseFailure` and re-raised. There is no fallback.
- `run_spec_parser_agent()` fails immediately on provider init or health-check failure with `Agent2ProviderUnavailableError` — the provider check is no longer advisory.
- Both exception types bubble out of the per-document loop. A new outer `except` block catches them, **deletes all partial SpecSection rows** for the project, commits, and re-raises. This guarantees the DB is never left in a partial state from a mid-run hard failure.

### B. Agent 2B promoted into the pipeline lifecycle

**Files:** `apex/backend/services/agent_orchestrator.py`, `apex/backend/agents/pipeline_contracts.py`, `apex/backend/agents/agent_2b_work_scopes.py`

- Agent 2B is now registered in `AGENT_DEFINITIONS` as integer key `25` (displayed as "2B", stored as 25 — same convention as 35 for "3.5").
- Added to `pipeline_agents = [1, 2, 25, 4, 3, 35, 5, 6]` — executes immediately after Agent 2.
- The old special-cased sidecar block (post-Agent-2 inline call) has been removed.
- Agent 2B now receives full orchestrator lifecycle coverage:
  - `AgentRunLog` entries written by `_log_start` / `_log_complete` / `_log_error`.
  - `ws_status` tracking in `pipeline_update` WebSocket frames.
  - Retry behaviour consistent with other pipeline agents (AGENT_MAX_RETRIES).
  - Skipped in `winest_import` mode (same as Agent 2).
- `_CONTRACT_MAP[25] = Agent2BOutput` and `AGENT_NAMES[25]` added in `pipeline_contracts.py`.
- `run_work_scope_agent()` now calls `validate_agent_output(25, ...)` instead of the no-op `validate_agent_output(0, ...)`.
- Added `_NON_BLOCKING_AGENTS: frozenset[int] = frozenset({25})` in the orchestrator. Agents in this set record visible failure (AgentRunLog + ws_status) but do **not** set `failed_at`, so downstream agents continue.
- `get_pipeline_status()` now iterates `[1, 2, 25, 4, 3, 35, 5, 6]` instead of `range(1, 7)`.

---

## Files Changed

| File | Change |
|------|--------|
| `apex/backend/agents/agent_2_spec_parser.py` | Removed regex fallback; added exception classes; hard-fail on provider/parse failure; cleanup on failure |
| `apex/backend/services/agent_orchestrator.py` | Registered agent 25; added to pipeline_agents; added `_NON_BLOCKING_AGENTS`; removed sidecar block; updated `get_pipeline_status()` |
| `apex/backend/agents/pipeline_contracts.py` | Added `25: Agent2BOutput` to `_CONTRACT_MAP`; added `25` to `AGENT_NAMES` |
| `apex/backend/agents/agent_2b_work_scopes.py` | Changed `validate_agent_output(0, ...)` to `validate_agent_output(25, ...)` |
| `apex/backend/tests/test_patch1_agent2_hardfail.py` | New: 19 acceptance-criteria tests |
| `apex/backend/tests/test_hf26_agent2_cleanslate.py` | Updated: added provider mocking (tests previously relied on implicit regex fallback reaching the doc-processing stage) |

---

## Previous Behaviour

| Scenario | Old behaviour |
|----------|---------------|
| LLM provider unreachable | Logged warning; silently fell back to regex; produced SpecSection rows from pattern matching |
| LLM returns unparseable output | Logged warning; silently fell back to regex; continued pipeline |
| Billing failure (402) | Already raised `LLMProviderBillingError`; pipeline halted |
| Agent 2B failure | Logged exception; set `results["agent_2b"] = {"status": "failed"}`; no AgentRunLog; not visible in ws_status |
| Agent 2B lifecycle | Called as inline sidecar after Agent 2, outside `pipeline_agents`; no AgentRunLog; no ws_status; no retry |

---

## New Behaviour

| Scenario | New behaviour |
|----------|---------------|
| LLM provider unreachable | Raises `Agent2ProviderUnavailableError`; partial SpecSection rows deleted; orchestrator marks Agent 2 failed; downstream agents skipped; `pipeline_error` WS event emitted; project status = "failed" |
| LLM returns unparseable output | Raises `Agent2LLMParseFailure`; same halt path as above |
| Billing failure (402) | Unchanged — raises `LLMProviderBillingError`; project status = "failed_billing" |
| Agent 2B failure | AgentRunLog created with status="failed"; ws_status shows "failed" for agent 25; `pipeline_update` broadcast includes failure; downstream agents **continue** (non-blocking) |
| Agent 2B lifecycle | Full pipeline citizen: AgentRunLog, ws_status, retry, winest_import skip, contract validation |

---

## Explicit Failure Modes

### Agent 2 failures (pipeline-halting)

1. **`Agent2ProviderUnavailableError`** — provider cannot be initialised (`get_llm_provider()` raises) or fails health check. No SpecSection rows exist after this failure.
2. **`Agent2LLMParseFailure`** — provider reachable but LLM response failed parsing. Partial rows from earlier docs in the same run are deleted.
3. **`LLMProviderBillingError`** — unchanged path; project status = "failed_billing".
4. **`TokenBudgetExceeded`** — unchanged path; pipeline halts with budget_exceeded status.

In all four cases `failed_at = 2`, downstream agents are skipped, the final `pipeline_error` WebSocket event names `failed_at_agent: 2`, and project.status transitions to "failed" or "failed_billing".

### Agent 2B failures (non-halting, visible)

Agent 2B failures propagate normally through the orchestrator's generic exception handler. Because `25 in _NON_BLOCKING_AGENTS`, `failed_at` is **not** set. Instead:
- `ws_status[25]["status"] = "failed"` — visible in all `pipeline_update` frames
- `AgentRunLog.status = "failed"` with `error_message` populated
- `results["agent_25"] = {"status": "failed", "error": "..."}`
- Pipeline continues to agents 4, 3, 35, 5, 6

---

## Agent 2B: Fail-Required or Optional?

**Decision: Optional (non-blocking), with visible failure.**

Rationale:
- Agent 2B is additive: it parses Work Scope documents into `WorkCategory` rows that Agent 3.5 and Agent 6 consume for scope matching and proposal form generation.
- Downstream agents degrade gracefully when `WorkCategory` rows are absent — Agent 3.5 produces fewer scope findings; Agent 6 produces a proposal form with no WC attribution; neither crashes.
- The original design comment was explicit: "Additive intelligence: a failure must not block Agents 3/4/5/6/7."
- "Silent ambiguity" has been eliminated: the failure is now truthfully surfaced in AgentRunLog, ws_status, and `pipeline_update` events.

If future work makes Agent 3.5 require WorkCategory rows (e.g. it aborts when no WCs exist), move `25` out of `_NON_BLOCKING_AGENTS` at that time.

---

## Follow-up Risks Not Addressed in This Patch

1. **`_enrich_division_03_parameters()` is still soft-fail**: per-section enrichment failures are logged and captured in warnings but never halt Agent 2. If enrichment quality matters for downstream agents, it may need its own hard-fail gate.

2. **No partial-run recovery**: if Agent 2 hard-fails mid-run (doc 3 of 10 fails), all committed rows from docs 1–2 are deleted. There is no mechanism to resume from doc 3. A future retry would re-parse all docs from scratch.

3. **Agent 2B `ws_status` display name**: the frontend currently receives `agent_number: 25` with `agent_name: "Work Scope Parser Agent"`. If the frontend renders "Agent 25" instead of "Agent 2B", a display-layer mapping is needed.

4. **`get_pipeline_status()` REST API shape change**: the endpoint now returns 8 agent status entries (1, 2, 25, 4, 3, 35, 5, 6) instead of 6 (1–6). If any frontend client iterates this list with a hard-coded length assumption, it will need updating.

5. **Work scope regex fallback still exists in `work_scope_parser.py`**: Agent 2B's parser service still falls back to regex when its LLM call fails. This is lower-risk (Work Scope rows are supplementary, not structural) but should be reviewed under the same hard-fail philosophy if Work Scope parsing becomes load-bearing.

6. **No idempotency guarantee for Agent 2B on re-run**: Agent 2B does not clean-slate WorkCategory rows before re-parsing (unlike Agent 2's HF-26 clean-slate). A re-run on the same project will upsert existing rows but may leave stale WC rows from documents that no longer classify as work_scope. A clean-slate delete-then-repopulate should be added when Agent 2B stabilises.

---

## Acceptance Criteria Status

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Agent 2 cannot silently fall back to regex | ✅ Removed; no `regex_parse_spec_sections` call in any path |
| 2 | Provider billing/outage → visible failed pipeline state | ✅ Hard-fail raises; orchestrator sets project.status="failed"; pipeline_error WS event |
| 3 | No fake SpecSection rows written on Agent 2 failure | ✅ Cleanup block deletes partial rows on `Agent2LLMParseFailure` / `Agent2ProviderUnavailableError` |
| 4 | No downstream stage runs after Agent 2 failure | ✅ `failed_at = 2` causes all subsequent agents to be skipped |
| 5 | Agent 2B in orchestrator lifecycle and observability | ✅ Registered as agent 25 in AGENT_DEFINITIONS and pipeline_agents |
| 6 | Agent 2B produces AgentRunLog entries | ✅ Same `_log_start` / `_log_complete` / `_log_error` path as all other agents |
| 7 | Agent 2B emits WebSocket progress/error visibility | ✅ ws_status[25] included in all `pipeline_update` broadcasts |
| 8 | Existing successful LLM-based spec parsing still works | ✅ test_successful_llm_parse_still_works passes; 254 suite tests pass |
| 9 | Existing successful work scope parsing still works | ✅ test_agent_2b_work_scopes.py: 4 tests pass |
| 10 | Frontend no longer reports healthy when stages fail | ✅ ws_status includes Agent 2 "failed" and Agent 2B "failed" in pipeline_update frames |

---

## Manual Verification Steps

1. **Known-good project**: upload spec + work scope docs; trigger pipeline. Confirm Agent 2 parses via LLM, Agent 2B appears in status panel as "completed" with an AgentRunLog entry at agent_number=25.

2. **Provider failure simulation**: set `AGENT_2_PROVIDER=ollama` with Ollama not running. Trigger pipeline. Verify:
   - Pipeline stops at Agent 2.
   - `project.status = "failed"` in DB.
   - `pipeline_error` WS event with `failed_at_agent: 2`.
   - `SELECT count(*) FROM spec_sections WHERE project_id = ?` returns 0.
   - Agents 25, 4, 3, 35, 5, 6 all show status="skipped" in AgentRunLog.

3. **Agent 2B failure simulation**: monkey-patch `run_work_scope_agent` to raise. Trigger pipeline. Verify:
   - Pipeline reaches and completes Agent 6.
   - `pipeline_status = "completed"` (not stopped).
   - AgentRunLog for agent_number=25 has status="failed".
   - `pipeline_update` WS frames include `agents[25]["status"] = "failed"`.

4. **Billing failure simulation**: configure OpenRouter with exhausted credits. Trigger pipeline. Verify:
   - `project.status = "failed_billing"`.
   - `pipeline_error` WS event with `status: "failed_billing"`.
   - No SpecSection rows in DB.
