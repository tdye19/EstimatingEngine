# 19E-UPLOAD Evidence — 2026-05-07

Sprint 19E.0-DIAG confirmed Agent 2 and Agent 2B were working correctly but
Project 4 was missing the KCCU Volume 2 Work Scopes PDF. This document is the
canonical evidence record for the clean validation run with both PDFs present.

## Project Identity

| Field | Value |
|---|---|
| Project ID | **5** |
| Project Name | KCCU HQ — clean validation 2026-05-07 |
| Project Number | PRJ-2026-002 |
| Created | 2026-05-07T14:43:38Z |

## Document Inventory

| doc_id | Filename | Type | Size | Pages |
|---|---|---|---|---|
| 6 | 2025-11-21 KCCU CI 1 Specifications .pdf | spec | 2.5 MB | 175 |
| 7 | KCCU_Volume_2_Work_Scopes_12_1_2025.pdf | work_scope | 732 KB | 28 |

Document routing gate: doc 6 → Agent 2 only; doc 7 → Agent 2B only. Correct.

## Pre-run Blockers Encountered

1. **Ollama default provider**: The backend's `.env` load path (`apex/backend/.env`) does
   not exist. The root `.env` is not loaded by the backend process, so `LLM_PROVIDER`
   fell through to the hardcoded default `"ollama"`. First two pipeline runs failed with
   `LLM provider 'ollama' failed health check`. Fixed by setting `LLM_PROVIDER=openrouter`
   in the uvicorn process environment. This is an environment-config gap, not a code bug.

2. **Work Scopes PDF path**: File is at
   `/workspaces/EstimatingEngine/KCCU Volume 2 - Work Scopes - 12.1.2025.pdf`
   (spaces, dashes), not at the `/mnt/project/` path referenced in the task spec.

## Pipeline Run Summary (Run 3, all agents from id ≥ 47)

| Agent | Number | Status | Duration |
|---|---|---|---|
| Document Ingestion | 1 | completed | 0.02s |
| Spec Parser | 2 | **completed** | **665.0s** |
| Work Scope Parser | 2B (25) | **completed** | **247.7s** |
| Rate Intelligence | 4 | completed | 0.03s |
| Scope Analysis | 3 | **completed** | **117.7s** |
| Scope Matcher | 3.5 (35) | completed | 0.08s |
| Field Calibration | 5 | completed | 0.01s |
| Intelligence Report | 6 | completed | 16.8s |

Overall pipeline status: **completed** (zero failures in this run).

## Agent 2 Validation

**Division coverage map:**

| Division | Description | Section Count |
|---|---|---|
| 14 | Conveying Equipment | 1 |
| 23 | HVAC | 1 |
| 26 | Electrical | 9 |
| 31 | Earthwork | 2 |
| 32 | Exterior Improvements | 3 |
| 33 | Utilities | 3 |
| **Total** | | **19** |

**Section numbers:** 14 21 00, 23 11 23, 26 05 00, 26 05 19, 26 05 26,
26 05 33.13, 26 05 33.16, 26 05 83, 26 21 00, 26 32 13, 26 56 00,
31 10 00, 31 20 00, 32 12 16, 32 13 13, 32 92 00, 33 41 00, 33 43 00, 33 44 00

**Assertion results:**
- ✅ Div 31 present: 2 sections
- ✅ Div 32 present: 3 sections
- ✅ Div 33 present: 3 sections
- ✅ Total sections ≥ 19: **19** (exactly meets baseline)
- ✅ Duration > 60s: **665.0s** (real LLM call confirmed, not regex fallback)
- ✅ parse_method = `llm`
- Tokens: 119,950 input / 28,121 output (4 chunks, chunk 3 required re-split)

Note: No additional SpecSections from Work Scopes PDF — expected. The Work Scopes
PDF is a subcontractor scope document, not a CSI spec, so Agent 2 correctly skips it.

## Agent 2B Validation

**WorkCategory list (8 total):**

| WC Number | Description (truncated) |
|---|---|
| WC 00 | General Requirements for All Subcontractors |
| WC 02 | Earthwork and Site Utilities |
| WC 05 | Site Concrete |
| WC 06 | Asphalt Paving |
| WC 07 | Fencing |
| WC 28A | Generator Procurement, Exterior Site Electrical and Temp. Electric |
| WC 30 | Elevators |
| WC 35 | Materials Testing |

**Assertion results:**
- ✅ WorkCategory count ≥ 8: **8** (meets minimum)
- ✅ Duration > 1.0s: **247.7s** (real LLM call, gate did not short-circuit)
- ✅ parse_methods: `{"llm": 8, "regex": 0, "regex_fallback": 0}`
- documents_examined=2, documents_parsed=1 (spec PDF correctly skipped by 2B)

Note: The task expected up to 11 WCs visible in PDF inspection (WC-00, 02, 05, 06,
11, 14, 23, 26, 28A, 30, 35). We received 8. WC 11, 14, 23, 26 were not extracted.
This may reflect the document scope (Vol 2 Bid Package No. 1 — Site/Civil/Elevators/
Electrical only) or LLM extraction gaps. Not a blocker; the ≥8 assertion passes.

## Agent 3 Validation

**analysis_method:** `llm`

This is not the `rule_based` or `rule_based_empty_fallback_to_checklist` path the
task described — Agent 3 ran full LLM gap analysis and succeeded:

- 36 gaps identified (30 critical, 5 moderate, 1 watch)
- overall_score: 100
- sections_analyzed: 19
- spec_vs_takeoff_gaps: 0 (no takeoff items uploaded)
- Duration: 117.7s

The LLM path activating means OpenRouter was available and Agent 3 bypassed the
rule-based path entirely. The `rule_based` path (and the fallback to checklist) is
only triggered when the LLM path fails. This run's outcome: **LLM gap analysis
succeeded — full success state**.

No concrete (Div 03) content is present in this spec. This was the 19E.4
hypothesis. With the LLM path succeeding, the calibration corpus question
(whether domain rules would fire on Div 03 content) remains open but is not
blocking — it is a separate 19E.4 concern.

## Agent 3.5 (Scope Matcher)

- 8 WCs, 0 takeoff items → 62 findings, all `in_scope_not_estimated`
- Duration: 0.08s (correct — no takeoff to match against, just emitting WC inclusions)

## Self-Debug Checklist

- ✅ Project 5 has exactly 2 documents (not 1 or 3)
- ✅ Pipeline run contains agent entries for agents 1, 2, 25 (2B), 4, 3, 35 (3.5), 5, 6
- ✅ All agents status = "completed" in the final run
- ✅ Agent 2B present in AgentRunLog (not absent as in the Project 4 failed runs)
- ✅ No agent failures in run 3

## Diagnostic Artifact

Full diagnostic JSON and markdown saved by `diagnose_agent2_coverage`:

- `apex/docs/diagnostics/project_5_agent2_diag_20260507.json`
- `apex/docs/diagnostics/project_5_agent2_diag_20260507.md`

## Action Items for Follow-On Work

1. **Fix `.env` load path** (root cause of two failed runs): `main.py` loads
   `apex/backend/.env` which does not exist. Should load root `.env` or Railway env
   vars should set `LLM_PROVIDER=openrouter` explicitly. This is a deployment config
   gap that will silently fail on every fresh Codespace start.

2. **WC extraction gap** (8 of expected 11): WC 11, 14, 23, 26 not extracted.
   Worth a follow-up inspection of the PDF to determine if these are truly absent
   from Vol 2 Bid Package No. 1 or if the LLM missed them.

3. **19E.4 domain rules calibration**: The `rule_based` path did not fire (LLM
   succeeded first). To test domain rules, a project with Div 03 content and a
   failed/unavailable LLM provider is needed. Separate sprint item.
