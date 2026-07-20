"""Command-related Pydantic schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CommandMode(StrEnum):
    FOREGROUND = "foreground"
    BACKGROUND = "background"


class CommandStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class CommandCreateRequest(BaseModel):
    """Request body for POST /commands."""

    command: str = Field(min_length=1)
    cwd: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float | None = Field(default=None, gt=0)
    mode: CommandMode = CommandMode.FOREGROUND


class CommandResponse(BaseModel):
    """Command status and result."""

    command_id: str
    remote_command_id: str | None = None
    status: CommandStatus
    exit_code: int | None = None
    duration_ms: int | None = None
    stdout: str = ""
    stderr: str = ""
    command: str = ""
    cwd: str | None = None
    mode: CommandMode = CommandMode.FOREGROUND


class CommandCreateResponse(BaseModel):
    """Response for POST /commands — includes command_id for SSE subscription."""

    command_id: str
    status: CommandStatus
    mode: CommandMode
