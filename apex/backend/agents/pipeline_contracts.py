"""Pipeline data contracts — Pydantic models for each agent's validated output.

Each agent validates its return dict against these contracts before returning.
If validation fails, a ContractViolation is raised with the agent name and details.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ContractViolation(Exception):
    """Raised when an agent's output fails contract validation."""

    def __init__(self, agent_name: str, detail: str):
        self.agent_name = agent_name
        self.detail = detail
        super().__init__(f"Contract violation in {agent_name}: {detail}")


# ---------------------------------------------------------------------------
# Agent 1 — Document Ingestion
# ---------------------------------------------------------------------------


class Agent1DocResult(BaseModel):
    document_id: int
    filename: str
    status: str
    classification: str | None = None
    pages: int | None = None
    chars: int | None = None
    error: str | None = None
    winest_format: str | None = None  # "est_native" | "xlsx_format1" | "xlsx_format2" | None


class Agent1Output(BaseModel):
    documents_processed: int = Field(ge=0)
    total_documents: int = Field(ge=0)
    results: list[Agent1DocResult] = []
    pipeline_mode: str | None = None  # "spec" or "winest_import"
    winest_line_items: list | None = None  # populated when pipeline_mode == "winest_import"


# ---------------------------------------------------------------------------
# Agent 2 — Spec Parser (v2: parameter extraction, no quantities)
# ---------------------------------------------------------------------------


class SpecParameter(BaseModel):
    """A single spec section with extracted material parameters."""

    division: str  # CSI division e.g. "03"
    section_number: str  # full CSI e.g. "03 30 00"
    section_title: str
    in_scope: bool = True
    material_specs: dict = Field(default_factory=dict)  # division-specific params
    quality_requirements: list[str] = []
    submittals_required: list[str] = []
    referenced_standards: list[str] = []  # ACI, ASTM, CRSI codes


class Agent2ParsedOutput(BaseModel):
    """Schema for LLM response across all chunks (merged)."""

    sections: list[SpecParameter] = []
    project_name: str | None = None
    project_type: str | None = None
    spec_date: str | None = None


class Agent2DocResult(BaseModel):
    document_id: int
    filename: str
    sections_found: int = Field(ge=0)
    parse_method: str
    status: str
    error: str | None = None


class AssemblyParameterEnrichment(BaseModel):
    """Agent 2 post-parse enrichment summary (Sprint 18.2.3).

    Produced by _enrich_division_03_parameters after SpecSection rows are
    committed. Failures are captured in warnings; extraction is per-section,
    so one section's failure never blocks others.
    """

    division_03_count: int = Field(ge=0)
    enriched: int = Field(ge=0)
    extraction_methods: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    duration_ms: float = Field(ge=0)


class SpecSectionDedupStats(BaseModel):
    """HF-21 (Sprint 18.3.0) — upsert counters for SpecSection writes.

    Surfaced in AgentRunLog.output_data so the /api/projects/{id}/agent-run-logs
    endpoint can show how many rows were inserted vs. replaced vs. skipped
    on a given parse run.
    """

    inserted: int = Field(ge=0)
    replaced: int = Field(ge=0)
    skipped: int = Field(ge=0)
    errors: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)


class Agent2Output(BaseModel):
    sections_parsed: int = Field(ge=0)
    documents_processed: int = Field(ge=0)
    parse_method: str
    results: list[Agent2DocResult] = []
    assembly_parameters: AssemblyParameterEnrichment | None = None  # Sprint 18.2.3
    dedup: SpecSectionDedupStats | None = None  # Sprint 18.3.0 HF-21


# ---------------------------------------------------------------------------
# Agent 2B — Work Scope Parser (Sprint 18.1)
# ---------------------------------------------------------------------------


class Agent2BOutput(BaseModel):
    """Agent 2B — Work Scope Parser output contract.

    Runs after Agent 2. Classifies every project document and parses docs
    identified as standalone_work_scope or embedded_work_scope into
    WorkCategory rows keyed on (project_id, wc_number).
    """

    project_id: int
    documents_examined: int = Field(ge=0)
    documents_parsed: int = Field(ge=0)
    work_categories_created: int = Field(ge=0)
    work_categories_updated: int = Field(ge=0)
    parse_methods: dict[str, int] = Field(default_factory=dict)
    classification_summary: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    duration_ms: float = Field(ge=0)


# ---------------------------------------------------------------------------
# Agent 3 — Gap Analysis
# ---------------------------------------------------------------------------


class Agent3Output(BaseModel):
    total_gaps: int = Field(ge=0)
    critical_count: int = Field(ge=0)
    moderate_count: int = Field(ge=0)
    watch_count: int = Field(ge=0)
    overall_score: float | None = None
    report_id: int
    sections_analyzed: int = Field(ge=0)
    spec_vs_takeoff_gaps: int = 0  # count of spec-vs-takeoff cross-reference gaps


# ---------------------------------------------------------------------------
# Agent 3.5 — Scope Gap Analysis (Sprint 18.3.1)
# ---------------------------------------------------------------------------


class GapFindingOut(BaseModel):
    """Serialized GapFinding row for API responses and inter-agent payloads.

    Consumes GapFinding ORM instances via from_attributes. Literal fields are
    the authoritative enum for finding_type / match_tier / source — the
    underlying DB columns are plain strings to match the Sprint 18 migration
    convention (no sa.Enum, no CHECK).
    """

    id: int
    project_id: int
    finding_type: Literal[
        "in_scope_not_estimated",
        "estimated_out_of_scope",
        "partial_coverage",
    ]
    work_category_id: int | None = None
    estimate_line_id: int | None = None
    spec_section_ref: str | None = None
    match_tier: Literal["csi_exact", "spec_section_fuzzy", "llm_semantic"]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    source: Literal["rule", "llm"]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------------------------
# Agent 4 — Rate Recommendation Engine (v2)
# ---------------------------------------------------------------------------


# DEPRECATED — v1 only
class Agent4SectionResult_V1(BaseModel):
    section_id: int | None = None  # None for gap-derived items with no matching section
    section_number: str
    quantity: float | None = None
    unit: str | None = None
    confidence: float | None = None
    drawings: list | None = None
    source: str | None = None  # "specified" or "estimated" (LLM path only)
    error: str | None = None


class TakeoffLineItem(BaseModel):
    """Single line item parsed from estimator's uploaded takeoff."""

    row_number: int
    wbs_area: str | None = None
    activity: str
    quantity: float | None = None
    unit: str | None = None
    crew: str | None = None
    production_rate: float | None = None
    labor_cost_per_unit: float | None = None
    material_cost_per_unit: float | None = None
    csi_code: str | None = None


class RateRecommendation(BaseModel):
    """Rate intelligence for a single takeoff line item."""

    line_item_row: int
    activity: str
    unit: str | None = None
    crew: str | None = None
    estimator_rate: float | None = None
    historical_avg_rate: float | None = None
    historical_min_rate: float | None = None
    historical_max_rate: float | None = None
    historical_spread: float | None = None
    sample_count: int = 0
    confidence: str = "none"  # "high" (n>=10), "medium" (5-9), "low" (1-4), "none" (0)
    delta_pct: float | None = None  # positive = optimistic vs history, negative = conservative
    flag: str = "NO_DATA"  # "OK" (<5%), "REVIEW" (5-20%), "UPDATE" (>20%), "NO_DATA", "NEEDS_RATE"
    matching_projects: list[str] = []
    labor_cost_per_unit: float | None = None
    material_cost_per_unit: float | None = None
    wbs_area: str | None = None


class Agent4Output(BaseModel):
    """Agent 4 v2 — Rate Recommendation Engine output."""

    takeoff_items_parsed: int = Field(ge=0)
    items_matched: int = Field(ge=0)
    items_unmatched: int = Field(ge=0)
    recommendations: list[RateRecommendation] = []
    flags_summary: dict = {}  # {"OK": N, "REVIEW": N, "UPDATE": N, "NO_DATA": N, "NEEDS_RATE": N}
    parse_format: str | None = None  # "26col", "21col", "csv", "manual"
    overall_optimism_score: float | None = None  # avg delta across all matched items


# ---------------------------------------------------------------------------
# Agent 5 — Field Actuals Comparison Layer (v2)
# ---------------------------------------------------------------------------


# DEPRECATED — v1 only
class Agent5ItemResult_V1(BaseModel):
    takeoff_item_id: int
    csi_code: str
    quantity: float | None = None
    rate: float | None = None
    crew_type: str | None = None
    labor_hours: float | None = None
    labor_cost: float | None = None
    confidence: float | None = None
    match_confidence: str | None = None
    matched_productivity_id: int | None = None
    notes: str | None = None
    error: str | None = None
    source: str | None = None


# DEPRECATED — v1 only
class Agent5Output_V1(BaseModel):
    estimates_created: int = Field(ge=0)
    total_labor_cost: float = Field(ge=0)
    total_labor_hours: float = Field(ge=0)
    items_processed: int = Field(ge=0)
    results: list[Agent5ItemResult_V1] = []
    labor_method: str | None = None
    tokens_used: int | None = None
    benchmark_coverage: float | None = None


class FieldActualsComparison(BaseModel):
    """Three-way comparison for a single takeoff line item."""

    line_item_row: int
    activity: str
    unit: str | None = None
    # The three rates
    estimator_rate: float | None = None  # what this estimator entered
    estimating_avg_rate: float | None = None  # what estimators historically enter (from PB)
    field_avg_rate: float | None = None  # what crews actually produce
    # Comparison metrics
    field_sample_count: int = 0
    estimating_to_field_delta_pct: float | None = None
    entered_to_field_delta_pct: float | None = None
    calibration_factor: float | None = None  # field_avg / estimating_avg
    calibration_direction: str = "no_data"  # "optimistic", "conservative", "aligned", "no_data"
    recommendation: str = ""  # human-readable guidance
    field_projects: list[str] = []  # which completed projects inform this


class Agent5Output(BaseModel):
    """Agent 5 v2 — Field Actuals Comparison output."""

    items_compared: int = Field(ge=0)
    items_with_field_data: int = Field(ge=0)
    items_without_field_data: int = Field(ge=0)
    comparisons: list[FieldActualsComparison] = []
    avg_calibration_factor: float | None = None
    calibration_summary: dict = {}  # {"optimistic": N, "conservative": N, "aligned": N, "no_data": N}


# ---------------------------------------------------------------------------
# Agent 6 — Intelligence Report Assembly (v2)
# ---------------------------------------------------------------------------


# DEPRECATED — v1 only
class Agent6Output_V1(BaseModel):
    estimate_id: int
    version: int = Field(ge=1)
    total_direct_cost: float = Field(ge=0)
    total_bid_amount: float = Field(ge=0)
    line_items_count: int = Field(ge=0)
    divisions_covered: list[str] = []
    bid_bond_required: bool = False
    executive_summary: str | None = None
    summary_method: str | None = None
    summary_tokens_used: int | None = None


class RateIntelligenceSummary(BaseModel):
    """Aggregated rate intelligence from Agent 4."""

    total_items: int = 0
    items_ok: int = 0  # <5% deviation
    items_review: int = 0  # 5-20% deviation
    items_update: int = 0  # >20% deviation
    items_no_match: int = 0  # no PB data
    items_needs_rate: int = 0  # PB match but no estimator rate (.est uploads)
    avg_deviation_pct: float | None = None
    optimism_score: float | None = None
    top_deviations: list[dict] = []  # top 5 items by absolute deviation


class FieldCalibrationSummary(BaseModel):
    """Aggregated field calibration from Agent 5."""

    items_with_field_data: int = 0
    items_without_field_data: int = 0
    avg_calibration_factor: float | None = None
    optimistic_count: int = 0
    conservative_count: int = 0
    aligned_count: int = 0
    critical_alerts: list[dict] = []  # items with cal_factor < 0.80 or > 1.20


class ScopeRiskSummary(BaseModel):
    """Aggregated scope risk from Agent 3."""

    total_gaps: int = 0
    critical_gaps: int = 0
    watch_gaps: int = 0
    spec_vs_takeoff_gaps: int = 0
    missing_divisions: list[str] = []
    top_risks: list[dict] = []  # top 5 gaps by severity

    # Sprint 18.3.3 additions — GapFinding rollups from Agent 3.5
    in_scope_not_estimated: int = 0
    estimated_out_of_scope: int = 0
    partial_coverage: int = 0
    severity_error: int = 0
    severity_warning: int = 0
    severity_info: int = 0
    top_gap_findings: list[dict] = []  # top 5 by severity then confidence


class ComparableProjectSummary(BaseModel):
    """Comparable projects from Bid Intelligence."""

    comparable_count: int = 0
    avg_bid_amount: float | None = None
    avg_cost_per_cy: float | None = None
    avg_production_mh_per_cy: float | None = None
    company_hit_rate: float | None = None
    comparables: list[dict] = []  # top 5 most similar projects


class IntelligenceReport(BaseModel):
    """Agent 6 v2 — full intelligence report output."""

    project_id: int
    report_version: int = 1
    generated_at: str = ""

    # Estimator's numbers (from takeoff)
    takeoff_item_count: int = 0
    takeoff_total_labor: float | None = None
    takeoff_total_material: float | None = None

    # Intelligence sections
    rate_intelligence: RateIntelligenceSummary = RateIntelligenceSummary()
    field_calibration: FieldCalibrationSummary = FieldCalibrationSummary()
    scope_risk: ScopeRiskSummary = ScopeRiskSummary()
    comparable_projects: ComparableProjectSummary = ComparableProjectSummary()

    # Spec intelligence
    spec_sections_parsed: int = 0
    material_specs_extracted: int = 0

    # Overall assessment
    overall_risk_level: str = "unknown"  # "low", "moderate", "high", "critical"
    confidence_score: float | None = None  # 0-100 based on data coverage
    executive_narrative: str = ""  # LLM-generated or template
    narrative_method: str = "template"  # "llm" or "template"

    # PB coverage
    pb_projects_loaded: int = 0
    pb_activities_available: int = 0

    # Token tracking
    narrative_tokens_used: int = 0


class Agent6Output(BaseModel):
    """Agent 6 v2 — Intelligence Report output for pipeline contract."""

    report_id: int = Field(ge=0)
    report_version: int = Field(ge=1)
    overall_risk_level: str = ""
    confidence_score: float | None = None
    rate_items_flagged: int = Field(ge=0, default=0)
    scope_gaps_found: int = Field(ge=0, default=0)
    field_calibration_alerts: int = Field(ge=0, default=0)
    comparable_projects_found: int = Field(ge=0, default=0)
    narrative_method: str = "template"
    narrative_tokens_used: int = Field(ge=0, default=0)


# ---------------------------------------------------------------------------
# Agent 7 — IMPROVE Feedback
# ---------------------------------------------------------------------------


class Agent7VarianceItem(BaseModel):
    """Single line-item variance as returned by the LLM (Pydantic-validated)."""

    line_item: str
    estimated_rate: float
    historical_actual_rate: float
    variance_pct: float
    likely_cause: str
    recommendation: str
    confidence: Literal["high", "medium", "low"]

    @field_validator("confidence", mode="before")
    @classmethod
    def _norm_confidence(cls, v: str) -> str:
        return str(v).lower().strip()

    @field_validator("estimated_rate", "historical_actual_rate", "variance_pct", mode="before")
    @classmethod
    def _to_float(cls, v) -> float:
        if isinstance(v, int | float):
            return float(v)
        return float(str(v).replace(",", "").strip())


class Agent7Output(BaseModel):
    actuals_processed: int = Field(ge=0)
    variances_calculated: int = Field(ge=0)
    productivity_updates: int = Field(ge=0)
    accuracy_score: float
    total_estimated_cost: float
    total_actual_cost: float
    overall_variance_pct: float
    variance_method: str | None = None  # "llm" or "statistical"
    variance_tokens_used: int | None = None
    variance_items: list[Agent7VarianceItem] = []
    message: str | None = None  # informational note (e.g. no actuals found)


class Agent35Output(BaseModel):
    """Agent 3.5 — Scope Matcher (stored as agent_number=35, displayed as 3.5)."""

    status: str  # "completed" | "noop"
    project_id: int
    findings_created: int = Field(ge=0)
    in_scope_not_estimated_count: int = Field(ge=0)
    estimated_out_of_scope_count: int = Field(ge=0)
    partial_coverage_count: int = Field(ge=0)
    error_count: int = Field(ge=0)


# ---------------------------------------------------------------------------
# Validation helpers — called by each agent before returning
# ---------------------------------------------------------------------------

_CONTRACT_MAP: dict[int, type[BaseModel]] = {
    1: Agent1Output,
    2: Agent2Output,
    3: Agent3Output,
    35: Agent35Output,
    4: Agent4Output,
    5: Agent5Output,
    6: Agent6Output,
    7: Agent7Output,
}

AGENT_NAMES = {
    1: "Document Ingestion Agent",
    2: "Spec Parser Agent",
    3: "Scope Analysis Agent",
    35: "Scope Matcher Agent",  # displayed as "3.5"
    4: "Rate Intelligence Agent",
    5: "Field Calibration Agent",
    6: "Intelligence Report Agent",
    7: "IMPROVE Feedback Agent",
}


def validate_agent_output(agent_number: int, output: dict) -> dict:
    """Validate *output* dict against the contract for *agent_number*.

    Returns the original dict unchanged if valid.
    Raises ContractViolation if validation fails.
    """
    contract_cls = _CONTRACT_MAP.get(agent_number)
    if contract_cls is None:
        return output

    agent_name = AGENT_NAMES.get(agent_number, f"Agent {agent_number}")
    try:
        contract_cls.model_validate(output)
    except Exception as exc:
        raise ContractViolation(agent_name, str(exc)) from exc

    return output
