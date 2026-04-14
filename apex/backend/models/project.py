"""Project model."""

from sqlalchemy import Column, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    project_number = Column(String(100), unique=True, nullable=False)
    project_type = Column(String(50), nullable=False)  # commercial, industrial, healthcare, data_center, etc.
    status = Column(String(50), default="draft")  # draft, estimating, bid_submitted, awarded, completed
    mode = Column(String(20), default="shadow", nullable=False)  # shadow, production
    description = Column(Text, nullable=True)
    location = Column(String(500), nullable=True)
    square_footage = Column(Float, nullable=True)
    estimated_value = Column(Float, nullable=True)
    bid_date = Column(String(50), nullable=True)
    manual_estimate_total = Column(Float, nullable=True)
    manual_estimate_notes = Column(Text, nullable=True)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    organization_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)
    # ── Decision-system context fields (§9.1 / §10) ──────────────────────────
    region = Column(String(50), nullable=True)  # geographic market: midwest | southeast | northeast | west
    # Required for context-aware benchmarking — historical rates must be
    # filtered by context. A hospital is not a school. (arch §3.4)
    market_sector = Column(String(100), nullable=True)  # mission_critical, healthcare, education, etc.
    scope_types = Column(Text, nullable=True)  # JSON array: ["sitework","concrete","steel"]
    delivery_method = Column(String(50), nullable=True)  # cmar, design_build, hard_bid, gmp
    contract_type = Column(String(50), nullable=True)  # self_perform, subcontract, mixed
    complexity_level = Column(String(20), nullable=True)  # low | medium | high | very_high
    schedule_pressure = Column(String(20), nullable=True)  # low | medium | high | extreme
    bid_due_date = Column(String(50), nullable=True)  # ISO date string

    owner = relationship("User", back_populates="projects")
    organization = relationship("Organization", back_populates="projects")
    documents = relationship("Document", back_populates="project", cascade="all, delete-orphan")
    spec_sections = relationship("SpecSection", back_populates="project", cascade="all, delete-orphan")
    gap_reports = relationship("GapReport", back_populates="project", cascade="all, delete-orphan")
    takeoff_items = relationship("TakeoffItem", back_populates="project", cascade="all, delete-orphan")
    takeoff_items_v2 = relationship("TakeoffItemV2", back_populates="project", cascade="all, delete-orphan")
    labor_estimates = relationship("LaborEstimate", back_populates="project", cascade="all, delete-orphan")
    estimates = relationship("Estimate", back_populates="project", cascade="all, delete-orphan")
    project_actuals = relationship("ProjectActual", back_populates="project", cascade="all, delete-orphan")
    agent_run_logs = relationship("AgentRunLog", back_populates="project", cascade="all, delete-orphan")
    token_usage_records = relationship("TokenUsage", back_populates="project", cascade="all, delete-orphan")
    bid_comparisons = relationship("BidComparison", back_populates="project", cascade="all, delete-orphan")
    change_orders = relationship("ChangeOrder", back_populates="project", cascade="all, delete-orphan")
