"""Spike 19E.5: Rule Grounding Validation Diagnostic.

Read-only. Loads project N's spec sections, work categories, and takeoff items,
constructs an Agent 3-shaped prompt that includes the 25 domain rules as
structured grounding, calls the production Agent 3 model once, and measures
whether the LLM correctly names rule_id references in gap findings.

This script does NOT modify production Agent 3 behavior. It runs in parallel
as a measurement tool. No writes to AgentRunLog, no DB mutations.

Usage:
    python -m apex.backend.scripts.spike_19e5_rule_grounding --project-id 5
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from apex.backend.agents.tools.domain_gap_rules import ALL_DOMAIN_RULES
from apex.backend.db.database import SessionLocal
from apex.backend.models.spec_section import SpecSection
from apex.backend.models.work_category import WorkCategory
from apex.backend.services.llm_provider import get_llm_provider
from apex.backend.utils.async_helper import run_async as _run_async

logger = logging.getLogger("apex.spike.19e5")

# ---------------------------------------------------------------------------
# ADR thresholds (binding, pre-declared in ADR-domain-rule-direction-c-strict.md)
# ---------------------------------------------------------------------------

ADR_VALID_CITE_THRESHOLD = 0.80
ADR_HALLUCINATION_THRESHOLD = 0.05

# ---------------------------------------------------------------------------
# Rule library
# ---------------------------------------------------------------------------


def load_rule_library() -> tuple[list[dict], set[str]]:
    """Return (grounding_list, valid_id_set) from ALL_DOMAIN_RULES.

    grounding_list is the spike-only JSON format sent to the LLM.
    valid_id_set is used for classification.
    """
    grounding: list[dict] = []
    valid_ids: set[str] = set()
    for rule in ALL_DOMAIN_RULES:
        valid_ids.add(rule.id)
        grounding.append(
            {
                "rule_id": rule.id,
                "category": rule.gap_type,
                "trigger_summary": rule.title,
                "typical_responsibility": rule.typical_responsibility,
            }
        )
    return grounding, valid_ids


# ---------------------------------------------------------------------------
# Finding classification (pure function — tested in isolation)
# ---------------------------------------------------------------------------


def classify_finding(finding: dict, valid_ids: set[str]) -> str:
    """Classify a single gap finding.

    Returns one of:
      'valid_cite'   — finding has a rule_id that exists in the library
      'hallucinated' — finding has a rule_id that does NOT exist in the library
      'no_cite'      — finding has no rule_id (or null/empty)
    """
    rule_id = finding.get("rule_id")
    if not rule_id:
        return "no_cite"
    if rule_id in valid_ids:
        return "valid_cite"
    return "hallucinated"


# ---------------------------------------------------------------------------
# DB data loading
# ---------------------------------------------------------------------------


def load_project_data(session, project_id: int) -> tuple[list[dict], list[dict], list[dict]]:
    """Load spec sections, work categories, and takeoff items for the project.

    Returns (specs, wcs, takeoffs) as lists of plain dicts.
    """
    spec_rows = (
        session.query(SpecSection)
        .filter(
            SpecSection.project_id == project_id,
            SpecSection.is_deleted == False,  # noqa: E712
        )
        .all()
    )
    specs = [
        {
            "section_number": s.section_number,
            "division_number": s.division_number,
            "title": s.title,
            "text": (s.raw_text or "")[:2000],
        }
        for s in spec_rows
    ]

    wc_rows = (
        session.query(WorkCategory)
        .filter(WorkCategory.project_id == project_id)
        .all()
    )
    wcs = [
        {
            "wc_number": w.wc_number,
            "title": w.title,
            "work_included": (w.work_included_items or [])[:20],
        }
        for w in wc_rows
    ]

    from apex.backend.models.takeoff_v2 import TakeoffItemV2

    takeoff_rows = (
        session.query(TakeoffItemV2)
        .filter(TakeoffItemV2.project_id == project_id)
        .all()
    )
    takeoffs = [
        {
            "description": t.activity,
            "quantity": t.quantity,
            "unit": t.unit,
        }
        for t in takeoff_rows
    ]

    return specs, wcs, takeoffs


# ---------------------------------------------------------------------------
# Spike-only system prompt
# ---------------------------------------------------------------------------

_SPIKE_SYSTEM_PROMPT = """\
You are a senior construction estimator with 20+ years of experience identifying \
scope gaps in commercial building specifications for general contractors.

You will receive:
1. Parsed CSI MasterFormat spec sections from a project specification
2. Work Categories defining the bid scope boundaries
3. Takeoff Items from the estimator's quantity survey
4. A Domain Rule Library of 25 construction-specific scope gap rules

Your task: Identify scope gaps in this project. For each gap finding:
- Write a clear description of the gap and its cost/risk implications
- Assign severity: "critical", "high", "medium", or "low"
- Name the affected CSI division (e.g., "03", "31")
- Provide a recommendation for the estimator
- If ONE of the Domain Rule Library entries directly applies, include a \
"rule_id" field with the exact rule identifier (e.g., "CGR-001"). \
Do NOT invent rule IDs not in the library. \
Do NOT include dollar amounts, cost ranges, or canonical responsibility text \
— only name the rule. \
If no rule clearly applies, omit the rule_id field entirely.

Respond ONLY with a valid JSON array. No markdown fences, no preamble — \
just the raw JSON array.

Each object must have exactly these fields:
  "description"           — gap explanation with cost risk
  "severity"              — "critical", "high", "medium", or "low"
  "affected_csi_division" — CSI division string, e.g. "03" or "31"
  "recommendation"        — specific action before finalizing bid
  "rule_id"               — (optional) exact rule_id from Domain Rule Library if applicable
"""


def build_user_prompt(
    specs: list[dict],
    wcs: list[dict],
    takeoffs: list[dict],
    grounding: list[dict],
) -> str:
    return "\n\n".join(
        [
            "## SPEC SECTIONS\n" + json.dumps(specs, indent=2),
            "## WORK CATEGORIES\n" + json.dumps(wcs, indent=2),
            "## TAKEOFF ITEMS\n" + json.dumps(takeoffs, indent=2),
            "## DOMAIN RULE LIBRARY\n" + json.dumps(grounding, indent=2),
            "Identify all scope gaps. Include rule_id only when a listed rule directly applies.",
        ]
    )


# ---------------------------------------------------------------------------
# LLM call — single shot, no retries
# ---------------------------------------------------------------------------


async def _call_llm(provider, system_prompt: str, user_prompt: str):
    return await provider.complete(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        temperature=0.1,
        max_tokens=16000,
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------


def parse_llm_response(raw_content: str) -> list[dict]:
    """Strip optional markdown fences and parse JSON array."""
    content = raw_content.strip()
    content = re.sub(r"^```(?:json)?\s*", "", content)
    content = re.sub(r"\s*```$", "", content.strip()).strip()
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        logger.error("Spike 19E.5: JSON parse error — %s", exc)
        return []
    if not isinstance(data, list):
        logger.error("Spike 19E.5: expected JSON array, got %s", type(data).__name__)
        return []
    return data


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def compute_metrics(
    findings: list[dict], valid_ids: set[str]
) -> tuple[dict, list[dict]]:
    """Classify all findings and compute aggregate metrics."""
    classified: list[dict] = []
    for f in findings:
        cls = classify_finding(f, valid_ids)
        rule_id = f.get("rule_id")
        rule_summary = None
        if cls == "valid_cite":
            for r in ALL_DOMAIN_RULES:
                if r.id == rule_id:
                    rule_summary = r.title
                    break
        classified.append(
            {
                "description": (f.get("description") or "")[:200],
                "rule_id": rule_id,
                "classification": cls,
                "rule_trigger_summary": rule_summary,
            }
        )

    total = len(findings)
    valid_count = sum(1 for c in classified if c["classification"] == "valid_cite")
    hallucinated_count = sum(1 for c in classified if c["classification"] == "hallucinated")
    no_cite_count = sum(1 for c in classified if c["classification"] == "no_cite")
    cited_count = valid_count + hallucinated_count

    metrics = {
        "total_findings": total,
        "valid_cite_count": valid_count,
        "hallucinated_count": hallucinated_count,
        "no_cite_count": no_cite_count,
        "valid_cite_rate_overall": round(valid_count / total, 4) if total else 0.0,
        "valid_cite_rate_among_cited": round(valid_count / cited_count, 4) if cited_count else 0.0,
        "hallucinated_rate": round(hallucinated_count / total, 4) if total else 0.0,
        "no_cite_rate": round(no_cite_count / total, 4) if total else 0.0,
    }
    return metrics, classified


# ---------------------------------------------------------------------------
# Pass / fail evaluation
# ---------------------------------------------------------------------------


def evaluate_pass_fail(metrics: dict) -> tuple[bool, list[str]]:
    """Evaluate metrics against ADR thresholds.

    NOTE: The ADR's 80% cite criterion applies to findings where a rule is
    *applicable*. This function uses valid_cite_rate_among_cited as the closest
    automatable proxy. Manual applicability grading by Tucker is required for
    the definitive ADR determination.
    """
    reasons: list[str] = []

    hall_ok = metrics["hallucinated_rate"] < ADR_HALLUCINATION_THRESHOLD
    if not hall_ok:
        reasons.append(
            f"hallucinated_rate={metrics['hallucinated_rate']:.1%} >= threshold {ADR_HALLUCINATION_THRESHOLD:.0%}"
        )

    cite_ok = metrics["valid_cite_rate_among_cited"] >= ADR_VALID_CITE_THRESHOLD
    if not cite_ok:
        reasons.append(
            f"valid_cite_rate_among_cited={metrics['valid_cite_rate_among_cited']:.1%}"
            f" < threshold {ADR_VALID_CITE_THRESHOLD:.0%}"
            " (proxy — manual applicability grading required for definitive ADR eval)"
        )

    return hall_ok and cite_ok, reasons


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def render_markdown(
    project_id: int,
    provider_name: str,
    model_name: str,
    metrics: dict,
    classified: list[dict],
    passed: bool,
    fail_reasons: list[str],
    token_counts: dict,
    timestamp: str,
) -> str:
    result_line = "RESULT: PASS" if passed else "RESULT: FAIL"
    lines: list[str] = [result_line, ""]

    lines += [
        f"# Spike 19E.5 — Rule Grounding Validation — Project {project_id}",
        f"_Generated: {timestamp}_",
        f"_Provider: {provider_name} / {model_name}_",
        "",
    ]

    lines += [
        "## ADR Threshold Evaluation",
        f"- **ADR cite threshold:** ≥{ADR_VALID_CITE_THRESHOLD:.0%} of applicable findings cite a valid rule_id",
        f"- **ADR hallucination threshold:** <{ADR_HALLUCINATION_THRESHOLD:.0%} hallucinated rule IDs",
        f"- **Automated result:** `{result_line}`",
        "",
    ]

    if fail_reasons:
        lines.append("**Fail reasons:**")
        for r in fail_reasons:
            lines.append(f"- {r}")
        lines.append("")

    lines += [
        "> **Denominator note:** The ADR's 80% criterion applies to findings where a rule is",
        "> _applicable_, not all findings. `valid_cite_rate_among_cited` is the closest automatable",
        "> proxy (denominator = findings where the LLM chose to cite any rule). Tucker must manually",
        "> grade applicability on the sample below to confirm the ADR determination.",
        "",
    ]

    lines += [
        "## Metrics",
        "| Metric | Value |",
        "|--------|-------|",
        f"| total_findings | {metrics['total_findings']} |",
        f"| valid_cite_count | {metrics['valid_cite_count']} |",
        f"| hallucinated_count | {metrics['hallucinated_count']} |",
        f"| no_cite_count | {metrics['no_cite_count']} |",
        f"| valid_cite_rate_overall | {metrics['valid_cite_rate_overall']:.1%} |",
        f"| valid_cite_rate_among_cited | {metrics['valid_cite_rate_among_cited']:.1%} |",
        f"| hallucinated_rate | {metrics['hallucinated_rate']:.1%} |",
        f"| no_cite_rate | {metrics['no_cite_rate']:.1%} |",
        "",
    ]

    lines += [
        "## Token Usage",
        f"- input_tokens: {token_counts.get('input_tokens', 'N/A')}",
        f"- output_tokens: {token_counts.get('output_tokens', 'N/A')}",
        f"- duration_ms: {token_counts.get('duration_ms', 'N/A')}",
        f"- estimated_cost_usd: {token_counts.get('estimated_cost_usd', 'N/A')} (approximate)",
        "",
    ]

    lines += [
        "## Sample Findings (~10) — Manual Applicability Grading Required",
        "",
        "| # | Classification | Rule ID | Trigger Summary | Description (truncated) |",
        "|---|----------------|---------|-----------------|------------------------|",
    ]
    for i, c in enumerate(classified[:10], 1):
        cls_label = {"valid_cite": "valid_cite", "hallucinated": "HALLUCINATED", "no_cite": "no_cite"}[
            c["classification"]
        ]
        rid = c["rule_id"] or "—"
        summary = (c["rule_trigger_summary"] or "—")[:50]
        desc = c["description"][:80].replace("|", "/")
        lines.append(f"| {i} | {cls_label} | {rid} | {summary} | {desc} |")

    lines += [
        "",
        "## All Findings — Full Classification",
        "",
        "| # | Classification | Rule ID |",
        "|---|----------------|---------|",
    ]
    for i, c in enumerate(classified, 1):
        rid = c["rule_id"] or "—"
        lines.append(f"| {i} | {c['classification']} | {rid} |")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Error report writer
# ---------------------------------------------------------------------------


def _write_error_report(out_dir: Path, project_id: int, message: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
    ts = datetime.now(tz=timezone.utc).isoformat()
    error_payload = {"spike": "19E-5", "project_id": project_id, "error": message, "timestamp": ts}
    (out_dir / f"19E-5-spike-{date_str}.json").write_text(json.dumps(error_payload, indent=2))
    (out_dir / f"19E-5-spike-{date_str}.md").write_text(
        f"RESULT: ERROR\n\n# Spike 19E.5 — Error\n\n_{ts}_\n\n**Error:** {message}\n"
    )


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


def run_spike(project_id: int, out_dir: Path) -> int:
    session = SessionLocal()
    try:
        from apex.backend.models.project import Project

        project = session.query(Project).filter(Project.id == project_id).first()
        if not project:
            print(f"ERROR: project_id={project_id} not found in DB.", file=sys.stderr)
            return 2

        grounding, valid_ids = load_rule_library()
        specs, wcs, takeoffs = load_project_data(session, project_id)

        print(
            f"Loaded: {len(specs)} spec sections, {len(wcs)} work categories, "
            f"{len(takeoffs)} takeoff items, {len(grounding)} domain rules"
        )

        try:
            provider = get_llm_provider(agent_number=3)
        except Exception as exc:
            _write_error_report(out_dir, project_id, f"Provider init failed: {exc}")
            print(f"ERROR: could not init LLM provider: {exc}", file=sys.stderr)
            return 3

        user_prompt = build_user_prompt(specs, wcs, takeoffs, grounding)
        timestamp = datetime.now(tz=timezone.utc).isoformat()

        print(f"Calling {provider.provider_name}/{provider.model_name} ...")
        try:
            response = _run_async(_call_llm(provider, _SPIKE_SYSTEM_PROMPT, user_prompt))
        except Exception as exc:
            _write_error_report(out_dir, project_id, f"LLM call failed: {exc}")
            print(f"ERROR: LLM call failed: {exc}", file=sys.stderr)
            return 4

        # Approximate cost — Claude Sonnet pricing as of 2026-Q2
        input_cost = response.input_tokens * 3.0 / 1_000_000
        output_cost = response.output_tokens * 15.0 / 1_000_000
        token_counts = {
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
            "duration_ms": round(response.duration_ms, 1),
            "estimated_cost_usd": round(input_cost + output_cost, 6),
        }
        print(
            f"LLM complete: {response.input_tokens} in, {response.output_tokens} out, "
            f"~${token_counts['estimated_cost_usd']:.4f} USD, {response.duration_ms:.0f} ms"
        )

        findings = parse_llm_response(response.content)
        print(f"Parsed {len(findings)} gap findings")

        metrics, classified = compute_metrics(findings, valid_ids)
        passed, fail_reasons = evaluate_pass_fail(metrics)

        date_str = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")
        full_artifact = {
            "spike": "19E-5",
            "project_id": project_id,
            "timestamp": timestamp,
            "provider": response.provider,
            "model": response.model,
            "metrics": metrics,
            "pass_fail": "PASS" if passed else "FAIL",
            "fail_reasons": fail_reasons,
            "token_counts": token_counts,
            "classified_findings": classified,
            "raw_llm_response": response.content,
        }

        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / f"19E-5-spike-{date_str}.json"
        md_path = out_dir / f"19E-5-spike-{date_str}.md"

        json_path.write_text(json.dumps(full_artifact, indent=2, default=str))
        md_path.write_text(
            render_markdown(
                project_id=project_id,
                provider_name=response.provider,
                model_name=response.model,
                metrics=metrics,
                classified=classified,
                passed=passed,
                fail_reasons=fail_reasons,
                token_counts=token_counts,
                timestamp=timestamp,
            )
        )

        print(f"\n{'PASS' if passed else 'FAIL'} — {md_path}")
        print(f"JSON: {json_path}")
        return 0

    finally:
        session.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Spike 19E.5 — rule grounding validation")
    parser.add_argument("--project-id", required=True, type=int)
    parser.add_argument(
        "--out-dir",
        default="apex/docs/diagnostics",
        help="Output directory (default: apex/docs/diagnostics)",
    )
    args = parser.parse_args()
    sys.exit(run_spike(project_id=args.project_id, out_dir=Path(args.out_dir)))


if __name__ == "__main__":
    main()
