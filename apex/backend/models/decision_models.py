"""Decision system domain models — coexist with existing agent pipeline models.

Architecture reference: apex/apex_decision_system_architecture.md
Every section annotation (§N.N) maps to that document.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(UTC)


# ─── Comparable projects (historical memory) ────────────────────────────────


class ComparableProject(Base):
    """Historical project used for context-aware benchmarking. §9.8"""

    __tablename__ = "comparable_projects"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    client = Column(String(255), nullable=True)
    location = Column(String(500), nullable=True)
    # Date range — both required for recency weighting
    start_date = Column(Date, nullable=True)  # §9.8
    end_date = Column(Date, nullable=True)  # §9.8
    completed_date = Column(DateTime, nullable=True)
    final_contract_value = Column(Float, nullable=True)
    # Context fields — mandatory for context-aware filtering (§10)
    project_type = Column(String(100), nullable=True)
    market_sector = Column(String(100), nullable=True)
    region = Column(String(100), nullable=True)
    delivery_method = Column(String(50), nullable=True)
    contract_type = Column(String(50), nullable=True)
    size_sf = Column(Float, nullable=True)
    scope_types = Column(Text, nullable=True)  # JSON array
    complexity_level = Column(String(20), nullable=True)
    schedule_pressure = Column(String(20), nullable=True)
    data_quality_score = Column(Float, default=0.5)
    source_system = Column(String(100), nullable=True)

    rate_observations = relationship(
        "HistoricalRateObservation",
        back_populates="comparable_project",
        cascade="all, delete-orphan",
    )
    field_actuals = relationship(
        "FieldActual",
        back_populates="comparable_project",
        cascade="all, delete-orphan",
    )


class HistoricalRateObservation(Base):
    """Activity-level rate observation from a comparable project. §9.9"""

    __tablename__ = "historical_rate_observations"

    id = Column(String(36), primary_key=True, default=_uuid)
    comparable_project_id = Column(String(36), ForeignKey("comparable_projects.id"), nullable=False)
    canonical_activity_id = Column(String(36), ForeignKey("canonical_activities.id"), nullable=True)
    raw_activity_name = Column(String(500), nullable=False)
    division_code = Column(String(20), nullable=True)
    quantity = Column(Float, nullable=True)
    unit = Column(String(20), nullable=True)
    # Rates per unit — separate from totals so benchmarking can compare apples-to-apples
    unit_cost = Column(Float, nullable=True)  # total unit cost
    labor_rate = Column(Float, nullable=True)  # §9.9 labor per unit
    material_rate = Column(Float, nullable=True)  # §9.9 material per unit
    equipment_rate = Column(Float, nullable=True)  # §9.9 equipment per unit
    subcontract_rate = Column(Float, nullable=True)  # §9.9 sub per unit
    # Totals (kept for import compatibility)
    total_cost = Column(Float, nullable=True)
    labor_cost = Column(Float, nullable=True)
    material_cost = Column(Float, nullable=True)
    equipment_cost = Column(Float, nullable=True)
    sub_cost = Column(Float, nullable=True)
    production_rate = Column(Float, nullable=True)
    production_rate_unit = Column(String(50), nullable=True)
    # Quality and recency signals
    observation_date = Column(Date, nullable=True)  # §9.9 — for recency decay
    recency_weight = Column(Float, default=1.0)  # §9.9 — computed from observation_date
    data_quality_score = Column(Float, default=0.5)
    quality_weight = Column(Float, default=1.0)  # §9.9 — separate from data_quality_score
    source_system = Column(String(100), nullable=True)  # §9.9 — winest | pb | manual
    source_row = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_now)

    comparable_project = relationship("ComparableProject", back_populates="rate_observations")


# ─── Canonical ontology ──────────────────────────────────────────────────────


class CanonicalActivity(Base):
    """Controlled vocabulary entry for estimating work items. §11"""

    __tablename__ = "canonical_activities"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), unique=True, nullable=False)
    division_code = Column(String(20), nullable=False)
    division_name = Column(String(255), nullable=True)
    expected_unit = Column(String(20), nullable=True)
    scope_family = Column(String(100), nullable=True)
    typical_cost_bucket = Column(String(50), nullable=True)
    common_dependencies = Column(Text, nullable=True)  # JSON array
    notes = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)

    aliases = relationship(
        "ActivityAlias",
        back_populates="canonical_activity",
        cascade="all, delete-orphan",
    )


class ActivityAlias(Base):
    """Known alternative names/spellings for a canonical activity. §11"""

    __tablename__ = "activity_aliases"

    id = Column(String(36), primary_key=True, default=_uuid)
    canonical_activity_id = Column(String(36), ForeignKey("canonical_activities.id"), nullable=False)
    alias = Column(String(500), nullable=False)
    source = Column(String(50), nullable=True)  # winest | pb | manual | llm
    confidence = Column(Float, default=1.0)

    canonical_activity = relationship("CanonicalActivity", back_populates="aliases")


# ─── Versioned estimate runs ─────────────────────────────────────────────────


class EstimateRun(Base):
    """One full analysis pass for a project. §9.2"""

    __tablename__ = "estimate_runs"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    version_number = Column(Integer, default=1, nullable=False)
    run_status = Column(String(30), default="in_progress")
    # in_progress | scope_extracted | priced | commercial | complete | error
    started_at = Column(DateTime, default=_now)
    completed_at = Column(DateTime, nullable=True)
    created_by = Column(String(100), nullable=True)
    # Snapshot of the project context at time of run — critical for audit (§3.3)
    context_snapshot = Column(Text, nullable=True)  # JSON
    # Source package — which document upload triggered this run
    source_package_id = Column(Integer, ForeignKey("documents.id"), nullable=True)  # §9.2
    # Cost totals — populated by Pricing + Commercial engines
    total_direct_cost = Column(Float, nullable=True)
    total_indirect_cost = Column(Float, nullable=True)
    total_risk = Column(Float, nullable=True)
    total_escalation = Column(Float, nullable=True)
    total_fee = Column(Float, nullable=True)
    final_bid_value = Column(Float, nullable=True)

    scope_items = relationship("ScopeItem", back_populates="estimate_run", cascade="all, delete-orphan")
    quantity_items = relationship("QuantityItem", back_populates="estimate_run", cascade="all, delete-orphan")
    benchmark_results = relationship("BenchmarkResult", back_populates="estimate_run", cascade="all, delete-orphan")
    estimate_lines = relationship("EstimateLine", back_populates="estimate_run", cascade="all, delete-orphan")
    risk_items = relationship("RiskItem", back_populates="estimate_run", cascade="all, delete-orphan")
    escalation_inputs = relationship("EscalationInput", back_populates="estimate_run", cascade="all, delete-orphan")
    cost_breakdown_buckets = relationship(
        "CostBreakdownBucket", back_populates="estimate_run", cascade="all, delete-orphan"
    )
    schedule_scenarios = relationship("ScheduleScenario", back_populates="estimate_run", cascade="all, delete-orphan")
    overrides = relationship("EstimatorOverride", back_populates="estimate_run", cascade="all, delete-orphan")
    project = relationship("Project", back_populates="estimate_runs")


# ─── Source traceability ─────────────────────────────────────────────────────


class SourceReference(Base):
    """Page/section-level pointer back to a source document. §9.4 / §3.3"""

    __tablename__ = "source_references"

    id = Column(String(36), primary_key=True, default=_uuid)
    source_document_id = Column(Integer, ForeignKey("documents.id"), nullable=False)
    page_number = Column(Integer, nullable=True)
    section_label = Column(String(255), nullable=True)
    snippet_text = Column(Text, nullable=True)
    bounding_box_json = Column(Text, nullable=True)  # JSON {x,y,w,h} for drawings
    reference_type = Column(String(50), nullable=True)
    # spec_section | drawing_note | addendum | quantity_table | exclusion


# ─── Scope items ─────────────────────────────────────────────────────────────


class ScopeItem(Base):
    """Canonical work item extracted from project scope. §9.5"""

    __tablename__ = "scope_items"

    SCOPE_STATUSES = (
        "included_explicit",
        "included_implied",
        "likely_missing",
        "excluded",
        "review_required",
        "not_applicable",
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    estimate_run_id = Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)
    canonical_activity_id = Column(String(36), ForeignKey("canonical_activities.id"), nullable=True)
    canonical_name = Column(String(255), nullable=False)
    division_code = Column(String(20), nullable=True)
    work_package = Column(String(100), nullable=True)
    activity_family = Column(String(100), nullable=True)
    scope_status = Column(String(30), default="review_required")
    inclusion_confidence = Column(Float, default=0.5)
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)

    estimate_run = relationship("EstimateRun", back_populates="scope_items")
    evidence = relationship("ScopeItemEvidence", back_populates="scope_item", cascade="all, delete-orphan")
    quantity_items = relationship("QuantityItem", back_populates="scope_item", cascade="all, delete-orphan")


class ScopeItemEvidence(Base):
    """Links a ScopeItem to its source references. §9.6"""

    __tablename__ = "scope_item_evidence"

    id = Column(String(36), primary_key=True, default=_uuid)
    scope_item_id = Column(String(36), ForeignKey("scope_items.id"), nullable=False)
    source_reference_id = Column(String(36), ForeignKey("source_references.id"), nullable=True)
    evidence_type = Column(String(30), nullable=True)
    # explicit | implied | dependency_rule | checklist
    confidence = Column(Float, default=1.0)
    note = Column(Text, nullable=True)

    scope_item = relationship("ScopeItem", back_populates="evidence")


# ─── Quantities ──────────────────────────────────────────────────────────────


class QuantityItem(Base):
    """Estimator-provided or takeoff-parsed quantity for a scope item. §9.7"""

    __tablename__ = "quantity_items"

    id = Column(String(36), primary_key=True, default=_uuid)
    estimate_run_id = Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)
    scope_item_id = Column(String(36), ForeignKey("scope_items.id"), nullable=True)
    quantity_value = Column(Float, nullable=True)
    unit = Column(String(20), nullable=True)
    source = Column(String(50), nullable=True)
    # takeoff_import | manual | parsed_drawing | estimated
    source_reference_id = Column(String(36), ForeignKey("source_references.id"), nullable=True)
    quantity_confidence = Column(Float, default=0.5)
    missing_flag = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now)

    estimate_run = relationship("EstimateRun", back_populates="quantity_items")
    scope_item = relationship("ScopeItem", back_populates="quantity_items")


# ─── Benchmarking ────────────────────────────────────────────────────────────


class BenchmarkResult(Base):
    """Computed percentile distribution for one scope item. §9.10 / §12.4"""

    __tablename__ = "benchmark_results"

    id = Column(String(36), primary_key=True, default=_uuid)
    estimate_run_id = Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)
    scope_item_id = Column(String(36), ForeignKey("scope_items.id"), nullable=True)
    canonical_activity_id = Column(String(36), ForeignKey("canonical_activities.id"), nullable=True)
    # Snapshot of context filters used — required for audit (§3.3)
    comparable_filter_json = Column(Text, nullable=True)
    sample_size = Column(Integer, default=0)
    p10 = Column(Float, nullable=True)  # §12.4 — required
    p25 = Column(Float, nullable=True)
    p50 = Column(Float, nullable=True)
    p75 = Column(Float, nullable=True)
    p90 = Column(Float, nullable=True)
    mean = Column(Float, nullable=True)
    std_dev = Column(Float, nullable=True)
    context_similarity_score = Column(Float, nullable=True)
    benchmark_confidence = Column(Float, nullable=True)
    confidence_label = Column(String(20), nullable=True)  # high | medium | low | very_low
    computed_at = Column(DateTime, default=_now)

    estimate_run = relationship("EstimateRun", back_populates="benchmark_results")


# ─── Estimate lines ──────────────────────────────────────────────────────────


class EstimateLine(Base):
    """Reviewable estimate line item. §9.11"""

    __tablename__ = "decision_estimate_lines"

    id = Column(String(36), primary_key=True, default=_uuid)
    # Versioned run — not raw project FK (§9.11)
    estimate_run_id = Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)
    scope_item_id = Column(String(36), ForeignKey("scope_items.id"), nullable=True)
    benchmark_result_id = Column(String(36), ForeignKey("benchmark_results.id"), nullable=True)
    description = Column(String(500), nullable=False)
    division_code = Column(String(20), nullable=True)
    quantity = Column(Float, nullable=False)
    unit = Column(String(20), nullable=True)
    # System recommendation
    recommended_unit_cost = Column(Float, nullable=True)
    recommended_total_cost = Column(Float, nullable=True)
    # Estimator final values — after override (§9.11)
    estimator_unit_cost = Column(Float, nullable=True)
    estimator_total_cost = Column(Float, nullable=True)
    # Pricing provenance
    pricing_basis = Column(String(50), default="no_data")
    # contextual_benchmark_p50 | contextual_benchmark_p25 | assembly | manual | allowance | no_data
    # Inline benchmark snapshot — denormalized from BenchmarkResult for fast UI rendering
    benchmark_sample_size = Column(Integer, nullable=True)
    benchmark_p25 = Column(Float, nullable=True)
    benchmark_p50 = Column(Float, nullable=True)
    benchmark_p75 = Column(Float, nullable=True)
    benchmark_p90 = Column(Float, nullable=True)
    benchmark_mean = Column(Float, nullable=True)
    benchmark_std_dev = Column(Float, nullable=True)
    benchmark_context_similarity = Column(Float, nullable=True)
    # Confidence
    confidence_score = Column(Float, nullable=True)
    confidence_level = Column(String(20), default="very_low")
    # Review flags
    line_status = Column(String(30), default="needs_review")
    # needs_review | accepted | overridden | excluded
    missing_quantity = Column(Boolean, default=False)
    explanation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)

    estimate_run = relationship("EstimateRun", back_populates="estimate_lines")
    overrides = relationship(
        "EstimatorOverride",
        back_populates="estimate_line",
        cascade="all, delete-orphan",
    )


# ─── Commercial structure ────────────────────────────────────────────────────


class CostBreakdownBucket(Base):
    """Commercial rollup bucket — keyed to an estimate run. §9.12"""

    __tablename__ = "cost_breakdown_buckets"

    BUCKET_TYPES = (
        "direct_labor",
        "direct_material",
        "direct_equipment",
        "subcontract",
        "general_conditions",
        "temporary_facilities",
        "supervision",
        "logistics",
        "permits",
        "testing",
        "contingency",
        "escalation",
        "overhead",
        "fee",
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    estimate_run_id = Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)
    bucket_type = Column(String(50), nullable=False)
    amount = Column(Float, default=0.0)
    method = Column(String(50), nullable=True)
    # percent_of_direct | lump_sum | computed
    notes = Column(Text, nullable=True)

    estimate_run = relationship("EstimateRun", back_populates="cost_breakdown_buckets")


# ─── Risk ────────────────────────────────────────────────────────────────────


class RiskItem(Base):
    """Explicit estimate risk item. §9.13 / §17"""

    __tablename__ = "decision_risk_items"

    CATEGORIES = (
        "scope_ambiguity",
        "design_incompleteness",
        "procurement_risk",
        "schedule_compression",
        "market_volatility",
        "labor_availability",
        "site_logistics",
        "subsurface_uncertainty",
        "owner_decision_risk",
        "permit_utility_coordination",
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    estimate_run_id = Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)
    name = Column(String(255), nullable=False)
    category = Column(String(50), nullable=True)
    probability = Column(Float, default=0.5)
    impact_cost = Column(Float, default=0.0)
    impact_time_days = Column(Integer, nullable=True)
    severity = Column(String(20), default="medium")  # low | medium | high | critical
    mitigation = Column(Text, nullable=True)
    source = Column(String(50), nullable=True)  # scope_gap | checklist | estimator | system
    # Traceability
    linked_scope_item_id = Column(String(36), ForeignKey("scope_items.id"), nullable=True)
    source_reference_id = Column(String(36), ForeignKey("source_references.id"), nullable=True)

    estimate_run = relationship("EstimateRun", back_populates="risk_items")


# ─── Escalation ──────────────────────────────────────────────────────────────


class EscalationInput(Base):
    """Category-specific escalation assumption. §9.15 / §18"""

    __tablename__ = "escalation_inputs"

    CATEGORIES = (
        "concrete",
        "steel",
        "rebar",
        "asphalt",
        "fuel",
        "electrical_commodities",
        "specialty_systems",
        "subcontractor_market",
    )

    id = Column(String(36), primary_key=True, default=_uuid)
    estimate_run_id = Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)
    category = Column(String(50), nullable=True)
    base_index = Column(Float, nullable=True)  # starting cost index value
    escalation_rate = Column(Float, default=0.03)  # annual rate, e.g. 0.04 = 4%
    start_date = Column(Date, nullable=True)  # when cost exposure begins
    procurement_date = Column(Date, nullable=True)  # when material is locked in
    install_date = Column(Date, nullable=True)  # when material is installed
    escalation_amount = Column(Float, nullable=True)  # computed: base × rate × duration

    estimate_run = relationship("EstimateRun", back_populates="escalation_inputs")


# ─── Schedule scenarios ──────────────────────────────────────────────────────


class ScheduleScenario(Base):
    """Schedule assumptions and their cost impact. §9.14 / §12.7 / §19"""

    __tablename__ = "schedule_scenarios"

    id = Column(String(36), primary_key=True, default=_uuid)
    estimate_run_id = Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)
    planned_duration_days = Column(Integer, nullable=True)
    aggressive_duration_days = Column(Integer, nullable=True)
    conservative_duration_days = Column(Integer, nullable=True)
    labor_loading_factor = Column(Float, default=1.0)
    gc_duration_factor = Column(Float, default=1.0)
    acceleration_cost = Column(Float, nullable=True)
    schedule_risk_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)

    estimate_run = relationship("EstimateRun", back_populates="schedule_scenarios")


# ─── Estimator overrides (learning loop) ─────────────────────────────────────


class EstimatorOverride(Base):
    """Captured estimator change. §9.16 / §21"""

    __tablename__ = "estimator_overrides"

    id = Column(String(36), primary_key=True, default=_uuid)
    estimate_run_id = Column(String(36), ForeignKey("estimate_runs.id"), nullable=False)
    estimate_line_id = Column(String(36), ForeignKey("decision_estimate_lines.id"), nullable=False)
    original_value = Column(Float, nullable=False)
    overridden_value = Column(Float, nullable=False)
    override_type = Column(String(30), nullable=False)
    # unit_cost | quantity | scope_status | line_excluded
    reason_code = Column(String(50), nullable=True)
    # local_knowledge | vendor_quote | market_adjustment | scope_change | data_distrust
    reason_text = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=_now)

    estimate_run = relationship("EstimateRun", back_populates="overrides")
    estimate_line = relationship("EstimateLine", back_populates="overrides")


# ─── Bid outcomes ────────────────────────────────────────────────────────────


class BidOutcome(Base):
    """Post-bid result — closes the learning loop. §9.17 / §21"""

    __tablename__ = "bid_outcomes"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    estimate_run_id = Column(String(36), ForeignKey("estimate_runs.id"), nullable=True)
    outcome = Column(String(20), nullable=True)  # won | lost | no_bid | pending
    final_bid_submitted = Column(Float, nullable=True)
    winning_bid_value = Column(Float, nullable=True)
    delta_to_winner = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=_now)

    project = relationship("Project", back_populates="bid_outcomes")


# ─── Field actuals ───────────────────────────────────────────────────────────


class FieldActual(Base):
    """Project actuals after execution — feeds back into comparable data. §9.18"""

    __tablename__ = "field_actuals"

    id = Column(String(36), primary_key=True, default=_uuid)
    comparable_project_id = Column(String(36), ForeignKey("comparable_projects.id"), nullable=False)
    canonical_activity_name = Column(String(255), nullable=True)
    quantity = Column(Float, nullable=True)
    unit = Column(String(20), nullable=True)
    actual_unit_cost = Column(Float, nullable=True)
    actual_total_cost = Column(Float, nullable=True)
    actual_production_rate = Column(Float, nullable=True)
    variance_to_estimate = Column(Float, nullable=True)
    cost_code = Column(String(50), nullable=True)
    source_system = Column(String(100), nullable=True)  # §9.18
    data_quality_score = Column(Float, default=0.5)

    comparable_project = relationship("ComparableProject", back_populates="field_actuals")
