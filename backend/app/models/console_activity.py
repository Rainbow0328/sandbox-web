"""Console activity (Level 1 history) ORM model."""

from __future__ import annotations

from sqlalchemy import JSON, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConsoleActivity(Base):
    """Console's own operations (commands, file writes, lifecycle actions).

    This is the Level 1 history described in §7.1 — it records what the *Console*
    did, independent of the Sandbox's Canonical History.

    ``event_id`` links this activity to the corresponding event in the sandbox's
    Canonical History (written via SandboxHistoryStore). NULL means the write
    has not been attempted or has not yet succeeded.

    ``history_state`` tracks the write-to-sandbox-history lifecycle:
      - ``pending``: write not yet attempted
      - ``written``: successfully written to sandbox SQLite
      - ``failed``: write attempted but failed (will be retried)
    """

    __tablename__ = "console_activities"
    __table_args__ = (
        Index(
            "idx_console_activities_sandbox",
            "connection_id",
            "sandbox_id",
            "occurred_at",
        ),
        Index(
            "idx_console_activities_event",
            "connection_id",
            "sandbox_id",
            "event_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[str | None] = mapped_column(String(26), nullable=True)
    sandbox_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    request_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[str] = mapped_column(String(40), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Links to the sandbox's Canonical History event (NULL until written).
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Tracks the write-to-sandbox-history lifecycle.
    history_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending",
    )
