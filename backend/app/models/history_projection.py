"""History projection ORM model — imported from Sandbox Canonical History."""

from __future__ import annotations

from sqlalchemy import JSON, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HistoryProjection(Base):
    """Operation Projection imported from the Sandbox's Canonical History.

    This is NOT the Source of Truth — it is a read-optimized copy maintained
    by the history sync subsystem. Each row represents the *latest* state of
    an operation (upserted by event_id + source_seq).
    """

    __tablename__ = "history_projection"
    __table_args__ = (
        Index("idx_hist_proj_event", "connection_id", "sandbox_id", "sandbox_instance_id", "event_id"),
        Index("idx_hist_proj_run", "connection_id", "sandbox_id", "thread_id", "run_id"),
        Index("idx_hist_proj_seq", "connection_id", "sandbox_id", "source_seq"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[str] = mapped_column(String(26), nullable=False)
    sandbox_id: Mapped[str] = mapped_column(String(128), nullable=False)
    sandbox_instance_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_seq: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # console|sdk|provider|gateway
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[str] = mapped_column(String(40), nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    request_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    output_complete: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    history_storage_state: Mapped[str] = mapped_column(String(32), nullable=False, default="complete")
    # Command fields (denormalized)
    command: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    cwd: Mapped[str | None] = mapped_column(String(512), nullable=True)
    environment_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    timeout_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # File fields (denormalized)
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    file_change_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    before_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    after_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    before_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    after_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
