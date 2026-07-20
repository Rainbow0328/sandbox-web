"""Database base class for SQLAlchemy ORM models."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all ORM models in the Web Console."""


class TimestampMixin:
    """Mixin providing created_at and updated_at columns."""

    created_at: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=lambda: _now_iso(),
    )
    updated_at: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default=lambda: _now_iso(),
        onupdate=lambda: _now_iso(),
    )


def _now_iso() -> str:
    """Return current UTC time in RFC3339 format."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
