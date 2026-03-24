"""Agent 3: Scope Gap Analysis Agent.

Compares parsed spec scope against a master scope checklist.
"""

import logging
from sqlalchemy.orm import Session
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.gap_report import GapReport, GapReportItem
from apex.backend.utils.csi_masterformat import MASTER_SCOPE_CHECKLIST
from apex.backend.agents.pipeline_contracts import validate_agent_output
from apex.backend.agents.tools.gap_tools import (
    checklist_compare_tool,
    gap_scorer_tool,
    risk_tagger_tool,
)

logger = logging.getLogger("apex.agent.gap_analysis")


def run_gap_analysis_agent(db: Session, project_id: int) -> dict:
    """Run gap analysis comparing project specs against master checklist.

    Returns dict with gap counts and report details.
    """
    # Get all parsed spec sections
    sections = db.query(SpecSection).filter(
        SpecSection.project_id == project_id,
        SpecSection.is_deleted == False,  # noqa: E712
    ).all()

    parsed_sections = [
        {
            "division_number": s.division_number,
            "section_number": s.section_number,
            "title": s.title,
        }
        for s in sections
    ]

    # Determine which divisions are present in the project
    project_divisions = set(s.division_number for s in sections)

    # Build checklist for relevant divisions (plus always check core divisions)
    core_divisions = {"03", "05", "07", "08", "09"}
    check_divisions = project_divisions | core_divisions
    checklist = {div: items for div, items in MASTER_SCOPE_CHECKLIST.items() if div in check_divisions}

    # Run comparison
    gaps = checklist_compare_tool(parsed_sections, checklist)

    # Score and tag each gap
    scored_gaps = []
    for gap in gaps:
        tagged = risk_tagger_tool(gap)
        scored_gaps.append(tagged)

    # Get overall scores
    scores = gap_scorer_tool(scored_gaps)

    # Create gap report
    report = GapReport(
        project_id=project_id,
        overall_score=scores["overall_score"],
        total_gaps=scores["total_gaps"],
        critical_count=scores["critical_count"],
        moderate_count=scores["moderate_count"],
        watch_count=scores["watch_count"],
        summary=f"Analysis of {len(parsed_sections)} spec sections against {len(checklist)} divisions. "
                f"Found {scores['total_gaps']} gaps: {scores['critical_count']} critical, "
                f"{scores['moderate_count']} moderate, {scores['watch_count']} watch.",
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    # Create gap items
    for gap in scored_gaps:
        item = GapReportItem(
            gap_report_id=report.id,
            division_number=gap["division_number"],
            section_number=gap.get("section_number"),
            title=gap["title"],
            gap_type=gap["gap_type"],
            severity=gap["severity"],
            description=gap.get("description"),
            recommendation=gap.get("recommendation"),
            risk_score=gap.get("risk_score"),
        )
        db.add(item)

    db.commit()

    return validate_agent_output(3, {
        "total_gaps": scores["total_gaps"],
        "critical_count": scores["critical_count"],
        "moderate_count": scores["moderate_count"],
        "watch_count": scores["watch_count"],
        "overall_score": scores["overall_score"],
        "report_id": report.id,
        "sections_analyzed": len(parsed_sections),
    })
