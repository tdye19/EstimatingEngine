"""Rule fact validator for Agent 3 gap findings (Spec 19E.6.3).

Pure function — no side effects, no logging, no DB writes.
The orchestrator (Agent 3) handles telemetry from the returned ValidationResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apex.backend.agents.pipeline_contracts import GapFinding
from apex.backend.agents.tools.domain_gap_rules import get_canonical_facts


@dataclass
class ValidationResult:
    findings: list[GapFinding]
    valid_cite_count: int
    stripped_cite_count: int
    no_cite_count: int
    stripped_rule_ids: list[str] = field(default_factory=list)
    valid_rule_ids: list[str] = field(default_factory=list)

    def to_telemetry_dict(self) -> dict:
        return {
            "total_findings": self.valid_cite_count + self.stripped_cite_count + self.no_cite_count,
            "valid_cite_count": self.valid_cite_count,
            "stripped_cite_count": self.stripped_cite_count,
            "no_cite_count": self.no_cite_count,
            "valid_rule_ids": self.valid_rule_ids,
            "stripped_rule_ids": self.stripped_rule_ids,
        }


def validate_and_attach_rule_facts(findings: list[GapFinding]) -> ValidationResult:
    """
    For each finding:
      - If rule_id is None: pass through unchanged.
      - If rule_id is valid: attach all five rule_* canonical fields.
      - If rule_id is invalid (not in library): strip rule_id (set to None);
        do NOT attach canonical fields. Record in stripped_rule_ids for telemetry.
    """
    processed: list[GapFinding] = []
    valid_cite_count = 0
    stripped_cite_count = 0
    no_cite_count = 0
    stripped_rule_ids: list[str] = []
    valid_rule_ids: list[str] = []

    for finding in findings:
        if finding.rule_id is None:
            no_cite_count += 1
            processed.append(finding)
            continue

        facts = get_canonical_facts(finding.rule_id)
        if facts is None:
            stripped_rule_ids.append(finding.rule_id)
            stripped_cite_count += 1
            processed.append(finding.model_copy(update={"rule_id": None}))
        else:
            valid_cite_count += 1
            valid_rule_ids.append(finding.rule_id)
            processed.append(
                finding.model_copy(
                    update={
                        "rule_standard_ref": facts["standard_ref"],
                        "rule_severity": facts["severity"],
                        "rule_cost_range_text": facts["cost_range_text"],
                        "rule_typical_responsibility": facts["typical_responsibility"],
                        "rule_rfi_template": facts["rfi_template"],
                    }
                )
            )

    return ValidationResult(
        findings=processed,
        valid_cite_count=valid_cite_count,
        stripped_cite_count=stripped_cite_count,
        no_cite_count=no_cite_count,
        stripped_rule_ids=stripped_rule_ids,
        valid_rule_ids=valid_rule_ids,
    )
