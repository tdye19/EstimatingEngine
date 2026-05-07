# Sprint 19E Finding — Domain Rule Schema Mismatch

**Date:** 2026-05-07
**Sprint:** 19E (Domain Rules Empirical Validation)
**Status:** Architectural finding documented. Resolution deferred to Sprint 19E.5 war room.
**Author:** Tucker Dye

---

## TL;DR

The 25 domain gap rules (CGR-001..015 + CIV-001..010) encode a gap-detection
semantics that is structurally mismatched to Christman's actual bid document
workflow. The rules were authored in Sprint 17.2-v2, before Agent 2B and the
WorkCategory model existed (Sprint 18.1). Their inputs assume a single
document type — the spec — when Christman bids actually consist of a spec
plus a Work Scope document, with significant scope information living
exclusively in WorkCategory rows.

This is not a corpus gap, a parsing bug, or a rule-logic error. It is a
schema mismatch between when the rules were designed and how the system now
ingests bid documents.

The empirical evidence: project 5, force-rule-based path, 2/25 rules fired,
both labeled FP because the WorkCategory text covered the scope the rules
flagged as missing.

---

## How the rule evaluator actually works

`apex/backend/agents/tools/domain_gap_rules.py::run_domain_rules()` takes
two inputs:

1. `parsed_sections` — list of dicts from `SpecSection` rows (structured:
   division_number + section_number)
2. `spec_content_text` — flat text blob built from `SpecSection.raw_text`
   and related fields

Each rule has three independent gates:

- **CSI scope gate** (`scope_includes_any` / `scope_excludes_all`) —
  evaluated against `parsed_sections`. Determines applicability.
- **Keyword presence gate** (`spec_keywords` + `spec_keyword_match`) —
  evaluated against `spec_content_text`. Fires the rule when keywords
  ARE present, not when they're absent.

The semantic mismatch lives in gate 2. The rules' descriptions read like
"specs mention X but your scope doesn't include 03 15 05 — that's a gap."
But the firing condition is *keywords were found in spec text* — the rule
fires when the spec mentions the topic, regardless of whether the topic
is actually covered elsewhere in the bid documents (e.g., in a
WorkCategory).

---

## The two FPs from project 5, explained

**CIV-006 (Existing Utility Crossings & Conflicts)** fired because:
- CSI scope gate matched (Div 33 11 / 33 31 / 33 41 sections present in
  KCCU SpecSection rows)
- Keyword gate matched somewhere in spec text (or was permissive due to
  thin spec content)

It was labeled FP because WC-02 items 10 and 12 explicitly require MISS-DIG
verification and coordination for existing utility relocations. The scope
is covered. The rule had no way to see WC-02.

**CIV-008 (Trench Safety / Shoring for Utilities)** fired identically. WC-02
Specific Note 6 explicitly requires "trench boxes, ramps and ladders for
safe egress & protection during excavations." Scope covered, rule blind to
WC text.

---

## Why concatenating WorkCategory text into spec_content_text would make this WORSE

The instinctive fix — fold WorkCategory text into `spec_content_text` so
the rules can see it — appears clean but inverts the wrong gate. The
keyword gate fires *more confidently* when keywords are present. If WC-02
mentions "Miss Dig" and "trench boxes," concatenating WC text into the
keyword corpus makes both rules' keyword gates match more strongly, not
less. The rules would still fire. The FPs would still be FPs.

Suppressing on WC presence requires a *new gate semantics* — "if these
keywords appear in WorkCategory text, the topic is covered, do NOT fire" —
which is structurally different from any of the three current gates.

---

## Why this happened — chronology

- **Sprint 17.2-v2 (April 2026)** — 25 domain rules authored. APEX at that
  time ingested only spec PDFs. The rule schema correctly modeled "spec
  mentions topic X, your scope (concrete CSI codes) doesn't include the
  related work" as a gap detection problem.
- **Sprint 18.1 (April 21, 2026)** — Agent 2B and the WorkCategory model
  shipped. Bid documents now have a second source of scope information
  that the rule evaluator was never updated to consume.
- **Sprint 19E (May 5–7, 2026)** — first attempt to empirically validate
  the rules. KCCU Vol 2 used as test corpus. Pipeline complexity and a
  series of stale-state bugs masked the schema mismatch until project 5's
  clean run plus the force-rule-based admin path isolated the rule output.

The rules are not wrong for the project type they were designed for
(spec-only). They are wrong for Christman's actual document workflow.

---

## Three directions for resolution (Sprint 19E.5 war-room candidates)

Not recommendations — options to debate. Listed in order of increasing
engineering effort.

### Direction A — Add `scope_covered_in_workcategory` suppression field

Each rule gets a new optional field listing keywords that, if found in
WorkCategory text, suppress the rule's firing. Cheap to encode by editing
the 25 rule definitions. Fires correctly on KCCU-style projects.

**Tradeoff:** Encodes Christman's specific WC numbering and phrasing
conventions into rule data. Other clients with different WC conventions
break the suppression.

### Direction B — Restructure rules to consume (SpecSection, WorkCategory, takeoff) symmetrically

Rules become "given (parsed_sections, work_categories, spec_text,
takeoff_items), is the topic covered or not?" The evaluator reasons about
coverage, not just keyword presence. Real refactor — touches
`domain_gap_rules.py`, every rule's data shape, the evaluator, the tests.

**Tradeoff:** This is the right answer if rules-as-moat is the long-term
play. It is not a hotfix. Probably 1–2 sprints of dedicated work.

### Direction C — Retire the rules as a primary path; bank their data as LLM prompt enrichment

The LLM path on project 5 produced 36 gaps with no rule input. If the LLM
is already covering the gap-detection surface, the rules' *structural form*
may be obsolete — but their *data* (cost ranges, RFI language, typical
responsibility, rule_id provenance) is still valuable as prompt context.
Restructure the rules into a knowledge base that grounds Agent 3's LLM
prompt rather than a parallel deterministic engine.

**Tradeoff:** Cedes the "deterministic engine disposes" doctrine point on
gap analysis. Banks the moat as data, not as code. Significant
philosophical shift.

### Direction D (mentioned for completeness) — Hybrid: rules as deterministic check on LLM output

After the LLM produces gaps, run the rules. For any rule that fires but is
not represented in the LLM gap set, surface as "rule_check_disagreement"
for estimator review. Rules become audit, not primary intelligence.

**Tradeoff:** Doesn't fix the schema mismatch — same FPs, just shown in a
different lane. Only useful if Direction A or B has happened first.

---

## What this means for the LLM-primary architecture

The May 7 evening reading of `agent_3_gap_analysis.py` confirmed: on every
healthy production run, the 25 rules are dead code. This finding makes
that observation sharper.

The LLM path produces gaps shaped to the project's actual document set.
The rule path produces gaps shaped to a document set that doesn't exist
on Christman bids. **If 19E.5 picks merge-as-is, the rules add false
positives to the LLM's true positives.** The merge wouldn't help; it
would dilute.

The merge-vs-fallback decision is not architecturally neutral. It
depends on whether the rules' schema is fixed first.

---

## Doctrine implications

This finding sits across three doctrine items:

- **#1 (deterministic engine disposes)** — On gap analysis, there is no
  deterministic disposer in production. The LLM proposes and disposes.
  Direction B preserves doctrine #1 fully. Direction C concedes it for
  gap analysis specifically.
- **#2 (historical data is the moat)** — The 25 rules carry rule_id,
  cost ranges, RFI language sourced from Christman experience. If the
  rules are restructured (B) or retired into prompt context (C), the
  data survives — its delivery mechanism changes.
- **#4 (show evidence, not abstracted confidence)** — Rule-shaped gaps
  carry richer evidence (rule_id, typical_responsibility, cost ranges)
  than LLM-shaped gaps. Whatever 19E.5 picks, the LLM gap output should
  be enriched to match the rule output's evidence density.

---

## Status of Sprint 19E

| Item | Status |
|---|---|
| 19E.3 — silent-fallback visibility | ✅ Shipped |
| HF-26 — CrewOrchestrator removal | ✅ Shipped |
| 19E.0-DIAG — diagnostic CLI | ✅ Shipped |
| 19E.UPLOAD — clean pipeline run on project 5 | ✅ Shipped |
| 19E.V — force_rule_based admin path + harness | ✅ Shipped |
| 19E.4 — calibration corpus (Div 03 bid packages) | ⏳ Open, but reframed: corpus is not the limiting factor |
| 19E.5 — rule schema architectural decision | ⏳ War-room candidate, NOT a coding task |
| HF-28 (concatenate WC text into spec_content_text) | ❌ Cancelled — would worsen FPs, not fix them |

---

## Next session

Sprint 19E.5 war-room session. Builder / Critic / Strategist / Estimator
perspectives on Directions A through D above. Output: a directional
decision plus an implementation sprint scoped to that direction.

Not a coding session. A thinking session.
