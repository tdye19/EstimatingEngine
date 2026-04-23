"""Admin diagnostics router — one-shot maintenance endpoints.

TEMPORARY — Sprint 18.3.3.1 validation maintenance window. Remove via
follow-up chore PR after summit validation (same teardown pattern used
by PR #82, which deleted the PR #79 / PR #80 diagnostics after their
one-shot Railway maintenance runs on 2026-04-22).

Each endpoint is independently gated by its own feature-flag env var so
the surface is invisible (returns 404) unless an operator has explicitly
turned it on for the duration of a maintenance window.
"""

from __future__ import annotations

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from apex.backend.db.database import get_db
from apex.backend.models.gap_finding import GapFinding
from apex.backend.models.project import Project
from apex.backend.models.user import User
from apex.backend.utils.auth import require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/diagnostics", tags=["admin-diagnostics"])

_SEED_GAP_FINDINGS_FLAG_ENV = "APEX_ENABLE_SEED_GAP_FINDINGS"
_FLAG_ON = "1"

_admin = require_role("admin")


def _require_seed_gap_findings_flag_enabled() -> None:
    """Hide the seed endpoint unless APEX_ENABLE_SEED_GAP_FINDINGS=1.

    Declared as the first dependency so it resolves before auth and the
    surface looks non-existent to any caller when the flag is off.
    Matches the PR #79 invisibility pattern.
    """
    if os.environ.get(_SEED_GAP_FINDINGS_FLAG_ENV, "") != _FLAG_ON:
        logger.info(
            "seed-test-gap-findings called with feature flag not enabled "
            f"({_SEED_GAP_FINDINGS_FLAG_ENV} != {_FLAG_ON}) — returning 404"
        )
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")


# ---------------------------------------------------------------------------
# Seed spec — Sprint 18.3.3.1 validation synthetic GapFindings.
# Exercises all 3 finding_type values + all 3 severities so Agent 6's
# populated-narrative branch has real data to aggregate on Railway.
#
# source: 4 rule / 1 llm — mirrors Agent 3.5's provenance split.
# match_tier: per-row to fit each rationale (csi_exact for division/exact
# codes, spec_section_fuzzy for prose/prefix matches, llm_semantic for
# the interpretive Tier-3 finding).
# ---------------------------------------------------------------------------

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


@router.post("/seed-test-gap-findings/{project_id}")
def seed_test_gap_findings(
    project_id: int,
    _flag: None = Depends(_require_seed_gap_findings_flag_enabled),
    _user: User = Depends(_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Seed 5 synthetic GapFinding rows so Agent 6 has real data to aggregate.

    TEMPORARY — Sprint 18.3.3.1 validation maintenance window. Remove via
    follow-up chore PR after summit validation.

    Delete-then-insert matches Agent 3.5's per-project regeneration contract
    (see apex/backend/models/gap_finding.py docstring) — two calls in a row
    leave exactly 5 rows, not 10.
    """
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project {project_id} not found",
        )

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
        f"seed-test-gap-findings: seeded {len(_SEED_ROWS)} rows for project {project_id} "
        f"(finding_types={finding_type_counts}, severities={severity_counts})"
    )

    return {
        "project_id": project_id,
        "seeded_count": len(_SEED_ROWS),
        "finding_types": finding_type_counts,
        "severities": severity_counts,
    }
