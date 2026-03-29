"""Accuracy scorer for APEX pipeline results.

Standalone scoring module — no APEX imports, no DB, no LLM calls.
Accepts a pipeline result dict and produces a structured accuracy report.

Usage:
    python -m apex.backend.tests.accuracy_scorer path/to/pipeline_result.json
    python apex/backend/tests/accuracy_scorer.py path/to/pipeline_result.json
"""

from __future__ import annotations

import json
import sys
from typing import Any


# ---------------------------------------------------------------------------
# Per-agent check definitions
# ---------------------------------------------------------------------------

def _check(name: str, passed: bool) -> dict:
    return {"name": name, "passed": passed}


def _score_agent_1(result: dict) -> dict:
    """Agent 1 — Document Ingestion: has 'documents' key with >= 1 item."""
    checks = []
    docs = result.get("documents")
    checks.append(_check("has_documents_key", docs is not None))
    has_items = isinstance(docs, list) and len(docs) >= 1
    checks.append(_check("at_least_1_document", has_items))
    passed = sum(c["passed"] for c in checks)
    return {
        "status": "pass" if passed == len(checks) else "fail",
        "checks": checks,
        "score": passed / len(checks),
    }


def _score_agent_2(result: dict) -> dict:
    """Agent 2 — Spec Parser: has 'spec_sections' with >= 3 sections."""
    checks = []
    sections = result.get("spec_sections")
    checks.append(_check("has_spec_sections_key", sections is not None))
    has_enough = isinstance(sections, list) and len(sections) >= 3
    checks.append(_check("at_least_3_sections", has_enough))
    passed = sum(c["passed"] for c in checks)
    return {
        "status": "pass" if passed == len(checks) else "fail",
        "checks": checks,
        "score": passed / len(checks),
    }


def _score_agent_3(result: dict) -> dict:
    """Agent 3 — Gap Analysis: has 'gap_report' with >= 1 item."""
    checks = []
    gap = result.get("gap_report")
    checks.append(_check("has_gap_report_key", gap is not None))
    if isinstance(gap, dict):
        items = gap.get("gaps") or gap.get("items") or []
        has_items = len(items) >= 1 if isinstance(items, list) else True
    elif isinstance(gap, list):
        has_items = len(gap) >= 1
    else:
        has_items = False
    checks.append(_check("at_least_1_gap_item", has_items))
    passed = sum(c["passed"] for c in checks)
    return {
        "status": "pass" if passed == len(checks) else "fail",
        "checks": checks,
        "score": passed / len(checks),
    }


def _score_agent_4(result: dict) -> dict:
    """Agent 4 — Quantity Takeoff: has 'line_items' with >= 1 having quantity > 0."""
    checks = []
    items = result.get("line_items")
    checks.append(_check("has_line_items_key", items is not None))
    has_qty = False
    if isinstance(items, list) and len(items) >= 1:
        has_qty = any((it.get("quantity") or 0) > 0 for it in items)
    checks.append(_check("at_least_1_with_quantity_gt_0", has_qty))
    passed = sum(c["passed"] for c in checks)
    return {
        "status": "pass" if passed == len(checks) else "fail",
        "checks": checks,
        "score": passed / len(checks),
    }


def _score_agent_5(result: dict) -> dict:
    """Agent 5 — Labor Productivity: >= 50% of line_items have unit_price > 0."""
    checks = []
    items = result.get("line_items")
    checks.append(_check("has_line_items_key", items is not None))
    pct_ok = False
    if isinstance(items, list) and len(items) >= 1:
        with_price = sum(1 for it in items if (it.get("unit_price") or 0) > 0)
        pct_ok = (with_price / len(items)) >= 0.50
    checks.append(_check("at_least_50pct_have_unit_price", pct_ok))
    passed = sum(c["passed"] for c in checks)
    return {
        "status": "pass" if passed == len(checks) else "fail",
        "checks": checks,
        "score": passed / len(checks),
    }


def _score_agent_6(result: dict) -> dict:
    """Agent 6 — Estimate Assembly: total_cost > 0 and executive_summary non-empty."""
    checks = []
    total = result.get("total_cost")
    checks.append(_check("total_cost_gt_0", isinstance(total, (int, float)) and total > 0))
    summary = result.get("executive_summary")
    checks.append(_check("executive_summary_non_empty", isinstance(summary, str) and len(summary.strip()) > 0))
    passed = sum(c["passed"] for c in checks)
    return {
        "status": "pass" if passed == len(checks) else "fail",
        "checks": checks,
        "score": passed / len(checks),
    }


def _score_agent_7(result: dict) -> dict:
    """Agent 7 — IMPROVE Feedback: has 'schedule' or 'milestones' with >= 1 entry."""
    checks = []
    sched = result.get("schedule")
    miles = result.get("milestones")
    has_key = sched is not None or miles is not None
    checks.append(_check("has_schedule_or_milestones_key", has_key))
    has_entries = False
    for coll in (sched, miles):
        if isinstance(coll, list) and len(coll) >= 1:
            has_entries = True
            break
    checks.append(_check("at_least_1_entry", has_entries))
    passed = sum(c["passed"] for c in checks)
    return {
        "status": "pass" if passed == len(checks) else "fail",
        "checks": checks,
        "score": passed / len(checks),
    }


AGENT_SCORERS = {
    "agent_1": _score_agent_1,
    "agent_2": _score_agent_2,
    "agent_3": _score_agent_3,
    "agent_4": _score_agent_4,
    "agent_5": _score_agent_5,
    "agent_6": _score_agent_6,
    "agent_7": _score_agent_7,
}


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_line_item_stats(result: dict) -> dict:
    items = result.get("line_items") or []
    if not isinstance(items, list):
        items = []
    total = len(items)
    with_price = sum(1 for it in items if (it.get("unit_price") or 0) > 0)
    with_qty = sum(1 for it in items if (it.get("quantity") or 0) > 0)
    with_csi = sum(1 for it in items if it.get("csi_code"))
    missing_all = sum(
        1 for it in items
        if (it.get("unit_price") or 0) == 0
        and (it.get("quantity") or 0) == 0
        and not it.get("csi_code")
    )
    coverage = (
        sum(1 for it in items if (it.get("unit_price") or 0) > 0 and (it.get("quantity") or 0) > 0)
        / total * 100 if total > 0 else 0.0
    )
    return {
        "total_items": total,
        "items_with_unit_price": with_price,
        "items_with_quantity": with_qty,
        "items_with_csi_code": with_csi,
        "items_missing_all": missing_all,
        "coverage_pct": round(coverage, 2),
    }


def _build_gap_analysis(result: dict) -> dict:
    gap = result.get("gap_report")
    if isinstance(gap, dict):
        items = gap.get("gaps") or gap.get("items") or []
    elif isinstance(gap, list):
        items = gap
    else:
        items = []
    if not isinstance(items, list):
        items = []
    total = len(items)
    with_csi = sum(1 for g in items if g.get("csi_code") or g.get("csi_division"))
    resolved = sum(1 for g in items if g.get("suggested_action"))
    return {
        "total_gaps": total,
        "gaps_with_csi": with_csi,
        "gaps_resolved": resolved,
    }


def _build_cost_summary(result: dict) -> dict:
    total_cost = result.get("total_cost")
    if not isinstance(total_cost, (int, float)):
        total_cost = 0.0
    has_summary = isinstance(result.get("executive_summary"), str) and len(
        (result.get("executive_summary") or "").strip()
    ) > 0
    has_sched = bool(result.get("schedule") or result.get("milestones"))
    return {
        "total_cost_usd": float(total_cost),
        "has_executive_summary": has_summary,
        "has_schedule": has_sched,
    }


# ---------------------------------------------------------------------------
# Main scorer
# ---------------------------------------------------------------------------

def score_pipeline_result(result: dict, verbose: bool = False) -> dict:
    """Score a completed pipeline result and return a structured accuracy report.

    Parameters
    ----------
    result : dict
        The final JSON output from the pipeline (e.g. saved by test_pipeline_e2e.py).
    verbose : bool
        If True, print a human-readable summary line per agent to stdout.

    Returns
    -------
    dict with keys: agent_scores, pipeline_summary, line_item_stats,
    gap_analysis, cost_summary.
    """
    agent_scores: dict[str, dict[str, Any]] = {}

    for agent_key, scorer in AGENT_SCORERS.items():
        # Determine whether this agent's data is present at all
        # Each scorer checks specific keys; if all relevant keys are missing, mark skip
        score_result = scorer(result)

        # If none of the checks have any data to work with, treat as skip
        all_failed_due_to_missing = all(not c["passed"] for c in score_result["checks"])
        # Specifically check if the primary key for this agent exists
        agent_num = int(agent_key.split("_")[1])
        primary_keys = {
            1: ["documents"],
            2: ["spec_sections"],
            3: ["gap_report"],
            4: ["line_items"],
            5: ["line_items"],
            6: ["total_cost", "executive_summary"],
            7: ["schedule", "milestones"],
        }
        keys_present = any(k in result for k in primary_keys[agent_num])
        if not keys_present:
            agent_scores[agent_key] = {
                "status": "skip",
                "checks": score_result["checks"],
                "score": 0.0,
            }
        else:
            agent_scores[agent_key] = score_result

        if verbose:
            s = agent_scores[agent_key]
            total_checks = len(s["checks"])
            passed_checks = sum(1 for c in s["checks"] if c["passed"])
            tag = s["status"].upper()
            print(
                f"Agent {agent_num} [{tag}] — "
                f"score: {s['score']:.2f} — "
                f"checks: {passed_checks}/{total_checks} passed"
            )

    # Pipeline summary
    statuses = [v["status"] for v in agent_scores.values()]
    scores = [v["score"] for v in agent_scores.values()]
    pipeline_summary = {
        "total_agents": len(agent_scores),
        "passed": statuses.count("pass"),
        "failed": statuses.count("fail"),
        "skipped": statuses.count("skip"),
        "overall_score": round(sum(scores) / len(scores), 4) if scores else 0.0,
    }

    return {
        "agent_scores": agent_scores,
        "pipeline_summary": pipeline_summary,
        "line_item_stats": _build_line_item_stats(result),
        "gap_analysis": _build_gap_analysis(result),
        "cost_summary": _build_cost_summary(result),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python accuracy_scorer.py <pipeline_result.json>", file=sys.stderr)
        sys.exit(1)

    result_file = sys.argv[1]
    with open(result_file) as f:
        result = json.load(f)
    report = score_pipeline_result(result, verbose=True)
    print(json.dumps(report, indent=2))
