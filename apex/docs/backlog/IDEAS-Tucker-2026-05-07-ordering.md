# Tucker Ideas 2026-05-07 — Ordering vs Existing Backlog

**Date:** 2026-05-07
**Context:** During the Sprint 19E.5 war-room session, Tucker raised two
new product surface proposals (Insurance & Bond Requirements Analyzer,
Contract Cost Intelligence Analyzer). This document explains where they
slot in the existing roadmap.

**Decision: Option B** — Sprint 22 stays Override Capture (critical for
M2 data flywheel). New proposals slot as 22.5 and 22.6 immediately
after Override Capture lands.

---

## Proposed slot summary

| Sprint | Item | Status |
|---|---|---|
| 19A/B/C/D | Hardening (security, schema, upload, determinism) | In progress |
| 19E.5 | Domain rule schema decision (war-room) | Open |
| 19F | WC-SPEC-LINK hero feature | Planned |
| 20 | Skills + RSMeans + Postgres | Planned |
| 21 | MCP integration | Planned |
| 22 | Override Capture | Planned (critical path for M2) |
| 22.5 | Insurance & Bond Requirements Analyzer | **NEW — Tucker 2026-05-07** |
| 22.6 | Contract Cost Intelligence Analyzer | **NEW — Tucker 2026-05-07** |
| 23–24 | Managed Agents migration | Planned |
| 25 | Design + integrations | Planned |
| 26+ | Calibration | Planned |

---

## Ordering rationale

### Why post-Override-Capture (Sprint 22.5+)

Override Capture is the keystone for the M2 data flywheel target
(September 2026). Every bid run with override capture turned on
produces calibration data that feeds every other APEX surface — gap
analysis, rate intelligence, and (eventually) contract cost
recommendations. Pushing Override Capture later to make room for new
features starves the data flywheel and weakens the M2 narrative.

The two new proposals are valuable but not on the critical path to M2.
They slot after Override Capture, so the data flywheel keeps building
while new product surface gets added.

### Why post-pilot (Sprint 22+)

The Christman pilot in June validates the existing APEX surfaces (gap
analysis, rate intelligence, takeoff matching, Intelligence Report).
Adding new product surface pre-pilot risks two failure modes:

1. **Pilot dilution.** Christman estimators evaluating APEX during pilot
   should be evaluating *what's polished*, not what's half-built.
   Insurance/Bond and Contract Cost Intelligence are net-new analyzers
   that need their own design, validation, and corpus calibration. Pilot
   is the wrong venue for "is this feature done?"
2. **Bandwidth squeeze.** Pre-pilot calendar (May 12 – June 6 per the
   integrated roadmap) is already committed to Sprint 19 hardening +
   pilot polish. Squeezing two new features in costs depth on every
   item.

### Why 22.5 (Insurance/Bond) before 22.6 (Contract Cost)

Three reasons:

1. **Implementation simplicity.** Insurance/Bond is extraction-shaped
   work. Contract Cost is extraction PLUS quantification PLUS
   recommendation logic. Insurance/Bond ships in 1 sprint; Contract
   Cost needs 2–3.
2. **Corpus availability.** Insurance/Bond requirements appear in every
   bid in standardized form. Contract Cost calibration requires bids
   PLUS applied markups, which is a deeper data ask from Christman.
3. **Risk profile.** Insurance/Bond surfaces requirements (low risk of
   being wrong — the requirement is or isn't there). Contract Cost
   surfaces recommendations (higher risk of being wrong — the
   recommendation must align with how Christman actually prices similar
   risks). Better to ship the lower-risk feature first and build
   estimator trust before the higher-risk one.

### What could change the order

- **Pilot signal that contract risk pricing is the burning need at
  Christman.** If estimators ask "where's the contract risk analysis?"
  during pilot week 1, prioritize 22.6 over 22.5.
- **Christman risk officer joining the pilot conversation.** That user
  has stronger interest in 22.5 (insurance/bond requirements) than
  estimators do. If risk officer engagement happens, 22.5 may move up
  to be a pre-pilot polish item.
- **A faster path to 22.6 via the calibration corpus appearing.** If
  Christman provides 10+ past bids with applied risk markups in the
  pilot's first weeks, the long-pole dependency on 22.6 disappears
  and it becomes just-as-easy as 22.5.
- **Override Capture lands ahead of schedule.** If Sprint 22 finishes
  early, 22.5 immediately backfills.

### What would make this ordering wrong

- **If the pilot fails or is delayed.** Without pilot validation, all
  post-pilot scheduling is provisional.
- **If a competitor ships construction-estimating-grade contract cost
  intelligence first.** Document Crunch is the competitor to watch
  here. If they expand into bid-phase cost intelligence (rather than
  staying in execution-phase legal review), 22.6 becomes urgent and
  pre-pilot work becomes worth the squeeze.
- **If the 19E.5 decision picks Direction B** (full rule schema
  restructure). That consumes 2–3 sprints of bandwidth and pushes 22.x
  by a month. Other directions (A, C, D) leave 22.x timing intact.

---

## Stretch consideration — Insurance/Bond as pilot polish

If pilot prep finishes early and Tucker has 1 weekend of buffer,
**Insurance/Bond extraction can ship as a pre-pilot polish item.**
Justification:

- 24–48 hour effort, fits a weekend
- Pure extraction work — low risk of shipping broken
- Adds visible product surface to the pilot ("APEX also reads your
  insurance requirements")
- Independent of all other pre-pilot work

This is NOT recommended as a planned pre-pilot deliverable. It's a
"bonus shot" if pilot prep finishes early. If pilot prep runs hot
(typical), Insurance/Bond stays in 22.5 as planned.

Contract Cost Intelligence does NOT have this stretch option — too much
design and corpus work to compress safely.

---

## Cross-references

- Full proposal: `apex/docs/backlog/PROPOSAL-Insurance-Bond-Requirements-Analyzer.md`
- Full proposal: `apex/docs/backlog/PROPOSAL-Contract-Cost-Intelligence-Analyzer.md`
- Integrated roadmap: `APEX-Integrated-Roadmap-2026-05-05.md`
- Sprint 19E.5 war room: `apex/docs/architecture/19E_5-war-room-decision-framework-2026-05-07.md`
