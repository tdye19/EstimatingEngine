"""Organization model."""

from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from apex.backend.db.database import Base
from apex.backend.models.base import TimestampMixin


class Organization(Base, TimestampMixin):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    address = Column(String(500), nullable=True)
    phone = Column(String(50), nullable=True)
    license_number = Column(String(100), nullable=True)

    users = relationship("User", back_populates="organization")
    projects = relationship("Project", back_populates="organization")
