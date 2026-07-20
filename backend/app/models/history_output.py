"""History output chunks ORM model — lazy-loaded stdout/stderr Projection."""

from __future__ import annotations

from sqlalchemy import Index, Integer, LargeBinary, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class HistoryOutputChunk(Base):
    """Paginated stdout/stderr chunk cache for history operations.

    Chunks are lazily fetched from the Sandbox via the history helper's
    ``get-output`` subcommand and cached here for subsequent reads.
    """

    __tablename__ = "history_output_chunks"
    __table_args__ = (
        Index(
            "idx_hist_out_chunk",
            "connection_id",
            "sandbox_id",
            "event_id",
            "stream",
            "chunk_index",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    connection_id: Mapped[str] = mapped_column(String(26), nullable=False)
    sandbox_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    stream: Mapped[str] = mapped_column(String(16), nullable=False)  # stdout|stderr
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encoding: Mapped[str] = mapped_column(String(32), nullable=False, default="identity")
    original_size: Mapped[int] = mapped_column(Integer, nullable=False)
    fetched_at: Mapped[str] = mapped_column(String(40), nullable=False)
