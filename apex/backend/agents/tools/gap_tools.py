"""Gap analysis tools for Agent 3."""

import logging

logger = logging.getLogger("apex.tools.gap")


def checklist_compare_tool(parsed_sections: list[dict], master_checklist: dict) -> list[dict]:
    """Compare parsed spec sections against master scope checklist.

    Args:
        parsed_sections: list of dicts with division_number, section_number
        master_checklist: dict keyed by division with list of required sections

    Returns:
        list of gap items with gap_type and severity
    """
    gaps = []

    # Build set of parsed section numbers (normalized)
    parsed_set = set()
    for s in parsed_sections:
        sec = s.get("section_number", "").replace(" ", "").replace(".", "")
        parsed_set.add(sec)
        # Also add shortened version
        if len(sec) >= 4:
            parsed_set.add(sec[:4])
            parsed_set.add(sec[:6])

    for div_num, checklist_items in master_checklist.items():
        for item in checklist_items:
            sec = item["section"].replace(" ", "").replace(".", "")
            sec_short4 = sec[:4] if len(sec) >= 4 else sec
            sec_short6 = sec[:6] if len(sec) >= 6 else sec

            found = sec in parsed_set or sec_short4 in parsed_set or sec_short6 in parsed_set

            if not found:
                severity = "critical" if item.get("required", False) else "watch"
                gaps.append({
                    "division_number": div_num,
                    "section_number": item["section"],
                    "title": item["title"],
                    "gap_type": "missing",
                    "severity": severity,
                    "description": f"Section {item['section']} ({item['title']}) not found in project specs.",
                    "recommendation": f"Request clarification or add {'required' if item.get('required') else 'optional'} section {item['section']}.",
                })

    return gaps


def gap_scorer_tool(gaps: list[dict]) -> dict:
    """Score gaps by severity and compute overall risk score.

    Returns:
        dict with overall_score, critical_count, moderate_count, watch_count
    """
    critical = sum(1 for g in gaps if g.get("severity") == "critical")
    moderate = sum(1 for g in gaps if g.get("severity") == "moderate")
    watch = sum(1 for g in gaps if g.get("severity") == "watch")

    total = len(gaps) or 1
    # Score: 0 = no risk, 100 = extreme risk
    score = min(100, (critical * 15 + moderate * 5 + watch * 1) / total * 10)

    return {
        "overall_score": round(score, 1),
        "total_gaps": len(gaps),
        "critical_count": critical,
        "moderate_count": moderate,
        "watch_count": watch,
    }


def risk_tagger_tool(gap_item: dict) -> dict:
    """Assign risk tags and scores to individual gap items."""
    severity = gap_item.get("severity", "watch")
    gap_type = gap_item.get("gap_type", "missing")

    risk_score = 0
    if severity == "critical":
        risk_score = 8 + (2 if gap_type == "missing" else 1)
    elif severity == "moderate":
        risk_score = 4 + (2 if gap_type == "conflicting" else 1)
    else:
        risk_score = 1 + (1 if gap_type == "ambiguous" else 0)

    gap_item["risk_score"] = min(10.0, float(risk_score))
    return gap_item
