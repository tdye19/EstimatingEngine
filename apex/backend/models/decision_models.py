"""Decision system domain models — coexist with existing agent pipeline models."""

import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
)
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


class ComparableProject(Base):
    __tablename__ = "comparable_projects"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), nullable=False)
    client = Column(String(255), nullable=True)
    location = Column(String(500), nullable=True)
    completed_date = Column(DateTime, nullable=True)
    final_contract_value = Column(Float, nullable=True)
    project_type = Column(String(100), nullable=True)
    market_sector = Column(String(100), nullable=True)
    region = Column(String(100), nullable=True)
    delivery_method = Column(String(50), nullable=True)
    contract_type = Column(String(50), nullable=True)
    size_sf = Column(Float, nullable=True)
    scope_types = Column(Text, nullable=True)  # JSON array stored as text
    complexity_level = Column(String(20), nullable=True)
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
    __tablename__ = "historical_rate_observations"

    id = Column(String(36), primary_key=True, default=_uuid)
    comparable_project_id = Column(
        String(36), ForeignKey("comparable_projects.id"), nullable=False
    )
    canonical_activity_id = Column(
        String(36), ForeignKey("canonical_activities.id"), nullable=True
    )
    raw_activity_name = Column(String(500), nullable=False)
    division_code = Column(String(20), nullable=True)
    quantity = Column(Float, nullable=True)
    unit = Column(String(20), nullable=True)
    unit_cost = Column(Float, nullable=True)
    total_cost = Column(Float, nullable=True)
    labor_cost = Column(Float, nullable=True)
    material_cost = Column(Float, nullable=True)
    equipment_cost = Column(Float, nullable=True)
    sub_cost = Column(Float, nullable=True)
    production_rate = Column(Float, nullable=True)
    production_rate_unit = Column(String(50), nullable=True)
    data_quality_score = Column(Float, default=0.5)
    source_row = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_now)

    comparable_project = relationship(
        "ComparableProject", back_populates="rate_observations"
    )


class CanonicalActivity(Base):
    __tablename__ = "canonical_activities"

    id = Column(String(36), primary_key=True, default=_uuid)
    name = Column(String(255), unique=True, nullable=False)
    division_code = Column(String(20), nullable=False)
    division_name = Column(String(255), nullable=True)
    expected_unit = Column(String(20), nullable=True)
    scope_family = Column(String(100), nullable=True)
    typical_cost_bucket = Column(String(50), nullable=True)
    common_dependencies = Column(Text, nullable=True)  # JSON array stored as text
    notes = Column(Text, nullable=True)

    aliases = relationship(
        "ActivityAlias",
        back_populates="canonical_activity",
        cascade="all, delete-orphan",
    )


class ActivityAlias(Base):
    __tablename__ = "activity_aliases"

    id = Column(String(36), primary_key=True, default=_uuid)
    canonical_activity_id = Column(
        String(36), ForeignKey("canonical_activities.id"), nullable=False
    )
    alias = Column(String(500), nullable=False)
    source = Column(String(50), nullable=True)
    confidence = Column(Float, default=1.0)

    canonical_activity = relationship("CanonicalActivity", back_populates="aliases")


class EstimateLine(Base):
    __tablename__ = "decision_estimate_lines"

    id = Column(String(36), primary_key=True, default=_uuid)
    # FK to the existing projects table (Integer PK)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    estimate_run_id = Column(String(100), nullable=True)
    description = Column(String(500), nullable=False)
    division_code = Column(String(20), nullable=True)
    quantity = Column(Float, nullable=False)
    unit = Column(String(20), nullable=True)
    recommended_unit_cost = Column(Float, nullable=True)
    recommended_total_cost = Column(Float, nullable=True)
    pricing_basis = Column(String(50), default="no_data")
    benchmark_sample_size = Column(Integer, nullable=True)
    benchmark_p25 = Column(Float, nullable=True)
    benchmark_p50 = Column(Float, nullable=True)
    benchmark_p75 = Column(Float, nullable=True)
    benchmark_p90 = Column(Float, nullable=True)
    benchmark_mean = Column(Float, nullable=True)
    benchmark_std_dev = Column(Float, nullable=True)
    benchmark_context_similarity = Column(Float, nullable=True)
    confidence_score = Column(Float, nullable=True)
    confidence_level = Column(String(20), default="very_low")
    missing_quantity = Column(Boolean, default=False)
    needs_review = Column(Boolean, default=True)
    explanation = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)

    overrides = relationship(
        "EstimatorOverride",
        back_populates="estimate_line",
        cascade="all, delete-orphan",
    )


class CostBreakdownBucket(Base):
    __tablename__ = "cost_breakdown_buckets"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    bucket_type = Column(String(50), nullable=False)
    amount = Column(Float, default=0.0)
    method = Column(String(50), nullable=True)
    notes = Column(Text, nullable=True)


class RiskItem(Base):
    __tablename__ = "decision_risk_items"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    name = Column(String(255), nullable=False)
    category = Column(String(50), nullable=True)
    probability = Column(Float, default=0.5)
    impact_cost = Column(Float, default=0.0)
    impact_time_days = Column(Integer, nullable=True)
    severity = Column(String(20), default="medium")
    mitigation = Column(Text, nullable=True)
    source = Column(String(50), nullable=True)


class EscalationInput(Base):
    __tablename__ = "escalation_inputs"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    category = Column(String(50), nullable=True)
    escalation_rate = Column(Float, default=0.03)
    escalation_amount = Column(Float, nullable=True)


class EstimatorOverride(Base):
    __tablename__ = "estimator_overrides"

    id = Column(String(36), primary_key=True, default=_uuid)
    estimate_line_id = Column(
        String(36), ForeignKey("decision_estimate_lines.id"), nullable=False
    )
    original_value = Column(Float, nullable=False)
    overridden_value = Column(Float, nullable=False)
    override_type = Column(String(30), nullable=False)
    reason_code = Column(String(50), nullable=True)
    reason_text = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=_now)

    estimate_line = relationship("EstimateLine", back_populates="overrides")


class BidOutcome(Base):
    __tablename__ = "bid_outcomes"

    id = Column(String(36), primary_key=True, default=_uuid)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    outcome = Column(String(20), nullable=True)
    final_bid_submitted = Column(Float, nullable=True)
    winning_bid_value = Column(Float, nullable=True)
    delta_to_winner = Column(Float, nullable=True)
    notes = Column(Text, nullable=True)
    recorded_at = Column(DateTime, default=_now)


class FieldActual(Base):
    __tablename__ = "field_actuals"

    id = Column(String(36), primary_key=True, default=_uuid)
    comparable_project_id = Column(
        String(36), ForeignKey("comparable_projects.id"), nullable=False
    )
    canonical_activity_name = Column(String(255), nullable=True)
    quantity = Column(Float, nullable=True)
    unit = Column(String(20), nullable=True)
    actual_unit_cost = Column(Float, nullable=True)
    actual_total_cost = Column(Float, nullable=True)
    actual_production_rate = Column(Float, nullable=True)
    variance_to_estimate = Column(Float, nullable=True)
    cost_code = Column(String(50), nullable=True)
    data_quality_score = Column(Float, default=0.5)

    comparable_project = relationship(
        "ComparableProject", back_populates="field_actuals"
    )
