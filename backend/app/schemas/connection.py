"""Sandbox Connection-related Pydantic schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


def _normalize_endpoint(v: str) -> str:
    """Ensure endpoint has an http:// or https:// prefix."""
    if not v:
        return v
    v = v.strip()
    if not v.startswith("http://") and not v.startswith("https://"):
        v = f"http://{v}"
    return v


class ConnectionCreate(BaseModel):
    """Request body for POST /api/v1/connections."""

    name: str = Field(min_length=1, max_length=255)
    provider_type: str = Field(default="opensandbox", min_length=1, max_length=64)
    endpoint: str = Field(min_length=1, max_length=512)
    auth_method: str = Field(default="api_key", pattern="^(api_key|basic|bearer)$")
    credentials: dict[str, Any] = Field(
        description="Connection credentials (e.g. api_key, username/password). Encrypted at rest."
    )
    default_workdir: str | None = Field(default=None, max_length=512)

    @field_validator("endpoint")
    @classmethod
    def _ensure_scheme(cls, v: str) -> str:
        return _normalize_endpoint(v)


class ConnectionUpdate(BaseModel):
    """Request body for PATCH /api/v1/connections/{id}. All fields optional."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    endpoint: str | None = Field(default=None, min_length=1, max_length=512)
    auth_method: str | None = Field(default=None, pattern="^(api_key|basic|bearer)$")
    credentials: dict[str, Any] | None = None
    default_workdir: str | None = Field(default=None, max_length=512)
    enabled: bool | None = None

    @field_validator("endpoint")
    @classmethod
    def _ensure_scheme(cls, v: str | None) -> str | None:
        if v is None:
            return v
        return _normalize_endpoint(v)


class ConnectionResponse(BaseModel):
    """Connection as returned by the API (credentials are never exposed)."""

    id: str
    name: str
    provider_type: str
    endpoint: str
    auth_method: str
    default_workdir: str | None = None
    enabled: bool
    capabilities_cache: dict[str, Any] | None = None
    created_at: str
    updated_at: str


class ConnectionTestResult(BaseModel):
    """Result of a connection test_connection call."""

    ok: bool
    message: str = ""
    capabilities: dict[str, Any] | None = None
    version: str | None = None
