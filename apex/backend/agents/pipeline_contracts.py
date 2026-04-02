"""Pipeline data contracts — Pydantic models for each agent's validated output.

Each agent validates its return dict against these contracts before returning.
If validation fails, a ContractViolation is raised with the agent name and details.
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


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
    classification: Optional[str] = None
    pages: Optional[int] = None
    chars: Optional[int] = None
    error: Optional[str] = None
    winest_format: Optional[str] = None   # "est_native" | "xlsx_format1" | "xlsx_format2" | None


class Agent1Output(BaseModel):
    documents_processed: int = Field(ge=0)
    total_documents: int = Field(ge=0)
    results: list[Agent1DocResult] = []
    pipeline_mode: Optional[str] = None         # "spec" or "winest_import"
    winest_line_items: Optional[list] = None     # populated when pipeline_mode == "winest_import"


# ---------------------------------------------------------------------------
# Agent 2 — Spec Parser (v2: parameter extraction, no quantities)
# ---------------------------------------------------------------------------

class SpecParameter(BaseModel):
    """A single spec section with extracted material parameters."""
    division: str                                       # CSI division e.g. "03"
    section_number: str                                 # full CSI e.g. "03 30 00"
    section_title: str
    in_scope: bool = True
    material_specs: dict = Field(default_factory=dict)  # division-specific params
    quality_requirements: list[str] = []
    submittals_required: list[str] = []
    referenced_standards: list[str] = []                # ACI, ASTM, CRSI codes


class Agent2ParsedOutput(BaseModel):
    """Schema for LLM response across all chunks (merged)."""
    sections: list[SpecParameter] = []
    project_name: Optional[str] = None
    project_type: Optional[str] = None
    spec_date: Optional[str] = None


class Agent2DocResult(BaseModel):
    document_id: int
    filename: str
    sections_found: int = Field(ge=0)
    parse_method: str
    status: str
    error: Optional[str] = None


class Agent2Output(BaseModel):
    sections_parsed: int = Field(ge=0)
    documents_processed: int = Field(ge=0)
    parse_method: str
    results: list[Agent2DocResult] = []


# ---------------------------------------------------------------------------
# Agent 3 — Gap Analysis
# ---------------------------------------------------------------------------

class Agent3Output(BaseModel):
    total_gaps: int = Field(ge=0)
    critical_count: int = Field(ge=0)
    moderate_count: int = Field(ge=0)
    watch_count: int = Field(ge=0)
    overall_score: Optional[float] = None
    report_id: int
    sections_analyzed: int = Field(ge=0)
    spec_vs_takeoff_gaps: int = 0   # count of spec-vs-takeoff cross-reference gaps


# ---------------------------------------------------------------------------
# Agent 4 — Rate Recommendation Engine (v2)
# ---------------------------------------------------------------------------

# DEPRECATED — v1 only
class Agent4SectionResult_V1(BaseModel):
    section_id: Optional[int] = None   # None for gap-derived items with no matching section
    section_number: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    confidence: Optional[float] = None
    drawings: Optional[list] = None
    source: Optional[str] = None       # "specified" or "estimated" (LLM path only)
    error: Optional[str] = None


class TakeoffLineItem(BaseModel):
    """Single line item parsed from estimator's uploaded takeoff."""
    row_number: int
    wbs_area: Optional[str] = None
    activity: str
    quantity: Optional[float] = None
    unit: Optional[str] = None
    crew: Optional[str] = None
    production_rate: Optional[float] = None
    labor_cost_per_unit: Optional[float] = None
    material_cost_per_unit: Optional[float] = None
    csi_code: Optional[str] = None


class RateRecommendation(BaseModel):
    """Rate intelligence for a single takeoff line item."""
    line_item_row: int
    activity: str
    unit: Optional[str] = None
    crew: Optional[str] = None
    estimator_rate: Optional[float] = None
    historical_avg_rate: Optional[float] = None
    historical_min_rate: Optional[float] = None
    historical_max_rate: Optional[float] = None
    historical_spread: Optional[float] = None
    sample_count: int = 0
    confidence: str = "none"  # "high" (n>=10), "medium" (5-9), "low" (1-4), "none" (0)
    delta_pct: Optional[float] = None  # positive = optimistic vs history, negative = conservative
    flag: str = "NO_DATA"  # "OK" (<5%), "REVIEW" (5-20%), "UPDATE" (>20%), "NO_DATA"
    matching_projects: list[str] = []
    labor_cost_per_unit: Optional[float] = None
    material_cost_per_unit: Optional[float] = None
    wbs_area: Optional[str] = None


class Agent4Output(BaseModel):
    """Agent 4 v2 — Rate Recommendation Engine output."""
    takeoff_items_parsed: int = Field(ge=0)
    items_matched: int = Field(ge=0)
    items_unmatched: int = Field(ge=0)
    recommendations: list[RateRecommendation] = []
    flags_summary: dict = {}  # {"OK": N, "REVIEW": N, "UPDATE": N, "NO_DATA": N}
    parse_format: Optional[str] = None  # "26col", "21col", "csv", "manual"
    overall_optimism_score: Optional[float] = None  # avg delta across all matched items


# ---------------------------------------------------------------------------
# Agent 5 — Field Actuals Comparison Layer (v2)
# ---------------------------------------------------------------------------

# DEPRECATED — v1 only
class Agent5ItemResult_V1(BaseModel):
    takeoff_item_id: int
    csi_code: str
    quantity: Optional[float] = None
    rate: Optional[float] = None
    crew_type: Optional[str] = None
    labor_hours: Optional[float] = None
    labor_cost: Optional[float] = None
    confidence: Optional[float] = None
    match_confidence: Optional[str] = None
    matched_productivity_id: Optional[int] = None
    notes: Optional[str] = None
    error: Optional[str] = None
    source: Optional[str] = None


# DEPRECATED — v1 only
class Agent5Output_V1(BaseModel):
    estimates_created: int = Field(ge=0)
    total_labor_cost: float = Field(ge=0)
    total_labor_hours: float = Field(ge=0)
    items_processed: int = Field(ge=0)
    results: list[Agent5ItemResult_V1] = []
    labor_method: Optional[str] = None
    tokens_used: Optional[int] = None
    benchmark_coverage: Optional[float] = None


class FieldActualsComparison(BaseModel):
    """Three-way comparison for a single takeoff line item."""
    line_item_row: int
    activity: str
    unit: Optional[str] = None
    # The three rates
    estimator_rate: Optional[float] = None       # what this estimator entered
    estimating_avg_rate: Optional[float] = None   # what estimators historically enter (from PB)
    field_avg_rate: Optional[float] = None        # what crews actually produce
    # Comparison metrics
    field_sample_count: int = 0
    estimating_to_field_delta_pct: Optional[float] = None
    entered_to_field_delta_pct: Optional[float] = None
    calibration_factor: Optional[float] = None    # field_avg / estimating_avg
    calibration_direction: str = "no_data"        # "optimistic", "conservative", "aligned", "no_data"
    recommendation: str = ""                       # human-readable guidance
    field_projects: list[str] = []                 # which completed projects inform this


class Agent5Output(BaseModel):
    """Agent 5 v2 — Field Actuals Comparison output."""
    items_compared: int = Field(ge=0)
    items_with_field_data: int = Field(ge=0)
    items_without_field_data: int = Field(ge=0)
    comparisons: list[FieldActualsComparison] = []
    avg_calibration_factor: Optional[float] = None
    calibration_summary: dict = {}  # {"optimistic": N, "conservative": N, "aligned": N, "no_data": N}


# ---------------------------------------------------------------------------
# Agent 6 — Estimate Assembly
# ---------------------------------------------------------------------------

class Agent6Output(BaseModel):
    estimate_id: int
    version: int = Field(ge=1)
    total_direct_cost: float = Field(ge=0)
    total_bid_amount: float = Field(ge=0)
    line_items_count: int = Field(ge=0)
    divisions_covered: list[str] = []
    bid_bond_required: bool = False
    executive_summary: Optional[str] = None
    summary_method: Optional[str] = None   # "llm" or "template"
    summary_tokens_used: Optional[int] = None


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
        if isinstance(v, (int, float)):
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
    variance_method: Optional[str] = None   # "llm" or "statistical"
    variance_tokens_used: Optional[int] = None
    variance_items: list[Agent7VarianceItem] = []
    message: Optional[str] = None           # informational note (e.g. no actuals found)


# ---------------------------------------------------------------------------
# Validation helpers — called by each agent before returning
# ---------------------------------------------------------------------------

_CONTRACT_MAP: dict[int, type[BaseModel]] = {
    1: Agent1Output,
    2: Agent2Output,
    3: Agent3Output,
    4: Agent4Output,
    5: Agent5Output,
    6: Agent6Output,
    7: Agent7Output,
}

AGENT_NAMES = {
    1: "Document Ingestion Agent",
    2: "Spec Parser Agent",
    3: "Scope Gap Analysis Agent",
    4: "Rate Intelligence Agent",
    5: "Field Calibration Agent",
    6: "Estimate Assembly Agent",
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
