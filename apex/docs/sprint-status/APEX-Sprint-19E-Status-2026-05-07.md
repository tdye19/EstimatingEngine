# Sprint 19E Status — End of 2026-05-07 Session

**Sprint goal (original):** Empirically validate the 25 domain gap rules
against real Christman bid content; refine rule logic where precision falls
below 90%.

**Sprint goal (revised after empirical evidence):** Document the architectural
finding that emerged from validation. Defer rule refinement until the schema
mismatch question is resolved in Sprint 19E.5.

## Shipped

- **19E.3** — Agent 3 silent-fallback visibility. WARN log + new
  `analysis_method = "rule_based_empty_fallback_to_checklist"` metadata
  state when domain rules return zero findings on rule-based path.
- **HF-26** — Stale `CrewOrchestrator` removed (defined wrong pipeline
  order, omitted Agent 3.5).
- **19E.0-DIAG** — `apex/backend/scripts/diagnose_agent2_coverage.py`.
  Read-only CLI dumping Agent 2 + Agent 2B state per project. Used to
  invalidate two May 6 bug hypotheses (Agent 2 Div 31/32/33 miss and
  Agent 2B 0.020s no-op were both stale-state misreads).
- **19E.UPLOAD** — Clean validation pipeline run on project 5 with both
  KCCU spec PDF and KCCU Vol 2 Work Scopes PDF. Confirmed: Agent 2 LLM
  (665s, 19 SpecSections including Divs 31/32/33), Agent 2B LLM (247s,
  8 WorkCategories), Agent 3 LLM (36 gaps via LLM path), zero failures.
- **19E.V** — `force_rule_based` parameter on `run_gap_analysis_agent`
  (default False, production behavior unchanged). Admin endpoint
  `POST /api/admin/projects/{id}/agent-3/force-rule-based` for empirical
  rule validation without altering production path. Both LLM and
  rule_based GapReports preserved on project 5 for comparison.

## Empirical result

Force-rule-based on project 5: 2/25 rules fired (CIV-006, CIV-008), both
labeled FP. Manual labeling root cause: WC-02 explicitly covers both
findings. CGR rules (15) correctly silent — no Div 03 content in KCCU
Vol 2.

Precision number (0%) is non-meaningful; the architectural finding from
the labeling exercise is the actual deliverable.

## Architectural finding

Domain rule schema mismatch with Christman's actual bid document workflow.
Documented in `apex/docs/architecture/19E-finding-domain-rule-schema-mismatch.md`.

Summary: rules were authored in Sprint 17.2-v2 before WorkCategory data
existed. Their keyword-presence gate fires on spec mentions of a topic,
regardless of whether the topic is covered in a WorkCategory. On
Christman bids, scope information lives in both spec sections and Work
Categories — rules are blind to half of it.

## Cancelled / non-issues

- **19E.1 (Agent 2 Div 31/32/33 fix)** — was a stale-state misread.
  Agent 2 working as designed.
- **19E.2 (Agent 2B short-circuit fix)** — was a missing-document
  misread. Agent 2B gate working as designed.
- **HF-28 (concatenate WorkCategory text into `spec_content_text`)** —
  hypothesis tested against the actual evaluator code on 2026-05-07.
  Concatenation would make both FPs fire MORE confidently because the
  keyword presence gate fires on keyword presence, not absence. The fix
  would worsen the precision number, not improve it. Cancelled.

## Open

- **19E.4 (calibration corpus expansion)** — original plan was to source
  Div 03 bid packages to enable CGR rule validation. Reframed: corpus
  expansion would not change the schema mismatch finding. Worth doing
  for breadth of validation, but not the limiting factor.
- **19E.5 (architectural decision)** — directional choice between four
  resolution paths (A, B, C, D in the architectural finding doc). NOT
  a coding task. War-room session — Builder / Critic / Strategist /
  Estimator perspectives — to produce a decision plus an
  implementation sprint scoped to that decision.

## Implications for adjacent sprints

- **Sprint 19F (WC-SPEC-LINK hero feature)** — partial dependency.
  Direction B in 19E.5 (restructured rules consuming SpecSection +
  WorkCategory + takeoff symmetrically) overlaps with the WC-SPEC-LINK
  data plumbing. If 19E.5 picks B, fold into 19F. If 19E.5 picks A or
  C, 19F stays scoped as planned.
- **Pilot readiness** — production LLM path on Agent 3 is healthy.
  Project 5 produced 36 gaps with critical_count = 30. Pilot is not
  blocked on 19E.5 — the gap-analysis surface works on a real Christman
  bid via the LLM path. 19E.5 is a *quality of the moat* decision,
  not a *can we ship* decision.
