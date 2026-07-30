"""Backup-related Pydantic schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class BackupItem(BaseModel):
    """A single file backup record (metadata only, no content)."""

    backup_id: str
    file_path: str
    content_hash: str
    content_size: int
    encoding: str = "identity"
    original_size: int
    description: str = ""
    trigger_type: str = "manual"
    rule_name: str | None = None
    actor_type: str = "system"
    actor_id: str | None = None
    command: str | None = None
    created_at: str


class BackupDetail(BaseModel):
    """A backup record with optional content."""

    backup_id: str
    file_path: str
    content_hash: str
    content_size: int
    encoding: str = "identity"
    original_size: int
    description: str = ""
    trigger_type: str = "manual"
    rule_name: str | None = None
    actor_type: str = "system"
    actor_id: str | None = None
    command: str | None = None
    created_at: str
    content_base64: str | None = None


class BackupListResponse(BaseModel):
    """Paginated list of backups."""

    backups: list[BackupItem]
    total: int
    limit: int
    offset: int


class BackupFileListResponse(BaseModel):
    """List of files that have backups."""

    files: list[dict[str, Any]]
    total: int


class BackupCreateRequest(BaseModel):
    """Request to create a manual backup."""

    file_path: str
    description: str = ""


class BackupCreateResponse(BaseModel):
    """Response after creating a backup."""

    backup_id: str | None
    file_path: str
    created: bool
    message: str | None = None


class BackupRestoreRequest(BaseModel):
    """Request to restore a file from a backup."""

    backup_id: str


class BackupRestoreResponse(BaseModel):
    """Response after restoring (rolling back) a file from a backup."""

    backup_id: str
    file_path: str
    content_hash: str
    content_size: int
    restored: bool
    pre_restore_backup_id: str | None = None
    message: str | None = None


class BackupDeleteResponse(BaseModel):
    """Response after deleting a backup."""

    backup_id: str
    deleted: bool


class BackupDeleteByPathResponse(BaseModel):
    """Response after deleting all backups for a file path."""

    file_path: str
    deleted: int


class BackupDiffResponse(BaseModel):
    """Git-style unified diff between a backup and the next version."""

    backup_id: str
    file_path: str
    diff: str | None = None
    has_diff: bool = False
    comparison_source: str = ""
    is_binary: bool = False
    is_latest: bool = False
