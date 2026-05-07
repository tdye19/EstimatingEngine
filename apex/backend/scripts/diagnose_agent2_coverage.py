"""Diagnostic CLI for Agent 2 / Agent 2B coverage analysis.

Read-only. Writes JSON + Markdown artifacts. Modifies no DB rows.

Usage:
    python -m apex.backend.scripts.diagnose_agent2_coverage --project-id N
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from apex.backend.db.database import SessionLocal
from apex.backend.models.agent_run_log import AgentRunLog
from apex.backend.models.document import Document
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.work_category import WorkCategory

# ---------------------------------------------------------------------------
# Pattern constants
# ---------------------------------------------------------------------------

CSI_SECTION_RE = re.compile(r"SECTION\s+\d{2}\s+\d{2}\s+\d{2}")
BARE_SITECIVIL_RE = re.compile(r"\b(03|31|32|33)\d{4}\b")
WC_HEADING_RE = re.compile(r"WC[-\s]?\d{2}[A-Z]?")
WORK_CATEGORY_NO_RE = re.compile(r"Work Category No\.?\s*\d+")
DIVISION_HEADER_RE = re.compile(r"DIVISION\s+\d{2}")

SITE_CIVIL_DIVS = {"31", "32", "33"}

# ---------------------------------------------------------------------------
# Pure functions (tested in isolation)
# ---------------------------------------------------------------------------


def infer_agent2_method(duration_ms: float | None) -> str:
    if duration_ms is None:
        return "UNKNOWN"
    if duration_ms < 2000:
        return "FALLBACK_REGEX_LIKELY"
    if duration_ms <= 10000:
        return "AMBIGUOUS"
    return "LLM_LIKELY"


def infer_agent2b_method(duration_ms: float | None) -> str:
    if duration_ms is None:
        return "UNKNOWN"
    if duration_ms < 100:
        return "NO_OP_OR_GATE_REJECTED"
    if duration_ms < 1000:
        return "RULE_BASED_LIKELY"
    return "LLM_LIKELY"


def count_patterns(text: str) -> dict[str, int]:
    return {
        "csi_section_headers": len(CSI_SECTION_RE.findall(text)),
        "bare_site_civil_6digit": len(BARE_SITECIVIL_RE.findall(text)),
        "wc_headings": len(WC_HEADING_RE.findall(text)),
        "work_category_no": len(WORK_CATEGORY_NO_RE.findall(text)),
        "division_headers": len(DIVISION_HEADER_RE.findall(text)),
    }


def build_hypotheses(
    agent2_method: str,
    agent2b_method: str,
    agent2_coverage: dict[str, int],
    agent2b_runs: list[dict],
    wc_counts: list[dict],
    raw_text_signals: dict,
) -> list[str]:
    hypotheses: list[str] = []

    total_wc_patterns = sum(
        d.get("wc_headings", 0) for d in raw_text_signals.values() if isinstance(d, dict)
    )
    has_31_32_33_text = raw_text_signals.get("_any_site_civil_text", False)
    covered_divs = set(agent2_coverage.keys())

    # --- Agent 2 hypotheses ---
    if agent2_method == "FALLBACK_REGEX_LIKELY" and total_wc_patterns > 0:
        hypotheses.append(
            "Agent 2 regex fallback fired on Work Scopes doc. "
            "Investigate why LLM call failed: check OpenRouter credit, "
            "AGENT_2_PROVIDER env var, last error in logs."
        )

    missing_site_civil = SITE_CIVIL_DIVS - covered_divs
    if (
        agent2_method == "LLM_LIKELY"
        and missing_site_civil
        and has_31_32_33_text
    ):
        hypotheses.append(
            f"Agent 2 LLM call dropped Div {'/'.join(sorted(missing_site_civil))} content. "
            "Investigate prompt design and chunking — document may use WC-XX-style "
            "headings rather than standard CSI SECTION headers; prompt may not handle them."
        )

    if agent2_method == "LLM_LIKELY" and not missing_site_civil:
        hypotheses.append(
            "Agent 2 working as designed — Div 31/32/33 sections ARE present in DB. "
            "Handoff observation may reflect an earlier failed run (regex fallback), "
            "not the most recent LLM run. Verify against run timestamps."
        )

    if agent2_method == "LLM_LIKELY" and missing_site_civil and not has_31_32_33_text:
        hypotheses.append(
            "Agent 2 coverage looks proportional to raw_text content — Div 31/32/33 "
            "textual content is absent from extracted raw_text. "
            "Calibration corpus needed (Sprint 19E.4)."
        )

    # --- Agent 2B hypotheses ---
    if not agent2b_runs:
        hypotheses.append(
            "Agent 2B never ran for this project. "
            "Investigate orchestrator pipeline order and Agent 2B trigger conditions."
        )
    elif agent2b_method == "NO_OP_OR_GATE_REJECTED":
        if total_wc_patterns > 5:
            hypotheses.append(
                f"Agent 2B classifier gate rejected the document despite {total_wc_patterns} "
                "WC-XX patterns detected. Investigate the work-scope-eligibility "
                "classification logic."
            )
        else:
            hypotheses.append(
                "Agent 2B ran as NO-OP (< 100 ms). No document in this project is classified "
                "as a work-scopes document. The KCCU Volume 2 Work Scopes PDF may not have "
                "been uploaded to this project yet."
            )
    elif agent2b_method == "LLM_LIKELY" and len(wc_counts) == 0:
        hypotheses.append(
            "Agent 2B LLM ran but persisted nothing. "
            "Investigate output parsing and DB write path."
        )

    return hypotheses


# ---------------------------------------------------------------------------
# DB collectors
# ---------------------------------------------------------------------------


def collect_documents(session: Session, project_id: int) -> list[dict]:
    docs = session.query(Document).filter(Document.project_id == project_id).order_by(Document.id).all()
    result = []
    for d in docs:
        rt = d.raw_text or ""
        patterns = count_patterns(rt)
        result.append(
            {
                "id": d.id,
                "filename": d.filename,
                "file_type": d.file_type,
                "classification": d.classification,
                "page_count": d.page_count,
                "raw_text_len": len(rt),
                "raw_text_first_500": rt[:500],
                "raw_text_last_500": rt[-500:] if len(rt) > 500 else "",
                "patterns": patterns,
            }
        )
    return result


def collect_agent2_runs(session: Session, project_id: int) -> list[dict]:
    rows = (
        session.query(AgentRunLog)
        .filter(
            AgentRunLog.project_id == project_id,
            AgentRunLog.agent_number == 2,
        )
        .order_by(AgentRunLog.id)
        .all()
    )
    result = []
    for r in rows:
        duration_ms = (r.duration_seconds * 1000) if r.duration_seconds is not None else None
        result.append(
            {
                "run_id": r.id,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "duration_ms": duration_ms,
                "status": r.status,
                "output_data": r.output_data,
                "error_message": r.error_message,
            }
        )
    return result


def collect_agent2b_runs(session: Session, project_id: int) -> list[dict]:
    rows = (
        session.query(AgentRunLog)
        .filter(
            AgentRunLog.project_id == project_id,
            AgentRunLog.agent_name.ilike("%Work Scope%"),
        )
        .order_by(AgentRunLog.id)
        .all()
    )
    result = []
    for r in rows:
        duration_ms = (r.duration_seconds * 1000) if r.duration_seconds is not None else None
        result.append(
            {
                "run_id": r.id,
                "agent_number": r.agent_number,
                "agent_name": r.agent_name,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "duration_ms": duration_ms,
                "status": r.status,
                "output_data": r.output_data,
                "error_message": r.error_message,
            }
        )
    return result


def collect_spec_coverage(session: Session, project_id: int) -> tuple[list[dict], dict[str, int]]:
    rows = session.query(SpecSection).filter(SpecSection.project_id == project_id).order_by(SpecSection.id).all()
    sections = []
    by_div: dict[str, int] = defaultdict(int)
    for r in rows:
        by_div[r.division_number] += 1
        sections.append(
            {
                "id": r.id,
                "section_number": r.section_number,
                "division_number": r.division_number,
                "title": r.title,
                "content_len": len(r.raw_text or ""),
                "keywords": r.keywords,
            }
        )
    return sections, dict(by_div)


def collect_work_categories(session: Session, project_id: int) -> list[dict]:
    rows = session.query(WorkCategory).filter(WorkCategory.project_id == project_id).order_by(WorkCategory.id).all()
    result = []
    for r in rows:
        result.append(
            {
                "id": r.id,
                "wc_number": r.wc_number,
                "title": r.title,
                "work_included_count": len(r.work_included_items or []),
                "related_work_by_others_count": len(r.related_work_by_others or []),
                "add_alternates_count": len(r.add_alternates or []),
                "allowances_count": len(r.allowances or []),
                "unit_prices_count": len(r.unit_prices or []),
                "parse_method": r.parse_method,
                "parse_confidence": r.parse_confidence,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Routing gate analysis
# ---------------------------------------------------------------------------


def analyze_routing(documents: list[dict]) -> list[dict]:
    routing = []
    for d in documents:
        cls = (d["classification"] or "").lower()
        wc_count = d["patterns"]["wc_headings"]

        routed_spec = cls in ("spec", "specification")
        routed_work_scopes = "work_scope" in cls or "work scope" in cls

        flag = None
        if wc_count > 5 and not routed_work_scopes:
            flag = f"POSSIBLE_MISCLASSIFICATION: {wc_count} WC-XX patterns but not routed to Agent 2B"

        routing.append(
            {
                "doc_id": d["id"],
                "filename": d["filename"],
                "classification": d["classification"],
                "routed_agent2_spec": routed_spec,
                "routed_agent2b_work_scopes": routed_work_scopes,
                "wc_pattern_count": wc_count,
                "flag": flag,
            }
        )
    return routing


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(data: dict) -> str:
    lines: list[str] = []
    pid = data["project_id"]
    ts = data["timestamp"]

    lines += [
        f"# Agent 2 / Agent 2B Diagnostic — Project {pid}",
        f"_Generated: {ts}_",
        "",
    ]

    # Summary banner
    lines += [
        "## Summary",
        f"- **Agent 2 inferred method:** `{data['agent_2_inferred_method']}`",
        f"- **Agent 2B inferred method:** `{data['agent_2b_inferred_method']}`",
        f"- **Spec sections extracted:** {sum(data['agent_2_coverage'].values())}",
        f"- **Work categories extracted:** {len(data['work_categories'])}",
        f"- **Hypotheses generated:** {len(data['hypotheses'])}",
        "",
    ]

    # Document inventory
    lines += ["## Document Inventory", ""]
    for d in data["documents"]:
        lines += [
            f"### Doc {d['id']}: {d['filename']}",
            f"- file_type: `{d['file_type']}` | classification: `{d['classification']}`",
            f"- page_count: {d['page_count']} | raw_text_len: {d['raw_text_len']:,}",
            "- **Pattern counts:**",
        ]
        for k, v in d["patterns"].items():
            lines.append(f"  - {k}: {v}")
        if d["raw_text_first_500"]:
            lines += [
                "- **First 500 chars:**",
                "```",
                d["raw_text_first_500"],
                "```",
            ]
        lines.append("")

    # Agent 2 runs
    lines += ["## Agent 2 Runs (Spec Parser)", ""]
    if not data["agent_2_runs"]:
        lines.append("_No runs found._")
    for r in data["agent_2_runs"]:
        ms = f"{r['duration_ms']:.1f} ms" if r["duration_ms"] is not None else "N/A"
        lines += [
            f"### Run {r['run_id']}",
            f"- Status: `{r['status']}` | Duration: {ms}",
            f"- Started: {r['started_at']} | Completed: {r['completed_at']}",
        ]
        if r["output_data"]:
            lines += [
                "- output_data:",
                "```json",
                json.dumps(r["output_data"], indent=2, default=str),
                "```",
            ]
        if r["error_message"]:
            lines.append(f"- **Error:** {r['error_message']}")
        lines.append("")

    # Agent 2 coverage map
    lines += ["## Agent 2 Coverage Map (by Division)", ""]
    if data["agent_2_coverage"]:
        for div, count in sorted(data["agent_2_coverage"].items()):
            marker = " ← SITE/CIVIL" if div in SITE_CIVIL_DIVS else ""
            lines.append(f"- Division {div}: {count} section(s){marker}")
    else:
        lines.append("_No spec sections found._")
    lines.append("")

    # Agent 2B runs
    lines += ["## Agent 2B Runs (Work Scope Parser)", ""]
    if not data["agent_2b_runs"]:
        lines.append("_No runs found._")
    for r in data["agent_2b_runs"]:
        ms = f"{r['duration_ms']:.1f} ms" if r["duration_ms"] is not None else "N/A"
        lines += [
            f"### Run {r['run_id']} (agent_number={r['agent_number']})",
            f"- Status: `{r['status']}` | Duration: {ms}",
            f"- Started: {r['started_at']} | Completed: {r['completed_at']}",
        ]
        if r["output_data"]:
            lines += [
                "- output_data:",
                "```json",
                json.dumps(r["output_data"], indent=2, default=str),
                "```",
            ]
        lines.append("")

    # Work categories
    lines += ["## Work Categories", ""]
    if not data["work_categories"]:
        lines.append("_None found._")
    for wc in data["work_categories"]:
        lines.append(
            f"- WC-{wc['wc_number']}: {wc['title']} "
            f"(incl={wc['work_included_count']}, excl={wc['related_work_by_others_count']}, "
            f"alt={wc['add_alternates_count']}, allow={wc['allowances_count']}, "
            f"unit_px={wc['unit_prices_count']}, method={wc['parse_method']})"
        )
    lines.append("")

    # Routing analysis
    lines += ["## Document Routing (Classification Gate)", ""]
    for r in data.get("routing_analysis", []):
        flag_str = f" **⚠ {r['flag']}**" if r["flag"] else ""
        lines.append(
            f"- Doc {r['doc_id']} `{r['filename']}`: "
            f"cls=`{r['classification']}` | "
            f"→ Agent2={r['routed_agent2_spec']} Agent2B={r['routed_agent2b_work_scopes']} | "
            f"WC-XX count={r['wc_pattern_count']}{flag_str}"
        )
    lines.append("")

    # Hypotheses
    lines += ["## Likely Root Causes", ""]
    if not data["hypotheses"]:
        lines.append("_No hypotheses generated._")
    for i, h in enumerate(data["hypotheses"], 1):
        lines.append(f"{i}. {h}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run_diagnostic(project_id: int, out_dir: Path) -> int:
    session = SessionLocal()
    try:
        from apex.backend.models.project import Project

        project = session.query(Project).filter(Project.id == project_id).first()
        if not project:
            print(f"ERROR: project_id={project_id} not found in DB.", file=sys.stderr)
            return 2

        documents = collect_documents(session, project_id)
        agent2_runs = collect_agent2_runs(session, project_id)
        agent2b_runs = collect_agent2b_runs(session, project_id)
        spec_sections, agent2_coverage = collect_spec_coverage(session, project_id)
        work_categories = collect_work_categories(session, project_id)
        routing = analyze_routing(documents)

        if not agent2_runs:
            print(
                f"ERROR: No AgentRunLog rows for Agent 2 on project {project_id}. "
                "Pipeline never ran on this project — upload and run pipeline first.",
                file=sys.stderr,
            )
            return 3

        # Inferred methods — use the most recent completed/failed run
        def _best_run_ms(runs: list[dict]) -> float | None:
            completed = [r for r in runs if r["status"] in ("completed", "failed") and r["duration_ms"] is not None]
            if not completed:
                return None
            return completed[-1]["duration_ms"]

        a2_ms = _best_run_ms(agent2_runs)
        a2b_ms = _best_run_ms(agent2b_runs)

        # Cross-check parse_method from output_data if available
        a2_method = infer_agent2_method(a2_ms)
        for r in reversed(agent2_runs):
            od = r.get("output_data") or {}
            if od.get("parse_method") == "llm":
                a2_method = "LLM_LIKELY"
                break
            if od.get("parse_method") in ("regex", "regex_fallback"):
                a2_method = "FALLBACK_REGEX_LIKELY"
                break

        a2b_method = infer_agent2b_method(a2b_ms)

        # Raw text signals for hypothesis engine
        raw_signals: dict[str, Any] = {}
        any_site_civil_text = False
        for d in documents:
            raw_signals[d["id"]] = d["patterns"]
            if d["patterns"]["bare_site_civil_6digit"] > 0 or d["patterns"]["division_headers"] > 0:
                any_site_civil_text = True
        raw_signals["_any_site_civil_text"] = any_site_civil_text

        hypotheses = build_hypotheses(
            agent2_method=a2_method,
            agent2b_method=a2b_method,
            agent2_coverage=agent2_coverage,
            agent2b_runs=agent2b_runs,
            wc_counts=work_categories,
            raw_text_signals=raw_signals,
        )

        # Detect classification contradictions across runs
        filenames_by_cls: dict[str, set[str]] = defaultdict(set)
        for d in documents:
            filenames_by_cls[d["classification"] or "None"].add(d["filename"])
        # Same filename appearing under multiple classifications → contradiction
        fname_cls_map: dict[str, list[str]] = defaultdict(list)
        for cls, fnames in filenames_by_cls.items():
            for fn in fnames:
                fname_cls_map[fn].append(cls)
        for fn, classes in fname_cls_map.items():
            if len(classes) > 1:
                print(f"WARNING: '{fn}' has conflicting classifications across rows: {classes}")

        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        date_str = datetime.now(tz=timezone.utc).strftime("%Y%m%d")

        artifact = {
            "project_id": project_id,
            "timestamp": ts,
            "documents": documents,
            "agent_2_runs": agent2_runs,
            "agent_2_coverage": agent2_coverage,
            "agent_2_inferred_method": a2_method,
            "agent_2b_runs": agent2b_runs,
            "agent_2b_inferred_method": a2b_method,
            "work_categories": work_categories,
            "hypotheses": hypotheses,
            "routing_analysis": routing,
        }

        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / f"project_{project_id}_agent2_diag_{date_str}.json"
        md_path = out_dir / f"project_{project_id}_agent2_diag_{date_str}.md"

        json_path.write_text(json.dumps(artifact, indent=2, default=str))
        md_path.write_text(render_markdown(artifact))

        print(
            f"Wrote diagnostic JSON to {json_path} and markdown summary to {md_path}. "
            f"Agent 2: {a2_method}. Agent 2B: {a2b_method}. Hypotheses: {len(hypotheses)}."
        )
        return 0

    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose Agent 2 / 2B coverage for a project.")
    parser.add_argument("--project-id", required=True, type=int)
    parser.add_argument(
        "--out-dir",
        default="apex/docs/diagnostics",
        help="Output directory (default: apex/docs/diagnostics)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    rc = run_diagnostic(project_id=args.project_id, out_dir=out_dir)
    sys.exit(rc)


if __name__ == "__main__":
    main()
