"""Reusable evaluation harness for domain gap rules — Sprint 17.2-V / Phase 0 closeout.

Produces two output files per run:
  1. domain_rules_worksheet_project_{id}_{YYYYMMDD}.md  — manual TP/FP labeling sheet
  2. domain_rules_coverage_project_{id}_{YYYYMMDD}.md   — precision/recall/coverage stats

Usage:
    python -m apex.backend.scripts.evaluate_domain_rules --project-id 20
    python -m apex.backend.scripts.evaluate_domain_rules --project-id 20 --output-dir /tmp/out
    python -m apex.backend.scripts.evaluate_domain_rules --project-id 20 --no-include-empty-rules
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("apex.scripts.evaluate_domain_rules")

# ---------------------------------------------------------------------------
# Pure functions — no DB imports, unit-testable in isolation
# ---------------------------------------------------------------------------

RULE_ID_RE = re.compile(r"\[Rule ID:\s*([A-Z]+-\d+)\]")


def extract_rule_id(description: str | None) -> str | None:
    """Parse rule ID from a GapReportItem description field.

    Returns the matched rule ID string (e.g. "CGR-001") or None if absent.
    Pattern requires uppercase prefix, dash, and digits — "bogus" will not match.
    """
    if not description:
        return None
    m = RULE_ID_RE.search(description)
    return m.group(1) if m else None


def filter_domain_rule_findings(items: list) -> list:
    """Return only items whose description contains the '[Rule ID:' sentinel."""
    return [i for i in items if i.description and "[Rule ID:" in i.description]


def compute_coverage_stats(findings_by_rule: dict, all_rules: list) -> dict:
    """Compute coverage stats from a findings dict and the full rule registry.

    Args:
        findings_by_rule: {rule_id: [list of findings]}
        all_rules: list of DomainGapRule objects from ALL_DOMAIN_RULES

    Returns dict with total_rules, rules_fired, rules_not_fired, total_findings,
    findings_per_rule_distribution.
    """
    total_rules = len(all_rules)
    rules_fired = sum(1 for rule in all_rules if findings_by_rule.get(rule.id))
    total_findings = sum(len(v) for v in findings_by_rule.values())
    distribution = {rule_id: len(findings) for rule_id, findings in findings_by_rule.items()}
    return {
        "total_rules": total_rules,
        "rules_fired": rules_fired,
        "rules_not_fired": total_rules - rules_fired,
        "total_findings": total_findings,
        "findings_per_rule_distribution": distribution,
    }


def _strip_rule_id_tag(description: str) -> str:
    return RULE_ID_RE.sub("", description).strip()


def _severity_mix(items: list) -> str:
    counts = Counter(i.severity for i in items)
    return ", ".join(f"{v} {k}" for k, v in sorted(counts.items()))


# ---------------------------------------------------------------------------
# Report builders — pure string assembly, no DB
# ---------------------------------------------------------------------------

def build_worksheet(
    project,
    findings_by_rule: dict,
    all_rules: list,
    include_empty_rules: bool,
    spec_source: str,
    generated_at: datetime,
) -> str:
    total_findings = sum(len(v) for v in findings_by_rule.values())
    lines = [
        "# Domain Rules Validation Worksheet",
        f"**Project:** {project.name} (id: {project.id})",
        f"**Spec source:** {spec_source}",
        f"**Generated:** {generated_at.isoformat()}",
        f"**Total findings to label:** {total_findings}",
        "",
        "## Instructions",
        "",
        "For each finding below, fill in the LABEL column with one of:",
        "- TP (true positive) — the spec genuinely has this gap",
        "- FP (false positive) — the rule misfired; the gap does not exist",
        "- UNCERTAIN — cannot determine from spec alone",
        "",
        "Fill in NOTES with a one-sentence rationale or spec section reference.",
        "",
        "## Findings by Rule",
    ]

    for rule in all_rules:
        items = findings_by_rule.get(rule.id, [])

        if not items and not include_empty_rules:
            continue

        lines.append("")
        lines.append(f"### {rule.id} — {rule.name}")

        if items:
            lines.append(f"_Fired {len(items)} time{'s' if len(items) != 1 else ''}._")
            lines.append("")
            lines.append("| # | Division | Section | Title | Severity | LABEL | NOTES |")
            lines.append("|---|----------|---------|-------|----------|-------|-------|")
            for idx, item in enumerate(items, 1):
                div = item.division_number or ""
                sec = item.section_number or ""
                title = (item.title or "")[:80].replace("|", "\\|")
                sev = item.severity or ""
                lines.append(f"| {idx} | {div} | {sec} | {title} | {sev} | _____ | _____ |")
            lines.append("")
            # Excerpt from first finding with rule-id tag stripped
            if items[0].description:
                excerpt = _strip_rule_id_tag(items[0].description)[:200].replace("\n", " ")
                lines.append(f"_{excerpt}_")
        else:
            lines.append("_Did not fire on this project._")

    lines += [
        "",
        "## Manual Labeling Summary (fill in after labeling)",
        "",
        "- True positives: _____",
        "- False positives: _____",
        "- Uncertain: _____",
        "- Precision = TP / (TP + FP) = _____",
    ]
    return "\n".join(lines)


def build_coverage_report(
    project,
    findings_by_rule: dict,
    all_rules: list,
    unknown_findings: list,
    stats: dict,
    generated_at: datetime,
) -> str:
    total = stats["total_rules"]
    fired = stats["rules_fired"]
    pct = round(100 * fired / total) if total else 0

    lines = [
        "# Domain Rules Coverage Report",
        f"**Project:** {project.name} (id: {project.id})",
        f"**Generated:** {generated_at.isoformat()}",
        "",
        "## Summary",
        "",
        f"- Total rules in registry: {total}",
        f"- Rules that fired on this project: {fired} ({pct}%)",
        f"- Rules that did not fire: {stats['rules_not_fired']}",
        f"- Total findings produced: {stats['total_findings']}",
        "",
        "## Rules That Fired",
        "",
        "| Rule ID | Findings | Severity Mix |",
        "|---------|----------|--------------|",
    ]

    for rule in all_rules:
        items = findings_by_rule.get(rule.id, [])
        if items:
            mix = _severity_mix(items)
            lines.append(f"| {rule.id} | {len(items)} | {mix} |")

    lines += [
        "",
        "## Rules That Did Not Fire",
        "",
        "| Rule ID | Description |",
        "|---------|-------------|",
    ]
    for rule in all_rules:
        if not findings_by_rule.get(rule.id):
            desc = (rule.description or "")[:100].replace("|", "\\|").replace("\n", " ")
            lines.append(f"| {rule.id} | {desc} |")

    lines += [
        "",
        "## Findings That Could Not Be Parsed",
        "",
    ]
    if unknown_findings:
        lines.append("| GapReportItem ID | Rule ID in Description | Note |")
        lines.append("|------------------|------------------------|------|")
        for item_id, raw_id in unknown_findings:
            lines.append(
                f"| {item_id} | {raw_id} | "
                "Rule ID not in registry — possible rename or typo |"
            )
    else:
        lines.append("_(None — all [Rule ID:] tags matched known rules.)_")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate domain gap rules against a project's gap report."
    )
    parser.add_argument("--project-id", type=int, required=True, help="Project ID to evaluate")
    parser.add_argument(
        "--output-dir",
        default="apex/docs/validation",
        help="Output directory for worksheet and coverage report (default: apex/docs/validation)",
    )
    parser.add_argument(
        "--include-empty-rules",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Include rules that did not fire in the worksheet (default: True)",
    )
    parser.add_argument(
        "--db-url",
        default=None,
        help="Database URL override (default: DATABASE_URL env var)",
    )
    args = parser.parse_args(argv)

    # Must set DATABASE_URL before the ORM engine is initialised on first import
    if args.db_url:
        import os
        os.environ["DATABASE_URL"] = args.db_url

    # Deferred imports — after possible DATABASE_URL override
    from apex.backend.agents.tools.domain_gap_rules import ALL_DOMAIN_RULES
    from apex.backend.db.database import SessionLocal
    from apex.backend.models.gap_report import GapReport, GapReportItem
    from apex.backend.models.project import Project

    known_rule_ids = {rule.id for rule in ALL_DOMAIN_RULES}

    db = SessionLocal()
    try:
        project = db.query(Project).filter(Project.id == args.project_id).first()
        if not project:
            logger.error("Project %d not found. Check the project ID.", args.project_id)
            return 1

        report = (
            db.query(GapReport)
            .filter(GapReport.project_id == args.project_id)
            .order_by(GapReport.created_at.desc())
            .first()
        )
        if not report:
            logger.error(
                "No GapReport found for project %d. "
                "Run the full pipeline on this project first, then re-run this harness.",
                args.project_id,
            )
            return 1

        all_items = (
            db.query(GapReportItem).filter(GapReportItem.gap_report_id == report.id).all()
        )
        domain_items = filter_domain_rule_findings(all_items)

        # Resolve spec source from first uploaded document if available
        spec_source = "unknown"
        try:
            from apex.backend.models.document import Document
            doc = (
                db.query(Document)
                .filter(Document.project_id == args.project_id)
                .order_by(Document.created_at)
                .first()
            )
            if doc:
                spec_source = doc.filename
        except Exception:
            pass

        # Group findings by rule_id; accumulate unknowns for the coverage report
        findings_by_rule: dict = defaultdict(list)
        unknown_findings: list = []  # [(item.id, raw_rule_id)]

        for item in domain_items:
            rule_id = extract_rule_id(item.description)
            if rule_id is None:
                logger.warning(
                    "GapReportItem %d has [Rule ID:] tag but regex did not match: %r",
                    item.id,
                    (item.description or "")[:120],
                )
                continue
            if rule_id not in known_rule_ids:
                logger.warning(
                    "GapReportItem %d references unknown rule %r — not in ALL_DOMAIN_RULES",
                    item.id,
                    rule_id,
                )
                unknown_findings.append((item.id, rule_id))
                continue
            findings_by_rule[rule_id].append(item)

        stats = compute_coverage_stats(dict(findings_by_rule), ALL_DOMAIN_RULES)
        generated_at = datetime.now(timezone.utc)
        date_stamp = generated_at.strftime("%Y%m%d")

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        worksheet_path = (
            output_dir / f"domain_rules_worksheet_project_{args.project_id}_{date_stamp}.md"
        )
        coverage_path = (
            output_dir / f"domain_rules_coverage_project_{args.project_id}_{date_stamp}.md"
        )

        worksheet_path.write_text(
            build_worksheet(
                project=project,
                findings_by_rule=dict(findings_by_rule),
                all_rules=ALL_DOMAIN_RULES,
                include_empty_rules=args.include_empty_rules,
                spec_source=spec_source,
                generated_at=generated_at,
            ),
            encoding="utf-8",
        )
        coverage_path.write_text(
            build_coverage_report(
                project=project,
                findings_by_rule=dict(findings_by_rule),
                all_rules=ALL_DOMAIN_RULES,
                unknown_findings=unknown_findings,
                stats=stats,
                generated_at=generated_at,
            ),
            encoding="utf-8",
        )

    finally:
        db.close()

    print(
        f"Wrote worksheet to {worksheet_path} and coverage report to {coverage_path}. "
        f"Rules fired: {stats['rules_fired']}/{stats['total_rules']}. "
        f"Total findings: {stats['total_findings']}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
