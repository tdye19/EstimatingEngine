"""Base mixin for all models with common fields."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, Column, DateTime


class TimestampMixin:
    created_at = Column(DateTime, default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    is_deleted = Column(Boolean, default=False, nullable=False)
