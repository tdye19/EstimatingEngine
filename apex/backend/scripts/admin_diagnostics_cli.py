"""Admin diagnostics CLI — ported from the Sprint 18.3.3.1 HTTP router.

Provides subcommands for seeding synthetic test/validation data without
exposing an HTTP endpoint.

Usage:
    python -m apex.backend.scripts.admin_diagnostics_cli seed-gap-findings --project-id N
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy.orm import Session

from apex.backend.db.database import SessionLocal
from apex.backend.models.gap_finding import GapFinding
from apex.backend.models.project import Project

logger = logging.getLogger(__name__)

_SEED_ROWS: list[dict] = [
    {
        "finding_type": "in_scope_not_estimated",
        "severity": "ERROR",
        "confidence": 0.95,
        "rationale": "Division 31 Earthwork present in work scope but no takeoff line items found",
        "source": "rule",
        "match_tier": "csi_exact",
        "spec_section_ref": "31 00 00",
    },
    {
        "finding_type": "in_scope_not_estimated",
        "severity": "WARNING",
        "confidence": 0.88,
        "rationale": "Trench safety and shoring referenced in scope; no matching line items",
        "source": "rule",
        "match_tier": "spec_section_fuzzy",
        "spec_section_ref": "31 54 00",
    },
    {
        "finding_type": "estimated_out_of_scope",
        "severity": "WARNING",
        "confidence": 0.82,
        "rationale": "Electrical conduit line item present; no matching WorkCategory in scope",
        "source": "rule",
        "match_tier": "csi_exact",
        "spec_section_ref": "26 05 00",
    },
    {
        "finding_type": "partial_coverage",
        "severity": "INFO",
        "confidence": 0.76,
        "rationale": (
            "Concrete formwork partially matches WC-05 but scope specifies "
            "architectural finish not reflected in takeoff"
        ),
        "source": "llm",
        "match_tier": "llm_semantic",
        "spec_section_ref": "03 30 00",
    },
    {
        "finding_type": "partial_coverage",
        "severity": "INFO",
        "confidence": 0.72,
        "rationale": "Rebar quantities approximated via division-prefix match, not exact section reference",
        "source": "rule",
        "match_tier": "spec_section_fuzzy",
        "spec_section_ref": "03 20 00",
    },
]


def seed_gap_findings(project_id: int, db: Session) -> dict:
    """Seed 5 synthetic GapFinding rows for the given project.

    Delete-then-insert: two calls leave exactly 5 rows, not 10.
    Returns summary dict with seeded_count, finding_types, severities.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    db.query(GapFinding).filter(GapFinding.project_id == project_id).delete(
        synchronize_session=False
    )

    finding_type_counts: dict[str, int] = {}
    severity_counts: dict[str, int] = {}
    for row in _SEED_ROWS:
        db.add(
            GapFinding(
                project_id=project_id,
                finding_type=row["finding_type"],
                severity=row["severity"],
                confidence=row["confidence"],
                rationale=row["rationale"],
                source=row["source"],
                match_tier=row["match_tier"],
                spec_section_ref=row["spec_section_ref"],
            )
        )
        finding_type_counts[row["finding_type"]] = finding_type_counts.get(row["finding_type"], 0) + 1
        severity_counts[row["severity"]] = severity_counts.get(row["severity"], 0) + 1

    db.commit()
    logger.info(
        "seed-gap-findings: seeded %d rows for project %d (finding_types=%s, severities=%s)",
        len(_SEED_ROWS),
        project_id,
        finding_type_counts,
        severity_counts,
    )
    return {
        "project_id": project_id,
        "seeded_count": len(_SEED_ROWS),
        "finding_types": finding_type_counts,
        "severities": severity_counts,
    }


def _cmd_seed_gap_findings(args: argparse.Namespace) -> None:
    db = SessionLocal()
    try:
        result = seed_gap_findings(args.project_id, db)
    finally:
        db.close()
    print(
        f"Seeded {result['seeded_count']} GapFindings for project {result['project_id']}. "
        f"finding_types={result['finding_types']} severities={result['severities']}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m apex.backend.scripts.admin_diagnostics_cli",
        description="Admin diagnostics CLI for synthetic data seeding.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_seed = sub.add_parser(
        "seed-gap-findings",
        help="Seed 5 synthetic GapFinding rows for a project (idempotent).",
    )
    p_seed.add_argument("--project-id", type=int, required=True, help="Target project ID")
    p_seed.set_defaults(func=_cmd_seed_gap_findings)

    return parser


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
