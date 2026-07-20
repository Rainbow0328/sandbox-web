"""Auth-related Pydantic schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Request body for POST /api/v1/auth/login."""

    token: str = Field(min_length=1, description="Admin token")


class LoginResponse(BaseModel):
    """Response body for successful login."""

    session_token: str
    actor_id: str
    auth_method: str
    expires_at: str  # RFC3339


class ActorInfo(BaseModel):
    """Current authenticated actor info (GET /api/v1/auth/me)."""

    actor_id: str
    auth_method: str
