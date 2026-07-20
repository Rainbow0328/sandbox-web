"""Consumer cursor ORM model — tracks ACK position per sandbox."""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConsumerCursor(Base):
    """Per-sandbox consumer cursor for incremental history sync.

    Dual-cursor design for safe ACK recovery:
    - ``acknowledged_seq``: locally committed AND Helper-confirmed (read position).
    - ``pending_seq``: locally committed but NOT yet Helper-ACK'd (NULL if clean).
    On startup, if ``pending_seq`` is not NULL, retry ACK before querying new data.
    """

    __tablename__ = "consumer_cursors"

    connection_id: Mapped[str] = mapped_column(String(26), primary_key=True)
    sandbox_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    sandbox_instance_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    consumer_id: Mapped[str] = mapped_column(String(64), nullable=False)
    acknowledged_seq: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pending_seq: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_synced_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(512), nullable=True)
    reset_required: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
