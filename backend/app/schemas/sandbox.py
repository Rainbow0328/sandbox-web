"""Sandbox-related Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SandboxInfo(BaseModel):
    """Sandbox info as returned by the API."""

    sandbox_id: str
    connection_id: str | None = None
    name: str = ""
    state: str  # running|paused|stopped|...
    image: str | None = None
    workdir: str = "/workspace"
    expires_at: str | None = None  # RFC3339
    metadata: dict[str, str] = Field(default_factory=dict)


class SandboxListResponse(BaseModel):
    """Paginated list of sandboxes."""

    items: list[SandboxInfo]
    total: int
    next_page_token: str | None = None
