"""ExportProfile — per-organization export branding and defaults."""

from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class ExportProfile(Base, TimestampMixin):
    __tablename__ = "export_profiles"

    id = Column(Integer, primary_key=True, index=True)
    organization_id = Column(
        Integer,
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    logo_url = Column(String(1000), nullable=True)
    header_text = Column(String(500), nullable=True)
    default_sections_json = Column(Text, nullable=True)  # JSON list of section keys
    include_assumptions = Column(Boolean, default=True, nullable=False)
    include_exclusions = Column(Boolean, default=True, nullable=False)
    # "trade" | "csi" | "scope_package"
    group_by = Column(String(50), default="trade", nullable=False)

    organization = relationship("Organization")
