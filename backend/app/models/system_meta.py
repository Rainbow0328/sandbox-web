"""System metadata table for deployment identity and configuration."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SystemMeta(Base):
    """Key-value store for deployment-level metadata (deployment_id, schema_version, etc.)."""

    __tablename__ = "system_meta"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    value: Mapped[str] = mapped_column(String(4096), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
