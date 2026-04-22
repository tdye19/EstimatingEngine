# Schema drift audit — 2026-04-22

## Trigger

Railway production deploy of `POST /api/admin/diagnostics/run-orphan-cleanup`
(flag-gated dry-run + real-run cleanup endpoint) fails with:

```
OperationalError: no such column: bid_outcomes.estimate_run_id
```

The error occurs while SQLAlchemy cascades the delete of soft-deleted project
`id=4`. Zero rows get deleted; the transaction is rolled back.

Railway DB state (soft-deleted project IDs 4–14, ~10,906 orphan rows across 11
tables) is therefore stuck until the cleanup path stops issuing a `SELECT` that
references `bid_outcomes.estimate_run_id`.

## Why the cascade triggers that SELECT

`apex/backend/models/project.py:77` declares:

```python
bid_outcomes = relationship(
    "BidOutcome", back_populates="project", cascade="all, delete-orphan"
)
```

`apex/backend/scripts/cleanup_orphan_projects.py:120` iterates soft-deleted
projects and calls `db.delete(proj)`. The `delete-orphan` cascade forces
SQLAlchemy to **load** every `BidOutcome` row for the parent before removing
it, and the default load emits `SELECT bid_outcomes.id, bid_outcomes.project_id,
bid_outcomes.estimate_run_id, …` — which is what blows up on Railway.

## What `decision_models.py` declares for every `estimate_run_id` table

Every table that holds an `estimate_run_id` FK is listed below with the model's
column declaration (file: `apex/backend/models/decision_models.py`).

| Table                      | Column (per model)                                             | Line |
|----------------------------|----------------------------------------------------------------|------|
| `scope_items`              | `Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)` | 232 |
| `quantity_items`           | `Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)` | 274 |
| `benchmark_results`        | `Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)` | 298 |
| `decision_estimate_lines`  | `Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)` | 329 |
| `cost_breakdown_buckets`   | `Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)` | 398 |
| `decision_risk_items`      | `Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)` | 430 |
| `escalation_inputs`        | `Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)` | 466 |
| `schedule_scenarios`       | `Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)` | 487 |
| `estimator_overrides`      | `Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)` | 509 |
| `bid_outcomes`             | `Column(String(36), ForeignKey("estimate_runs.id"), nullable=True)`  | 535 |

`bid_outcomes.estimate_run_id` is the **only** one of these that the ORM
permits to be NULL. All others are `nullable=False`, so a Railway row in any of
those tables could not exist without the column being present — i.e. if those
tables hold any rows on Railway, their `estimate_run_id` column is present by
construction. `bid_outcomes` is the single table for which a missing column is
consistent with the observed error.

## What migration `2e5ae275617d_decision_system_tables.py` declares

Revision `2e5ae275617d` (`Revises: a8c0d2e4f6b7`) creates `bid_outcomes` — and
**includes** `estimate_run_id` — at lines 206–227:

```python
if not _table_exists("bid_outcomes"):
    op.create_table(
        "bid_outcomes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("estimate_run_id", sa.String(length=36), nullable=True),
        sa.Column("outcome", sa.String(length=20), nullable=True),
        sa.Column("final_bid_submitted", sa.Float(), nullable=True),
        sa.Column("winning_bid_value", sa.Float(), nullable=True),
        sa.Column("delta_to_winner", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["estimate_run_id"], ["estimate_runs.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
```

**Key property:** the entire CREATE is wrapped in `if not _table_exists(…)`.
Once `bid_outcomes` exists, the migration is a no-op — it will **not**
retroactively add any columns.

No subsequent migration adds `estimate_run_id` to `bid_outcomes` via
`op.add_column` (grep confirms only `2e5ae275617d` and `05f8b317e2cd` mention
the table). The FK-index migration `05f8b317e2cd` at line 54 assumes the
column is present:

```python
("ix_bid_outcomes_estimate_run_id", "bid_outcomes", ["estimate_run_id"]),
```

but it swallows exceptions (`try: op.create_index … except Exception: pass`),
so a missing column silently fails to produce an index on Railway without
crashing the deploy.

## Hypothesis: why Railway's `bid_outcomes` lacks `estimate_run_id`

The original BidOutcome model (commit `982ea4a` — "feat: decision system
domain models") declared `bid_outcomes` **without** `estimate_run_id`:

```python
class BidOutcome(Base):
    __tablename__ = "bid_outcomes"
    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    outcome = Column(String(20), nullable=True)
    # … no estimate_run_id …
```

At that commit, no migration existed for the decision-system tables. The
migration `2e5ae275617d` (with `estimate_run_id` present) was only added later
in commit `d8367ca`, and rewritten to be idempotent in commit `5426cdf`
("fixes to railway and decision system tables").

The most likely sequence on Railway:

1. An early deploy — at or shortly after `982ea4a` but before `d8367ca` —
   created `bid_outcomes` with the old, estimate_run_id-free shape. The most
   plausible path is a seed or dev script that called
   `Base.metadata.create_all(engine)` (still present in `apex/backend/db/seed.py:44`
   and `apex/backend/db/seed_decision_data.py:422`), or a hand-run of the
   pre-rewrite migration.
2. When `d8367ca` / `5426cdf` later landed on Railway, `alembic upgrade head`
   ran `2e5ae275617d`, saw that `bid_outcomes` already existed, and skipped
   the whole `op.create_table` block.
3. No `ALTER TABLE bid_outcomes ADD COLUMN estimate_run_id …` migration was
   ever authored, so the column never arrived.

Supporting evidence that Railway's alembic head is otherwise current:

- Railway's start command is `alembic upgrade head && gunicorn …` — if alembic
  were failing, the container would not serve any requests, and the health
  check would fail.
- All other `estimate_run_id` tables (above) have that column as `NOT NULL`.
  If Railway had drifted more broadly, we would see similar column-missing
  errors on those tables during the decision-system pipeline — instead we see
  a single failure on the only nullable-FK variant.

**Short version:** not a full migration lag. It is one table, one column,
caused by an idempotency guard that once rescued a dev-state DB but is now
masking a needed backfill.

## Other potential drift (report only — no action here)

- `apex/backend/db/seed.py:44`, `apex/backend/db/seed_decision_data.py:422`,
  `apex/backend/db/load_remaining_projects.py:76,140` all call
  `Base.metadata.create_all(bind=engine)`. These paths will create any
  currently-model-defined table that does not yet exist using the model's
  current shape, on any environment that runs them. Long-term risk: they can
  silently anchor a schema version that alembic then refuses to touch.
- `apex/backend/db/database.py:ensure_project_context_columns` already uses
  per-column `ALTER TABLE` add-with-try/except to retrofit the `projects`
  table. There is no analogue for `bid_outcomes` or any decision-system
  table.

## Recommendation

Two viable patches (scope is "unblock cleanup," not "reconcile alembic"):

**(a) One-shot `repair-bid-outcomes-column` admin endpoint**
Flag-gated `POST /api/admin/diagnostics/repair-bid-outcomes-column`, admin-only,
runs idempotent raw SQL: inspect `bid_outcomes.columns`; if
`estimate_run_id` absent, `ALTER TABLE bid_outcomes ADD COLUMN estimate_run_id
TEXT REFERENCES estimate_runs(id)`. Fixes the root cause (column missing);
after a single call Railway's schema matches the model and the existing
cleanup endpoint works with no further change. Risk: adds an admin write
surface that mutates schema — needs the `APEX_ENABLE_SCHEMA_REPAIR=1` flag
plus the existing admin auth to avoid leaving a dangerous endpoint exposed.

**(b) Bypass the ORM cascade in `cleanup_orphan_projects.py`**
Before invoking `db.delete(proj)` for each soft-deleted project, issue a raw
`DELETE FROM bid_outcomes WHERE project_id IN (:ids)` to drain the broken
relationship. SQLAlchemy then has no rows to load during cascade and the
OperationalError cannot fire. Fixes the symptom, not the root cause —
`bid_outcomes.estimate_run_id` is still missing on Railway, and any future
code path that reads the column will break the same way. Lowest blast radius
for the cleanup path specifically.

**Recommended: (a).** One column, one idempotent DDL, and the problem is
actually gone instead of papered over. The cleanup script is already careful
(dry-run by default, wraps everything in one transaction) — once the schema
is aligned, no cleanup-code change is needed. The pre-summit constraint
argues for the fix that doesn't leave a landmine.

Path (b) is preferable only if we consider schema-mutating admin endpoints an
unacceptable surface even behind a flag, or if we have evidence that other
decision-system tables also drifted (in which case both (a) and (b) are
insufficient and we should defer to post-summit).
