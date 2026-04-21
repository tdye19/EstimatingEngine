# Agent 4 — Rate Attachment Path Discovery (DIAG-1)

Date: 2026-04-21
Branch/HEAD: `main` (post Sprint 18.2 lock)
Scope: Determine the actual mechanism by which Agent 4 attaches Productivity Brain rates to estimate line items, and whether CSI backfill is on the demo critical path.

Method: Read-only code trace of `apex/backend/services/rate_engine/matcher.py`, `apex/backend/agents/agent_4_takeoff.py`, and all PB consumers. No code changes, no migrations, no new endpoints.

---

## 1. Matcher entry point(s)

All rate attachment funnels through a single class:

**`RateMatchingEngine`** — `apex/backend/services/rate_engine/matcher.py:34`

Public surface (the only methods Agent 4 calls):

| Signature | File:line |
|---|---|
| `RateMatchingEngine.__init__(self, db: Session)` | `matcher.py:37` |
| `match_all(self, items: list[TakeoffLineItem]) -> list[RateRecommendation]` | `matcher.py:178` |
| `compute_optimism_score(self, recommendations) -> float \| None` | `matcher.py:248` |
| `flags_summary(recommendations) -> dict` | `matcher.py:260` (staticmethod) |

Construction side-effect: `__init__` eagerly calls `_load_pb_summary()` (`matcher.py:39`) and caches the full PB summary in memory. Per-item matching (`_find_best_match`, `matcher.py:129`) is run in pure Python against that cache — **there is exactly one SQL touch of `pb_line_items` at engine construction**, plus one follow-up query per distinct `(activity, unit)` group to collect project names.

### Queries issued against `PBLineItem`

**Query A — load summary (`matcher.py:49-72`)**

```python
self.db.query(
    PBLineItem.activity,
    PBLineItem.unit,
    PBLineItem.crew_trade,
    PBLineItem.csi_code,                # ← included in SELECT list
    func.avg(PBLineItem.production_rate).label("avg_rate"),
    func.min(PBLineItem.production_rate).label("min_rate"),
    func.max(PBLineItem.production_rate).label("max_rate"),
    func.count(PBLineItem.id).label("sample_count"),
    func.avg(PBLineItem.production_rate * PBLineItem.production_rate).label("avg_sq"),
    func.avg(PBLineItem.labor_cost_per_unit).label("avg_labor_cost"),
    func.avg(PBLineItem.material_cost_per_unit).label("avg_mat_cost"),
)
.filter(
    PBLineItem.production_rate.isnot(None),
)
.group_by(
    PBLineItem.activity,
    PBLineItem.unit,
)
```

Columns read for matching: `activity`, `unit`, `crew_trade`, `csi_code`. The `csi_code` value returned per group is *non-aggregated under a group-by that does not include it* — SQLite's loose grouping returns an arbitrary row's value (effectively the first); PostgreSQL would reject this statement as-is. Today this only works because the production DB is SQLite (`apex/backend/apex.db`).

**Query B — distinct source projects per (activity, unit) (`matcher.py:82-91`)**

```python
self.db.query(func.distinct(PBLineItem.source_project))
    .filter(
        PBLineItem.activity == r.activity,
        PBLineItem.unit == r.unit,
        PBLineItem.production_rate.isnot(None),
        PBLineItem.source_project.isnot(None),
    )
```

Runs once per group. Reads `source_project`. Not used for matching — only for populating `matching_projects` in the recommendation.

No other SQL is issued against `PBLineItem` from the rate engine.

---

## 2. Match strategy

**Verdict: `activity_fuzzy` (effectively). The CSI fast-path is declared but never fires in production.**

`_find_best_match` (`matcher.py:129-174`) declares two strategies in priority order.

### Strategy 1 — CSI exact match (`matcher.py:138-149`)

```python
if item.csi_code:
    csi_matches = [s for s in self._pb_summary
                   if s["csi_code"] and s["csi_code"] == item.csi_code]
    if len(csi_matches) == 1:
        return csi_matches[0]
    if len(csi_matches) > 1:
        # tiebreak by fuzzy score on activity
        ...
```

For this branch to produce a match, **both sides must be non-null**:
1. `item.csi_code` (on the `TakeoffLineItem` coming out of `takeoff_parser`)
2. `s["csi_code"]` (on the PB summary row)

DATA-1.0 (`PB-SCHEMA-DISCOVERY.md` §6) established that **`PBLineItem.csi_code` is 100% NULL in the loaded PB project** — none of `parse_26col`, `parse_21col`, or `parse_averaged_rates` writes that column. Therefore the list comprehension filter `s["csi_code"] and s["csi_code"] == item.csi_code` is false for every `s`, and `csi_matches` is always `[]`. Strategy 1 is dead on arrival regardless of what the takeoff parser produces.

### Strategy 2 — fuzzy activity match (`matcher.py:151-174`)

```python
norm_item = self._normalize(item.activity)
for s in self._pb_summary:
    score = self._fuzzy_score(norm_item, self._normalize(s["activity"]))
    if score < 0.6:
        continue
    if item.unit and s["unit"] and item.unit.lower().strip() == s["unit"].lower().strip():
        score += 0.1      # unit boost
    if item.crew and s["crew_trade"] and item.crew.lower().strip() == s["crew_trade"].lower().strip():
        score += 0.05     # crew boost
    candidates.append((score, s))
```

- Normalizer: lowercase, strip, `_`/`-` → space, collapse spaces (`matcher.py:115-120`).
- Scorer: stdlib `difflib.SequenceMatcher.ratio()` (`matcher.py:122-125`) — **not** `rapidfuzz`, not Levenshtein, not RapidFuzz/Jaro. Plain `SequenceMatcher`.
- Threshold: `score >= 0.6` before unit/crew boosts.
- Tiebreaker: highest boosted score wins. `(activity, unit)` composite effectively becomes the join key.

This is the path that runs for 100% of items in production today.

---

## 3. Dead code paths

### `csi_code` branch in `_find_best_match`

`matcher.py:138-149` is live code that never fires. Not a code bug — the branch is sound; it just presupposes PB ingestion populates a column that no parser currently populates. `PB-SCHEMA-DISCOVERY.md:235` already flagged this.

### `csi_code` in the GROUP BY SELECT list

`matcher.py:54` pulls `PBLineItem.csi_code` into the grouped query despite grouping only on `(activity, unit)`. The resulting column is carried into `summaries[].csi_code` at `matcher.py:99`. Only `_find_best_match`'s dead branch reads it. Cost: one column on every row of the in-memory summary. Risk: if the DB ever migrates to Postgres, this query fails.

### `ProductivityBrainService.match_activity` (not Agent 4's path)

`apex/backend/services/library/productivity_brain/service.py:223-278` is a **second, duplicate** matching implementation — same CSI-exact → fuzzy-description → unit-tiebreaker pattern. It is wired into the HTTP router (`apex/backend/routers/library/productivity_brain.py:153` → `GET /api/library/productivity-brain/match`) for ad-hoc UI lookups. **Agent 4 does not call it.** It is *not* a fallback; it is a parallel code path for a different consumer (manual UI query). Same CSI-is-null problem applies.

---

## 4. Agent 4 consumer behavior

Call site: **`apex/backend/agents/agent_4_takeoff.py:98`**

```python
# agent_4_takeoff.py:98-101
engine = RateMatchingEngine(db)
recommendations = engine.match_all(items)
optimism = engine.compute_optimism_score(recommendations)
flags = engine.flags_summary(recommendations)
```

### Inputs passed in

`items: list[TakeoffLineItem]` produced by `parse_takeoff(doc.file_path)` on whatever takeoff document was found for the project (`agent_4_takeoff.py:79`). `TakeoffLineItem` has a `csi_code: str | None` field (`pipeline_contracts.py:175`); the takeoff parser *does* populate it when the source .xlsx has a "CSI" / "CSI Code" column (`services/takeoff_parser/parser.py:202, 225-226, 288-289, 346, 652`). So the takeoff side can carry a CSI code — but it never finds a partner on the PB side, so it doesn't matter.

### Response handling (`agent_4_takeoff.py:103-142`)

- `items_matched = sum(1 for r in recommendations if r.flag not in ("NO_DATA",))` — **any flag other than NO_DATA counts as matched**: OK, REVIEW, UPDATE, and NEEDS_RATE all count.
- `items_unmatched = sum(1 for r in recommendations if r.flag == "NO_DATA")`.
- Log emitted: `"Agent 4: X matched, Y unmatched, optimism=Z%"` (`agent_4_takeoff.py:106-111`). No per-item or aggregate log of *which strategy fired* — the matcher doesn't record that signal anywhere.
- TakeoffItemV2 rows for the project are **deleted and re-inserted wholesale** (`agent_4_takeoff.py:114-141`) — clean slate per run.
- Low-confidence and empty-match rows are still persisted, just with `flag="NO_DATA"` and `sample_count=0` (matcher.py:230-244). Nothing is filtered out or retried.

No fallback to an alternate matcher, no re-query, no graceful degradation if the PB DB is empty — `_load_pb_summary()` returning `[]` just means every item gets `NO_DATA`.

---

## 5. Fallback paths — other rate attachment sites

Exhaustive search (`Grep PBLineItem|rate_engine|RateMatchingEngine` across `apex/backend`):

| File | What it does | Is it a rate-attachment path? |
|---|---|---|
| `services/rate_engine/matcher.py` | The engine. | **Yes — the only one.** |
| `agents/agent_4_takeoff.py:36,98` | Imports and invokes the engine. | Consumer, not a fallback. |
| `services/library/productivity_brain/service.py:240,267-276` | `match_activity()` — duplicate CSI → fuzzy algorithm, exposed via `/api/library/productivity-brain/match`. | Separate HTTP endpoint for UI/manual use. Not called by the pipeline. |
| `agents/agent_6_assembly.py:402-403` | `db.query(func.count(PBLineItem.id))` — reads PB **count** for context. | Not a matcher; statistics only. |
| `services/library/field_actuals/service.py:180` | Comment says "same approach as rate_engine" for actuals. | Different domain (field actuals ≠ estimator rates). Not a fallback. |
| `services/library/productivity_brain/__init__.py` | Re-export. | n/a |
| `models/__init__.py` | Re-export. | n/a |
| `alembic/env.py` | Alembic autogenerate. | n/a |

**Conclusion: Agent 4 has no fallback.** `RateMatchingEngine` is the sole rate-attachment mechanism in the pipeline. If it misses, the item gets `NO_DATA` and ships that way.

---

## 6. Sample hit rate from real run

**Requires new diagnostic endpoint (or direct DB access) — stopped here per the "do not add endpoints" constraint.**

What is and isn't reachable today:

- `GET /api/projects/{id}/agent-run-logs` (`routers/agent_run_logs.py`) *does* return `output_data`, and Agent 4's output_data is the full `Agent4Output` contract — so `items_matched`, `items_unmatched`, `flags_summary`, `overall_optimism_score`, and the per-item `recommendations[]` list (with `flag`, `confidence`, `sample_count`) are all retrievable per run. **Overall hit rate is therefore calculable from this endpoint right now**, given (a) a project ID that has run Agent 4, and (b) a bearer token against the Railway host. Neither was provided in this task's scope.
- **What the logs do _not_ surface: which matching strategy fired per item.** The engine never records that signal — there is no `matcher_strategy` field on `RateRecommendation`, no log line, no counter in `flags_summary`. Given the analysis in §2 we can state with confidence that Strategy 1 fires on 0% of items today (because PB-side `csi_code` is 100% NULL), but confirming this from the logs is not possible without adding instrumentation.

To get per-strategy breakdowns we would need one of:
1. A small diagnostic endpoint (e.g. `GET /api/admin/projects/{id}/agent-4-match-diag`) that re-runs the matcher with a flag set and counts CSI-hits vs fuzzy-hits — ~30 LOC.
2. Instrumentation added to `_find_best_match` to stamp the strategy onto each returned summary dict — trivial patch, persists via TakeoffItemV2 if we add a column (bigger change).
3. Direct Railway DB read via `railway connect` — executed by the user, not Claude.

Recommendation for whoever picks this up: option 1 is the cheapest read-only confirmation and mirrors the pattern DATA-1.0 proposed for `GET /api/admin/db/pb-sample`.

---

## 7. Recommendation: is CSI backfill on the demo critical path?

**Verdict: NO.**

The CSI fast-path in `_find_best_match` requires a non-null CSI code on **both** sides of the match — PB and takeoff. DATA-1.0 established that the PB side is 100% NULL and that no current parser writes it; the takeoff side is populated only when the uploaded .xlsx happens to carry a "CSI" column, which is not guaranteed for WinEst exports. Backfilling just the PB side buys nothing on its own — the fuzzy path still does all the work for any takeoff that lacks a CSI column, and for the takeoffs that *do* carry one, we'd also need a mapping source-of-truth on the PB ingestion side (WBS→CSI? a manual crosswalk?) before a backfill has anything to write. Meanwhile, the fuzzy path via `SequenceMatcher` + `(activity, unit)` composite + crew tiebreaker is the live production path and, by construction of this codebase, always has been. The higher-leverage pre-demo investment is to measure fuzzy hit rate on the one loaded PB project using the existing `agent-run-logs` endpoint (or the small diag endpoint in §6) — if hit rate is acceptable, ship as-is; if it's poor, improve the normalizer or add an explicit activity crosswalk before building CSI infrastructure that still wouldn't fire until the takeoff side is fixed too.

One paragraph summary for the sprint doc: **CSI backfill is polish, not critical path. Ship the demo on the fuzzy path it has always used; measure the hit rate; only invest in CSI once we have a PB-side source-of-truth _and_ confirmation that uploaded takeoffs reliably carry CSI codes.**
