"""History-related Pydantic schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class HistoryEvent(BaseModel):
    """A single operation event from the unified history."""

    event_id: str
    source_seq: int = 0
    source: str = "console"  # console|sdk|provider|gateway
    actor_type: str = "user"
    actor_id: str | None = None
    thread_id: str | None = None
    run_id: str | None = None
    operation_type: str
    status: str
    occurred_at: str
    completed_at: str | None = None
    duration_ms: int | None = None
    command: str | None = None
    cwd: str | None = None
    exit_code: int | None = None
    file_path: str | None = None
    file_change_type: str | None = None
    before_hash: str | None = None
    after_hash: str | None = None
    before_size: int | None = None
    after_size: int | None = None
    output_complete: int = 1
    history_storage_state: str = "complete"


class HistoryResponse(BaseModel):
    """Unified history response with coverage metadata."""

    coverage: str = "Connection/Sandbox history"  # or "Connection only"
    source: str = "sandbox"  # sandbox|console|database|none
    helper_status: str = "available"  # available|unavailable
    items: list[HistoryEvent]
    total: int
    last_synced_at: str | None = None


class HistoryEventDetail(BaseModel):
    """Detailed view of a single event, including output."""

    event: HistoryEvent
    stdout: str | None = None
    stderr: str | None = None
    request: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class HistoryAvailability(BaseModel):
    """Helper availability status for a sandbox."""

    available: bool
    reason: str | None = None
    last_synced_at: str | None = None
