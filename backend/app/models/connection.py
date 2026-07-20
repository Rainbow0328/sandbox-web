"""Sandbox Connection ORM model.

A Connection stores the access configuration (endpoint + credentials) for a
sandbox environment. It is a Console-side convenience — sandboxes themselves
live in the sandbox service and their data (history, identity) resides in the
sandbox's own SQLite.
"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Connection(Base, TimestampMixin):
    """A registered sandbox connection (OpenSandbox, Microsandbox, etc.).

    Credentials are encrypted with Fernet using the master key.
    The ``capabilities_cache`` stores the result of the last ``test_connection`` call.
    """

    __tablename__ = "connections"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)  # ULID-like
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    provider_type: Mapped[str] = mapped_column(String(64), nullable=False)  # 'opensandbox'
    endpoint: Mapped[str] = mapped_column(String(512), nullable=False)
    auth_method: Mapped[str] = mapped_column(String(32), nullable=False)  # api_key|basic|bearer
    encrypted_credentials: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    capabilities_cache: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    default_workdir: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
