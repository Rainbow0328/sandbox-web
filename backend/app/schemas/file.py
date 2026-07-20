"""File-related Pydantic schemas."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class FileKind(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    OTHER = "other"


class FileEntryResponse(BaseModel):
    """A single file or directory entry."""

    path: str
    kind: FileKind
    size: int = Field(ge=0)
    content_hash: str | None = None


class FileListResponse(BaseModel):
    """List of files in a directory."""

    path: str
    entries: list[FileEntryResponse]


class FileContentResponse(BaseModel):
    """File content with metadata."""

    path: str
    content: str  # UTF-8 text; binary files use download endpoint
    content_hash: str
    size: int
    is_binary: bool = False


class FileWriteRequest(BaseModel):
    """Request body for PUT /file — content is UTF-8 text."""

    content: str = Field(description="File content (UTF-8 text)")
    expected_hash: str | None = Field(
        default=None,
        description="If-Match hash for optimistic concurrency control",
    )


class FileWriteResponse(BaseModel):
    """Response after a successful file write."""

    path: str
    content_hash: str
    size: int
    previous_hash: str | None = None
