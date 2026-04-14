"""ProductivityBenchmark model — aggregated cost/productivity data computed from HistoricalLineItems."""

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)

from apex.backend.db.database import Base


class ProductivityBenchmark(Base):
    """Aggregated benchmark record keyed on CSI code + project type + region + org."""

    __tablename__ = "productivity_benchmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # CSI classification
    csi_division = Column(String(2), nullable=False, index=True)  # e.g. "03", "09"
    csi_code = Column(String(20), nullable=True, index=True)  # e.g. "03 30 00"

    description = Column(String(500), nullable=False)

    # Segmentation dimensions
    project_type = Column(String(50), nullable=True, index=True)  # healthcare, commercial, industrial
    region = Column(String(100), nullable=True, index=True)  # MSA or state

    unit_of_measure = Column(String(20), nullable=False)  # SF, LF, CY, EA, etc.

    # Aggregated cost stats
    avg_unit_cost = Column(Float, nullable=False)
    avg_labor_cost_per_unit = Column(Float, nullable=True)
    avg_material_cost_per_unit = Column(Float, nullable=True)
    avg_equipment_cost_per_unit = Column(Float, nullable=True)
    avg_sub_cost_per_unit = Column(Float, nullable=True)

    # Productivity rate
    avg_labor_hours_per_unit = Column(Float, nullable=True)

    # Distribution
    min_unit_cost = Column(Float, nullable=True)
    max_unit_cost = Column(Float, nullable=True)
    std_dev = Column(Float, nullable=True)

    # Data quality
    sample_size = Column(Integer, nullable=False)
    confidence_score = Column(Float, nullable=True)  # 0.0–1.0

    last_computed_at = Column(DateTime, nullable=False)
    source_project_ids = Column(Text, nullable=True)  # JSON array of contributing project IDs

    # Org scope
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Soft-delete + timestamps
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, onupdate=func.now(), nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        Index(
            "ix_pb_division_type_region_org",
            "csi_division",
            "project_type",
            "region",
            "organization_id",
        ),
        Index(
            "ix_pb_code_uom_org",
            "csi_code",
            "unit_of_measure",
            "organization_id",
        ),
    )
