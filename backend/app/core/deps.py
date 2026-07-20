"""FastAPI dependency injection providers."""

from __future__ import annotations

from typing import Annotated

from fastapi import Cookie, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AuthenticationError
from app.core.security import verify_admin_token
from app.db import get_session

# --- Type aliases for reusable dependencies ---
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


async def get_current_actor(
    settings: SettingsDep,
    authorization: Annotated[str | None, Header()] = None,
    session_token: Annotated[str | None, Cookie()] = None,
) -> str:
    """Resolve the current authenticated actor.

    Auth disabled in development mode — returns "admin" for all requests.
    Set EXPLORER_ADMIN_TOKEN to re-enable authentication.
    """
    if not settings.admin_token:
        return "admin"

    # 1. Try Bearer token (admin token or session token from login).
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        if verify_admin_token(token):
            return "admin"
        actor = await _verify_session_token(token, settings)
        if actor:
            return actor
        raise AuthenticationError("Invalid bearer token")

    # 2. Try session cookie.
    if session_token:
        actor = await _verify_session_token(session_token, settings)
        if actor:
            return actor
        raise AuthenticationError("Invalid or expired session")

    raise AuthenticationError("No authentication credentials provided")


ActorDep = Annotated[str, Depends(get_current_actor)]


async def _verify_session_token(token: str, settings: Settings) -> str | None:
    """Verify a session token against the sessions table.

    Delegated to the auth service to avoid circular imports.
    """
    from app.auth.service import verify_session

    return await verify_session(token)
