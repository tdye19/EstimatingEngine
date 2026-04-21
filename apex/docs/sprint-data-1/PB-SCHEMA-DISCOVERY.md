# PB Schema Discovery — Sprint DATA-1.0

Date: 2026-04-21
Branch/HEAD: main @ `a324e9f970ac` (Sprint 18.2 lock)
Scope: Existing Productivity Brain (PB) surface area in APEX, in preparation for CityGate loader work.

---

## 1. Models Found

All PB models live under `apex/backend/services/library/productivity_brain/models.py` (re-exported through `apex/backend/models/__init__.py` lines 50, 81–82).

### `PBProject` — table `pb_projects`

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer | PK, autoincrement |
| `name` | String(255) | NOT NULL |
| `source_file` | String(500) | NOT NULL |
| `file_hash` | String(32) | NOT NULL, **UNIQUE** (MD5, idempotency key) |
| `format_type` | String(30) | nullable — one of `'26col_civil' \| '21col_estimate' \| 'averaged_rates'` |
| `project_count` | Integer | default=1 — number of sub-projects folded into this ingest (see §5) |
| `total_line_items` | Integer | default=0 |
| `ingested_at` | DateTime | server_default=now() |

Relationships: `line_items → PBLineItem` (cascade delete-orphan via `project_id` FK).

### `PBLineItem` — table `pb_line_items`

| Column | Type | Constraints |
|---|---|---|
| `id` | Integer | PK, autoincrement |
| `project_id` | Integer | FK → `pb_projects.id`, NOT NULL, indexed |
| `wbs_area` | String(255) | nullable |
| `activity` | String(500) | NOT NULL, indexed |
| `quantity` | Float | nullable |
| `unit` | String(50) | nullable |
| `crew_trade` | String(200) | nullable |
| `production_rate` | Float | nullable — unit/MH |
| `labor_hours` | Float | nullable |
| `labor_cost_per_unit` | Float | nullable |
| `material_cost_per_unit` | Float | nullable |
| `equipment_cost` | Float | nullable — per-unit despite the name (see §5) |
| `sub_cost` | Float | nullable — per-unit despite the name (see §5) |
| `total_cost` | Float | nullable — "grand total" unit price |
| `csi_code` | String(20) | nullable, indexed — **never written by current parsers** (see §5) |
| `source_project` | String(255) | nullable — sub-project tag, only set by averaged-rates parser |

Indexes:
- `ix_pb_line_items_project_id`
- `ix_pb_line_items_activity`
- `ix_pb_line_items_csi_code`
- `ix_pb_li_activity_unit` — composite (activity, unit) for Agent 4 match path

No unique constraints at row level — duplicate (project_id, activity, unit) rows are allowed; dedup is file-level via `pb_projects.file_hash`.

### Adjacent models (NOT part of PB — do not conflate)

- `ProductivityHistory` (`apex/backend/models/productivity_history.py`, table `productivity_history`) — legacy Sprint 7 rate table, used by `/api/productivity-library`.
- `ProductivityBenchmark` (`apex/backend/models/productivity_benchmark.py`, table `productivity_benchmarks`) — Sprint 10 aggregation over HistoricalLineItem, org-scoped. Different domain.

---

## 2. Services / Loaders Found

Package: `apex/backend/services/library/productivity_brain/`

### `parser.py` — format detection + Excel parsers

```python
compute_file_hash(filepath: str) -> str           # MD5 of file bytes
detect_format(filepath: str) -> str               # '26col_civil' | '21col_estimate' | 'averaged_rates' | 'unknown'
parse_26col(filepath: str) -> list[dict]          # CCI Civil Est Report (26 cols, header at row 4)
parse_21col(filepath: str) -> list[dict]          # CCI Estimate Report  (21 cols, header at row 4)
parse_averaged_rates(filepath: str) -> list[dict] # e.g. CityGate_Master_Productivity_Rates.xlsx — header at row 3
```

Format detection priority:
1. Cell A1 string-match on `"CCI Civil Est Report"` → 26col
2. Cell A1 string-match on `"CCI Estimate Report"` → 21col
3. Row-3 header fuzzy match on `"wbs area"` + `"avg prod"` → averaged
4. Column-count fallback (≥25 → 26col, ≥20 → 21col)

Column maps are hardcoded positional (`FORMAT_26_COLS`, `FORMAT_21_COLS`). Averaged-rates parser discovers columns by header text at row 3 and treats each column between `AVG Prod` and `Count` as a per-sub-project rate column — each non-null per-project value emits one `PBLineItem` with `source_project=<col header>`, plus an aggregate row with `source_project='_averaged'`.

### `service.py` — `ProductivityBrainService(db: Session)`

```python
ingest_file(filepath: str, filename: str) -> dict          # dedups by file_hash → 'ingested' | 'skipped' | 'error'
batch_ingest(filepaths: list[tuple[str, str]]) -> list[dict]
get_rates(activity=None, wbs=None, unit=None) -> list[dict]
compare_estimate(estimate_items: list[dict]) -> list[dict] # adds historical_avg, delta_pct, flag (OK|REVIEW|UPDATE|NO DATA)
get_stats() -> dict                                        # total_projects, total_line_items, total_activities, format_breakdown
get_projects() -> list[dict]
match_activity(csi_code=None, description=None, unit=None) -> dict | None   # Agent 4 entrypoint
```

**Idempotency**: single mechanism — `file_hash` UNIQUE on `pb_projects`. Re-uploading the same file returns `{"status": "skipped", "reason": "duplicate"}`. No row-level dedup.

**Validation**: essentially none.
- Activity text must be non-empty (rows with null description skipped).
- Numeric cells routed through `_safe_float` (strips `$`/`,`, returns `None` on failure).
- `'—' / '-- / '-'` treated as None by `_clean_dash` in averaged parser.
- No schema validation (Pydantic), no unit vocabulary check, no CSI validation, no quantity/rate sanity bounds.

**Math locality**: all averages, min/max, delta_pct in deterministic Python / SQL AVG — no LLM touches rates. Matches APEX rule "LLM never touches final dollar amounts."

### Consumers (already wired)

| Consumer | File | Usage |
|---|---|---|
| Agent 4 (rate engine) | `services/rate_engine/matcher.py` | Groups by `(activity, unit, crew_trade, csi_code)`, computes avg/min/max/std from `production_rate`, returns sample stats. Also scans `PBLineItem.source_project` for project diversity. |
| Agent 6 (assembly) | `agents/agent_6_assembly.py:401-403` | Reads totals for context. |
| Intelligence report | `routers/reports.py:77` | Reports `pb_projects_loaded` field. |

---

## 3. API Endpoints Found

Router: `apex/backend/routers/library/productivity_brain.py`
Mount: `app.include_router(productivity_brain_router.router)` in `main.py:171`
Prefix: `/api/library/productivity-brain`
Auth: `Depends(require_auth)` at router level — **all endpoints require a signed-in user**.

| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| POST | `/upload` | `multipart/form-data`: up to 50 `.xlsx` `files[]` | `APIResponse<list[{filename, status, project_id?, name?, format?, line_items?, error?}]>` | Saves to `UPLOAD_DIR/productivity_brain/`, invokes `ingest_file` per file. |
| GET | `/stats` | — | `APIResponse<{total_projects, total_line_items, total_activities, format_breakdown, last_ingested}>` | |
| GET | `/rates` | `?activity=&wbs=&unit=` | `APIResponse<list[{activity, unit, occurrences, project_count, avg_rate, min_rate, max_rate, spread, avg_labor_cost_per_unit, avg_material_cost_per_unit}]>` | `spread` computed in router (max − min). |
| POST | `/compare` | JSON: `list[{activity, rate/production_rate, unit?, csi_code?}]` | `APIResponse<list[{activity, estimate_rate, historical_avg, delta_pct, flag, sample_count, confidence}]>` | `confidence`: `high` ≥10, `medium` ≥5, `low` <5. `flag`: OK/REVIEW/UPDATE/NO DATA. |
| GET | `/projects` | — | `APIResponse<list[{id, name, source_file, format_type, project_count, total_line_items, ingested_at}]>` | |
| GET | `/match` | `?csi_code=&description=&unit=` | `APIResponse<{activity, unit, crew_trade, occurrences, project_count, avg/min/max_rate, avg_labor_cost_per_unit, avg_material_cost_per_unit} \| null>` | Used by Agent 4: exact CSI → fuzzy desc (ratio ≥0.6) → unit tiebreaker. |

Unrelated router — do not confuse: `apex/backend/routers/productivity.py` at `/api/productivity-library` reads `ProductivityHistory`, not PB.

---

## 4. Existing Migration

File: `apex/backend/alembic/versions/b3d5f7a9c1e2_pb_integrate_1_productivity_brain_tables.py`
Revision: **`b3d5f7a9c1e2`**
Down-revision: `a1b2c3d4e5f6` (sprint 12.4 shadow mode)
Created: 2026-04-01 ("PB-INTEGRATE-1")

### Confirmation it is in the current HEAD chain

HEAD per Sprint 18.2 lock: `a324e9f970ac`. Walking `down_revision` from HEAD:

```
a324e9f970ac (sprint18.2.1, HEAD)
 → 8ae8a8fdc4c6 (sprint18.1 WorkCategory)
 → 230fce14e46f (add_sub_bid_tables)
 → 05f8b317e2cd (add_missing_fk_indexes)
 → 2e5ae275617d (decision_system_tables)
 → a8c0d2e4f6b7 (sprint16 intelligence_report)
 → f7b9d1e3a5c6 (sprint15 field_actuals)
 → e6a8c2d4f0b3 (sprint14 takeoff_v2)
 → d5f7b9a1c3e4 (agent2_v2 spec_parameter_columns)
 → c4e6a8d0f2b1 (bi_ingest_1 bid_intelligence_table)
 → b3d5f7a9c1e2  ← PB tables
 → a1b2c3d4e5f6 (sprint12.4 shadow mode)
 → e4ae649389b5 → e5a2b7d3f1c8 → f2c9d4e7b3a1 → d4f7b1c9e2a5
 → c9f4a8d2e1b3 → 37e85ea73069 → ee412a823a92 (initial)
```

**Confirmed: `b3d5f7a9c1e2` is reachable from current HEAD.** No branching; single linear chain.

Schema created by the migration matches the models byte-for-byte. Indexes created: `ix_pb_line_items_project_id`, `ix_pb_line_items_activity`, `ix_pb_line_items_csi_code`, `ix_pb_li_activity_unit`. UNIQUE on `pb_projects.file_hash`.

---

## 5. Current Database State (Railway)

**Status: NOT YET PULLED.** This section documents what *can* be pulled and how.

### The 4/21 handoff constraint

`railway run python …` executes against the local Codespace SQLite (`apex/backend/apex.db`), not Railway's Postgres. The only way to read the Railway DB from this repo is via the deployed API itself.

### What existing Railway endpoints already expose

Two endpoints already cover most of the required counts and can be hit with a bearer token against the Railway host right now — no new code required:

| Quantity | Endpoint |
|---|---|
| Count of PB projects | `GET /api/library/productivity-brain/stats` → `total_projects` |
| Count of line items | same → `total_line_items` |
| Count of distinct activities (with non-null rate) | same → `total_activities` |
| Format breakdown | same → `format_breakdown` |
| Per-project rows (id, name, source_file, format_type, project_count, total_line_items, ingested_at) | `GET /api/library/productivity-brain/projects` |

These should reconcile to the "1 project / 243 items / 59 activities" figure quoted in the brief.

### What is NOT exposed and therefore blocks a full check

The spec asks for "5 sample rows from each PB table with representative data." No existing endpoint returns raw `pb_line_items` rows — `/rates` returns aggregates, `/match` returns a single best hit. Sampling requires either:

1. A minimal read-only diagnostic endpoint (e.g. `GET /api/admin/db/pb-sample` gated on `require_role("admin")`, returning `LIMIT 5` rows per table), or
2. A one-shot Railway `psql` / `railway connect` session run locally by the user.

Per the spec's "DO NOT write any new endpoints yet" clause, this has been left for the next step — see §7.

### Counts to verify once DB access is available

- `SELECT COUNT(*) FROM pb_projects;` (expect 1)
- `SELECT COUNT(*) FROM pb_line_items;` (expect 243)
- `SELECT COUNT(DISTINCT activity) FROM pb_line_items WHERE production_rate IS NOT NULL;` (expect 59)
- `SELECT * FROM pb_projects LIMIT 5;`
- `SELECT * FROM pb_line_items LIMIT 5;`
- `SELECT COUNT(*) FROM pb_line_items WHERE csi_code IS NOT NULL;` (**see §6 — likely 0**)
- `SELECT format_type, COUNT(*) FROM pb_projects GROUP BY format_type;`

---

## 6. Unknown Columns / Open Questions

### ⚠️ `csi_code` — declared, indexed, **never written**

`PBLineItem.csi_code` (String(20), indexed) is defined in the model and migration, **but none of the three parsers populate it**. Inspect the parser return dicts:

- `parse_26col` (`parser.py:134-149`) — keys: `wbs_area, activity, quantity, unit, crew_trade, production_rate, labor_hours, labor_cost_per_unit, material_cost_per_unit, equipment_cost, sub_cost, total_cost`. No `csi_code`.
- `parse_21col` (`parser.py:166-181`) — same keys, no `csi_code`.
- `parse_averaged_rates` (`parser.py:236-249`) — base dict has no `csi_code`.

Yet `ProductivityBrainService.match_activity` uses it as its **highest-priority match path**:

```python
# service.py:238-242
if csi_code:
    match = self._rates_for_filter(PBLineItem.csi_code == csi_code)
    if match:
        return match[0]
```

And `rate_engine/matcher.py:54` groups by it. For the existing 243 rows, `csi_code` is almost certainly 100% NULL, meaning the CSI fast-path never fires and every Agent 4 lookup falls through to fuzzy description match.

**Open question for CityGate loader:** do we populate `csi_code` on ingest (requires a source of truth — WBS-to-CSI map?), or is it intentionally deferred to a later enrichment pass?

### ⚠️ `source_project` — semantics are format-dependent

`source_project` is only populated by `parse_averaged_rates`. For the other two formats it is always NULL. In averaged files it carries either the per-sub-project column header, or the literal sentinel string `'_averaged'` for the aggregate row (`parser.py:257, 261`). Consumers must know to either filter out `_averaged` or keep it and ignore duplicates — `_count_projects` (`service.py:326-328`) explicitly discards `_averaged`. `rate_engine/matcher.py:83-88` reads it to count distinct sub-projects.

**Open question:** for the CityGate load, will we emit one row per sub-project + one `_averaged` aggregate row (current pattern), or flatten to per-sub-project only?

### ⚠️ `equipment_cost` and `sub_cost` — named like totals, populated like unit prices

Model names suggest totals, but the 26-col / 21-col parsers read them from the `equip_up` / `subs_up` columns — the **per-unit** rates, not the extended totals. The extended totals (`equip_total`, `subs_total`) are read by the parser's column map but **discarded** before the dict is built. Any downstream code assuming these are line-totals is wrong.

### ⚠️ `PBProject.project_count` — two different meanings in the codebase

- On the **model**: "for averaged files, number of sub-projects folded in; else 1" (set by `_count_projects` in `service.py:323-328`).
- In **aggregate queries** (`service.py:93, 118, 289, 313`): a computed label for `COUNT(DISTINCT project_id)` — i.e. how many PBProjects contributed rows to the grouped result.

Same name, different meanings. Easy to confuse when writing new queries.

### Minor

- `PBProject.format_type` is String(30) with no CHECK constraint; enforcement is code-side only. Enum values: `'26col_civil'`, `'21col_estimate'`, `'averaged_rates'`.
- `file_hash` is MD5 (32-char hex), not cryptographically sensitive — used purely for dedup.
- No soft-delete on either PB table. A bad ingest can only be removed via cascade delete on `PBProject`.
- No `organization_id` on either PB table — **PB is currently a global library, not org-scoped.** Diverges from Sprint 10 `ProductivityBenchmark`, which is org-scoped. If CityGate data must be isolated per org, this is a schema gap.

---

## 7. Recommended Next Step

Before writing the CityGate loader, (a) add a tiny admin-only `GET /api/admin/db/pb-sample` endpoint that runs `SELECT * … LIMIT 5` against both PB tables so we can close out §5 with real Railway data, and (b) decide whether CityGate data should populate `csi_code` at ingest — the current parsers leave it NULL and Agent 4's fast-path is therefore dead in production today. The bigger structural call is whether PB needs `organization_id` before loading a second customer's data; if yes, that's a migration that should precede the loader, not follow it.
