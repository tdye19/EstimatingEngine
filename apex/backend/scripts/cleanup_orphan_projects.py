"""One-time cleanup for legacy soft-deleted projects and their orphan children.

Runs in two modes controlled by the APEX_CONFIRM_ORPHAN_CLEANUP env var:

  unset / anything-not-YES   →  DRY RUN.  Reports what would be deleted,
                                writes nothing.  Safe.
  YES                         →  REAL RUN. db.delete() each soft-deleted
                                project inside a single transaction. If
                                anything raises, the whole transaction is
                                rolled back.

Usage:
    # Dry run (default)
    python -m apex.backend.scripts.cleanup_orphan_projects

    # Real run
    APEX_CONFIRM_ORPHAN_CLEANUP=YES python -m apex.backend.scripts.cleanup_orphan_projects

This is a one-shot cleanup for data that accumulated under the pre-fix
DELETE handler (which only flipped is_deleted=True and never removed
any row). Once this runs on Railway and the project count is confirmed
correct, the script can be kept in-repo for future audit or removed.

Cascade coverage: the ORM cascade declared on Project.* relationships
removes every child row SQLAlchemy knows about. For safety against any
orphan that isn't ORM-linked — whether because a relationship is
nullable (and therefore not on Project.* by design) or because a new
child table lands without being wired up — we also scan
information_schema for tables with a project_id FK and delete by raw
SQL after the ORM cascade. Any row this extra scan finds is by
definition an orphan not covered by the ORM cascade and reported as
'orphan_rows_cleared'.
"""

from __future__ import annotations

import os
import sys
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import bindparam, inspect, text
from sqlalchemy.orm import Session

from apex.backend.db.database import SessionLocal, engine
from apex.backend.models.project import Project

_CONFIRM_ENV = "APEX_CONFIRM_ORPHAN_CLEANUP"
_CONFIRM_VALUE = "YES"


@dataclass
class CleanupReport:
    dry_run: bool
    soft_deleted_project_ids: list[int] = field(default_factory=list)
    per_table_rowcounts_before: Counter = field(default_factory=Counter)
    orphan_rows_cleared: Counter = field(default_factory=Counter)
    projects_deleted: int = 0
    aborted_with: str | None = None

    def as_dict(self) -> dict:
        return {
            "dry_run": self.dry_run,
            "soft_deleted_project_ids": list(self.soft_deleted_project_ids),
            "projects_deleted": self.projects_deleted,
            "per_table_rowcounts_before": dict(self.per_table_rowcounts_before),
            "orphan_rows_cleared_via_raw_sql": dict(self.orphan_rows_cleared),
            "aborted_with": self.aborted_with,
        }


def _child_tables_referencing_projects(db: Session) -> list[tuple[str, str]]:
    """(table, fk_col) for every table with a FK to projects.id.
    Works on both SQLite and Postgres via dialect-agnostic Inspector."""
    inspector = inspect(db.get_bind())
    out: list[tuple[str, str]] = []
    for table_name in inspector.get_table_names():
        if table_name == "projects":
            continue
        for fk in inspector.get_foreign_keys(table_name):
            if fk.get("referred_table") == "projects" and "id" in (fk.get("referred_columns") or []):
                constrained = fk.get("constrained_columns") or []
                if constrained:
                    out.append((table_name, constrained[0]))
                break
    return sorted(out)


def _count_children(db: Session, project_ids: list[int], tables: list[tuple[str, str]]) -> Counter:
    counts: Counter = Counter()
    if not project_ids:
        return counts
    for tbl, col in tables:
        sql = text(f"SELECT COUNT(*) FROM {tbl} WHERE {col} IN :ids").bindparams(
            bindparam("ids", expanding=True)
        )
        n = db.execute(sql, {"ids": project_ids}).scalar() or 0
        if n:
            counts[tbl] = int(n)
    return counts


def run_cleanup(db: Session, dry_run: bool) -> CleanupReport:
    report = CleanupReport(dry_run=dry_run)

    soft_deleted = db.query(Project).filter(Project.is_deleted == True).all()  # noqa: E712
    report.soft_deleted_project_ids = [p.id for p in soft_deleted]
    if not soft_deleted:
        return report

    child_tables = _child_tables_referencing_projects(db)
    report.per_table_rowcounts_before = _count_children(
        db, report.soft_deleted_project_ids, child_tables
    )

    if dry_run:
        return report

    try:
        for proj in soft_deleted:
            db.delete(proj)  # fires ORM cascade across Project.* relationships
        db.flush()

        # Orphan sweep: any row whose project is now gone is by definition
        # not ORM-cascaded. Clean with raw SQL in the same transaction.
        for tbl, col in child_tables:
            deleted = db.execute(
                text(f"DELETE FROM {tbl} WHERE {col} IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"ids": report.soft_deleted_project_ids},
            )
            rc = getattr(deleted, "rowcount", 0) or 0
            if rc:
                report.orphan_rows_cleared[tbl] = int(rc)

        report.projects_deleted = len(soft_deleted)
        db.commit()
    except Exception as exc:
        db.rollback()
        report.aborted_with = f"{type(exc).__name__}: {exc}"
        report.projects_deleted = 0
        report.orphan_rows_cleared.clear()
    return report


def _confirm_flag_yes() -> bool:
    return os.environ.get(_CONFIRM_ENV, "").strip().upper() == _CONFIRM_VALUE


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI wrapper
    import json

    dry_run = not _confirm_flag_yes()
    # Use the app's SessionLocal so env-var-driven DATABASE_URL wiring
    # matches whatever backend the caller pointed us at.
    session = SessionLocal()
    try:
        report = run_cleanup(session, dry_run=dry_run)
    finally:
        session.close()

    mode_banner = "DRY RUN" if dry_run else "REAL RUN"
    print(f"=== orphan-project cleanup — {mode_banner} ===")
    print(f"engine: {engine.url!s}")
    if dry_run:
        print(
            f"(set {_CONFIRM_ENV}={_CONFIRM_VALUE} to actually delete. "
            "no rows written on this invocation.)"
        )
    print(json.dumps(report.as_dict(), indent=2, default=str))
    return 0 if report.aborted_with is None else 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main(sys.argv[1:]))
