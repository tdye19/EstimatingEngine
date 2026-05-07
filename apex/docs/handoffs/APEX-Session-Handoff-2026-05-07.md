# APEX Session Handoff — May 7, 2026

**Session date:** Thursday May 7, 2026 (single extended day session)
**Prior state:** Sprint 19E.0-DIAG and 19E.3 + HF-26 specs ready to run; May 6 handoff identified two upstream bugs blocking domain rule validation.
**End state:** Sprint 19E substantially closed with architectural finding banked, two ghost bugs from May 6 retired, two Sprint 19B hardening items shipped, two new product surface proposals scoped and ordered, war-room decision artifact ready for next session.

---

## ⭐ THE SESSION IN ONE LINE

Diagnostic-first methodology paid off — reversed two false bug reports, shipped two hardening items, banked an architectural finding with four-direction decision framework, scoped two new product proposals, all in one session at 363 tests passing.

---

## What shipped to main this session

| Commit | Title | Impact |
|---|---|---|
| (HF-26 + 19E.3) | Agent 3 silent-fallback visibility + remove stale CrewOrchestrator | Doctrine #4 visibility fix, dead code removal |
| (19E.0-DIAG) | diagnose_agent2_coverage CLI | Read-only diagnostic that invalidated two May 6 bug hypotheses |
| (19E-UPLOAD) | Clean KCCU pipeline run on project 5 | Validation evidence for end-to-end pipeline |
| (19E.V) | force_rule_based admin path + harness | Empirical rule validation without altering production |
| (19E finding) | Architectural finding doc — domain rule schema mismatch | Banked the real bug |
| (19E.5 war room) | Decision framework with 4 directions | War-room artifact for next session |
| (19B.1) | Retire runtime ALTER TABLE for project context columns | Migration hygiene; pilot prep |
| (19B.2) | Retire `?token=` query param for document URLs | Token leak via referrer/logs closed |
| (Backlog proposals) | Insurance/Bond + Contract Cost Intelligence proposals | Two new product surfaces scoped, slotted Sprint 22.5/22.6 |
| (.gitignore) | Untrack .claude/ local state | Prevents future accidental commits |

Total: ~10 commits, +11 new tests on 19B.2 alone, full suite at 363 passed, 20 skipped.

---

## Sprint 19E — substantially closed

| Item | Status |
|---|---|
| 19E.3 — Agent 3 silent-fallback visibility | ✅ Shipped |
| HF-26 — CrewOrchestrator removal | ✅ Shipped |
| 19E.0-DIAG — diagnostic CLI | ✅ Shipped |
| 19E.UPLOAD — clean pipeline run on project 5 | ✅ Shipped |
| 19E.V — force_rule_based admin path + harness | ✅ Shipped |
| 19E architectural finding | ✅ Documented |
| 19E.5 war-room decision framework | ✅ Drafted, banked |
| 19E.1 (Agent 2 Div 31/32/33 fix) | ❌ Cancelled — was a stale-state misread |
| 19E.2 (Agent 2B short-circuit fix) | ❌ Cancelled — was a missing-document misread |
| HF-28 (concatenate WC text into spec_content_text) | ❌ Cancelled — would worsen FPs not fix them |
| 19E.4 (calibration corpus expansion) | ⏳ Open, not coding work |
| 19E.5 (architectural decision) | ⏳ War-room ready, decision deferred |

---

## The architectural finding (the day's most important deliverable)

The 25 domain gap rules (CGR-001..015 + CIV-001..010) have a schema
mismatch with Christman's actual bid document workflow. They were
authored Sprint 17.2-v2, before WorkCategory existed (Sprint 18.1).
Their keyword-presence gate fires on spec mentions of a topic, blind
to whether the topic is covered in WorkCategory rows.

Empirical evidence: project 5 force-rule-based run produced 2/25 rules
firing (CIV-006, CIV-008), both labeled FP. Both findings are explicitly
covered by KCCU WC-02 — the rules had no way to see WC text.

**Critical secondary finding:** on every healthy production run, the 25
rules are dead code. The LLM path succeeds first; rule_based is fallback
only. The "rules as moat" framing needs a directional decision.

Documented in:
- `apex/docs/architecture/19E-finding-domain-rule-schema-mismatch.md`
- `apex/docs/architecture/19E_5-war-room-decision-framework-2026-05-07.md`

Four directions debated in the war room:
- **A** — `scope_covered_in_workcategory` keyword suppression field (1 sprint, ~tactical)
- **B** — restructure rules to consume (SpecSection, WC, takeoff) symmetrically (2-3 sprints, doctrine-aligned)
- **C** — retire rules as primary path, bank data as LLM prompt enrichment (1 sprint, cedes doctrine #1 for gap analysis)
- **D** — hybrid: rules as deterministic check on LLM output (1 sprint, requires A or B underneath)

Decision target: pick a direction next session, name the ONE thing that
would make the choice wrong, define what success looks like at end of
implementation sprint.

---

## Sprint 19B (schema/migration hygiene) — partial

| Item | Status |
|---|---|
| 19B.1 — Retire runtime ALTER TABLE | ✅ Shipped |
| 19B.2 — Retire `?token=` query param | ✅ Shipped |
| 19B.3 — Other runtime safety nets (sweep) | ⏳ Open |

19B.1 details:
- Migration `3a69638ff6bd_retire_runtime_alter_for_project_.py` created
- 9 columns moved from runtime ALTER to proper Alembic migration
- Idempotent upgrade (production DBs already have columns from runtime
  ALTER → skipped; new DBs get columns added)
- `ensure_project_context_columns()` and `init_db()` deleted from
  `apex/backend/db/database.py`
- `init_db()` call removed from app startup lifespan
- 352 tests passing post-19B.1

19B.2 details:
- `BLOB_TOKEN_TTL_SECONDS = 300`, `create_blob_token`, `verify_blob_token`
  added to `apex/backend/utils/auth.py`
- New endpoint: `POST /api/projects/{id}/documents/{doc_id}/signed-url`
  (Bearer-authed, returns short-lived signed URL)
- New `blob_router` (no global auth) hosts the file endpoint for
  iframe/img direct access
- Frontend `getDocumentFileUrl()` removed; `getDocumentSignedUrl()` added
- 11 new tests passing (token type discrimination, expiry, tampering,
  doc_id mismatch, JWT-as-blob rejection)
- 363 tests total post-19B.2

---

## New product surface proposals (Tucker idea, this session)

Reframed during ideation from "Contract Review" to "Contract Cost
Intelligence" to sidestep Document Crunch overlap. Pitch sentence:
*"Document Crunch tells your legal team what the contract says. APEX
tells your estimator what the contract costs."*

Two proposals banked:

1. **Insurance & Bond Requirements Analyzer** —
   `apex/docs/backlog/PROPOSAL-Insurance-Bond-Requirements-Analyzer.md`.
   Extraction-shaped feature. Surfaces required insurance types/amounts,
   bond requirements, OCIP/CCIP indicators. Slot: Sprint 22.5
   (post-pilot, after Override Capture).

2. **Contract Cost Intelligence Analyzer** —
   `apex/docs/backlog/PROPOSAL-Contract-Cost-Intelligence-Analyzer.md`.
   Extraction + quantification + recommendation. Surfaces liquidated
   damages, consequential damages, prevailing wage, retention,
   pay-if-paid, etc. with cost/risk impact and bid treatment per item.
   Slot: Sprint 22.6 (post-pilot).

Ordering decision (Option B): Sprint 22 stays Override Capture (M2 data
flywheel critical path). New proposals slot 22.5 and 22.6 immediately
after. Documented in:
`apex/docs/backlog/IDEAS-Tucker-2026-05-07-ordering.md`.

Stretch consideration: Insurance/Bond can ship as pre-pilot polish if
bandwidth permits (24-48 hour effort, pure extraction). Contract Cost
cannot — too much corpus and design work.

---

## Backlog added this session

- **HF-27** — Fail-loud on missing `LLM_PROVIDER` env var. Defaulting
  to ollama silently bit project 5 (two failed Agent 2 runs). Doctrine
  #4 silent-compensation pattern.
- **HF-28** — ❌ Cancelled. Concatenating WC text into `spec_content_text`
  would make FPs worse (keyword presence gate fires on presence, not
  absence). Resolution lives in 19E.5.
- **HF-29** — `size_sf` is a zombie column on `projects` table — added
  by retired runtime ALTER but never defined in `Project` SQLAlchemy
  model. All accesses go through `getattr(project, "size_sf", None)`
  defensive pattern. Either add to model or drop from DB. ~30 min task.
- **19E.4** — Calibration corpus expansion. Source 2-3 Division 03
  (concrete) bid packages for proper CGR rule validation. Reframed:
  corpus expansion would not change the schema mismatch finding. Worth
  doing for breadth of validation, but not the limiting factor.
- **19E.5** — Domain rule schema decision. War-room artifact ready.

---

## Sprint status across the board (post-session snapshot)

| Sprint | Status |
|---|---|
| 19A (Security/Auth) | HF-25 done May 6. Tenant isolation + JWT rotation pending — both need design conversation |
| 19B (Schema/Migration) | 19B.1 + 19B.2 shipped. Other runtime safety nets sweep pending |
| 19C (Upload/CI Hardening) | Not started. ~10 items |
| 19D (Determinism Hygiene) | Not started. Agent 5 Haiku doctrine violation pending |
| 19E (Domain Rules) | Substantially closed. 19E.5 decision pending |
| 19F (WC-SPEC-LINK hero) | Not started. Potentially absorbed by 19E.5 Direction B |
| 20 (Skills + RSMeans + Postgres) | Planned |
| 21 (MCP integration) | Planned |
| 22 (Override Capture) | Planned (M2 critical path) |
| 22.5 (Insurance/Bond) | Newly slotted this session |
| 22.6 (Contract Cost Intelligence) | Newly slotted this session |
| 23-24 (Managed Agents) | Planned |
| 25+ (Calibration, design, integrations) | Planned |

---

## Operational findings worth banking

1. **Diagnostic-first methodology paid off.** The May 6 handoff named
   two specific bugs (Agent 2 Div 31/32/33 miss; Agent 2B 0.020s
   no-op). Both were stale-state misreads. Specs 3 and 4 from the
   morning plan would have fixed non-bugs and introduced regressions.
   The `diagnose_agent2_coverage` CLI invalidated both hypotheses in
   one read-only run. **Lesson: build measurement tools before fix
   tools.**

2. **Read-the-evaluator-before-specifying paid off.** Last night's
   instinct on HF-28 (concatenate WC text into spec_content_text) was
   a 5-line fix in theory. Reading `domain_gap_rules.py` revealed the
   keyword presence gate semantics are inverted from the fix —
   concatenation would worsen FPs. **Lesson: read source before writing
   spec, especially when the spec sounds simple.**

3. **Stale state from failed pipeline runs is invisible.** Project 4's
   apparent Agent 2 Div 31/32/33 miss was actually two failed runs
   leaving zero sections. The successful Run 24 extracted everything
   correctly. The DB and AgentRunLog don't surface this distinction
   prominently enough. Backlog candidate: "Failed agent runs must
   produce visibly distinguishable state from sparse-but-successful
   runs."

4. **The cost-intelligence reframe matters strategically.** "Contract
   review" overlaps with Document Crunch (which the integrated roadmap
   explicitly says not to build). "Contract cost intelligence" is a
   distinct product surface that complements Document Crunch rather
   than competing. Same idea, different positioning, different roadmap
   fate.

---

## Where to pick up next session

Three options, in order of bandwidth ask:

1. **19E.5 directional decision.** Read the war-room doc, sit with the
   four directions, pick one. Name the ONE thing that would make the
   choice wrong. Define success criteria. Then write the implementation
   sprint specs. Estimated time: 30-60 minutes thinking + 30-60 minutes
   spec writing.

2. **Continue 19A/B/C/D hardening.** Several clean targets:
   - 19A tenant isolation on batch import endpoints (needs design)
   - 19A JWT token rotation (needs design)
   - 19C `admin_diagnostics.py` router removal (clean ~30 min target)
   - 19C chunk upload size enforcement (clean ~1 hr target)
   - 19D Agent 5 Haiku doctrine violation (needs design — Python should
     pick rates, not LLM)

3. **HF-29 cleanup.** `size_sf` zombie column reconciliation. ~30
   minutes. Low priority but a clean win if you want one.

---

## Files generated this session

In repo:
- `apex/backend/scripts/diagnose_agent2_coverage.py` (19E.0-DIAG)
- `apex/backend/tests/test_diagnose_agent2_coverage.py`
- `apex/docs/diagnostics/project_5_agent2_diag_20260507.md`
- `apex/docs/diagnostics/project_5_agent2_diag_20260507.json`
- `apex/docs/validation/19E-UPLOAD-evidence-2026-05-07.md`
- `apex/backend/alembic/versions/3a69638ff6bd_retire_runtime_alter_for_project_.py` (19B.1)
- `apex/docs/architecture/19E-finding-domain-rule-schema-mismatch.md`
- `apex/docs/architecture/19E_5-war-room-decision-framework-2026-05-07.md`
- `apex/docs/backlog/PROPOSAL-Insurance-Bond-Requirements-Analyzer.md`
- `apex/docs/backlog/PROPOSAL-Contract-Cost-Intelligence-Analyzer.md`
- `apex/docs/backlog/IDEAS-Tucker-2026-05-07-ordering.md`

Modified:
- `apex/backend/agents/agent_3_gap_analysis.py` (19E.3)
- `apex/backend/db/database.py` (19B.1)
- `apex/backend/main.py` (19B.1, 19B.2)
- `apex/backend/utils/auth.py` (19B.2)
- `apex/backend/routers/projects.py` (19B.2)
- `apex/frontend/src/api.js` (19B.2)
- `apex/frontend/src/components/tabs/DocumentsTab.jsx` (19B.2)
- `.gitignore`

Deleted:
- `apex/backend/services/crew_orchestrator.py` (HF-26)

Modified tests:
- `apex/backend/tests/test_agent_3_gap_analysis.py` (added 1 test)
- `apex/backend/tests/test_agent_3_timeout.py` (3 assertions widened)
- `apex/backend/tests/test_admin_endpoints.py` (added 2 tests)
- `apex/backend/tests/test_migrations.py` (created with 3 tests)
- `apex/backend/tests/test_auth_blob_token.py` (created with 11 tests)

Test count: 363 passed, 20 skipped (up from 314 pre-session).

---

## Session stats

- Duration: ~10 hours
- Commits to main: ~10
- Tests: 363 passed (+49 from baseline 314)
- Sprints touched: 5 (19B partial, 19E substantial, 22 new slots, plus banked items)
- Specs written by Claude (this project): 5 — 19E.3+HF-26, 19E.0-DIAG, 19E.UPLOAD, 19E.V, 19B.1, 19B.2
- Docs banked: 5 — finding, war room, 2 proposals, ordering
- Hypotheses falsified before code: 3 (May 6 Agent 2 miss, Agent 2B short-circuit, HF-28 concatenation fix)
- Days to Christman pilot (June): ~32

---

## End of handoff

_Generated May 7, 2026 evening. Strong session. Diagnostic-first
methodology validated. War-room artifact ready for next session's
directional decision on the domain rule schema mismatch._

