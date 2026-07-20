"""Session ORM model for Console authentication."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Session(Base):
    """A Console session issued after login (admin token or OIDC)."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # session token
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)  # 'admin' in v0.1
    auth_method: Mapped[str] = mapped_column(String(32), nullable=False)  # admin_token|oidc
    issued_at: Mapped[str] = mapped_column(String(40), nullable=False)
    expires_at: Mapped[str] = mapped_column(String(40), nullable=False)
    last_seen_at: Mapped[str] = mapped_column(String(40), nullable=False)
