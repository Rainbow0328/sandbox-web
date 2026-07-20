"""Auth service: login, session verification, logout."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_session_token, verify_admin_token
from app.db import get_session_factory
from app.models.session import Session

# Session lifetime (v0.1: 7 days).
SESSION_TTL = timedelta(days=7)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _expires_at_iso() -> str:
    return (datetime.now(UTC) + SESSION_TTL).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


async def login(admin_token: str) -> tuple[str, str, str] | None:
    """Verify the admin token and create a session.

    Returns ``(session_token, actor_id, expires_at)`` on success, or ``None``
    if the admin token is invalid.
    """
    if not verify_admin_token(admin_token):
        return None

    token = generate_session_token()
    now = _now_iso()
    expires = _expires_at_iso()

    factory = get_session_factory()
    async with factory() as session:
        sess = Session(
            id=token,
            actor_id="admin",
            auth_method="admin_token",
            issued_at=now,
            expires_at=expires,
            last_seen_at=now,
        )
        session.add(sess)
        await session.commit()

    return token, "admin", expires


async def verify_session(token: str) -> str | None:
    """Verify a session token and return the actor_id, or ``None`` if invalid/expired."""
    now = datetime.now(UTC)

    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Session).where(Session.id == token)
        )
        sess = result.scalar_one_or_none()
        if sess is None:
            return None

        # Check expiry.
        expires_dt = datetime.fromisoformat(sess.expires_at.replace("Z", "+00:00"))
        if expires_dt < now:
            # Clean up expired session.
            await session.execute(delete(Session).where(Session.id == token))
            await session.commit()
            return None

        return sess.actor_id


async def touch_session(token: str) -> None:
    """Update last_seen_at for a session token."""
    now = _now_iso()
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(
            update(Session).where(Session.id == token).values(last_seen_at=now)
        )
        await session.commit()


async def logout(token: str) -> None:
    """Delete a session."""
    factory = get_session_factory()
    async with factory() as session:
        await session.execute(delete(Session).where(Session.id == token))
        await session.commit()


async def cleanup_expired_sessions(session: AsyncSession) -> int:
    """Delete all expired sessions. Returns the number deleted."""
    now = _now_iso()
    result = await session.execute(
        delete(Session).where(Session.expires_at < now)
    )
    await session.commit()
    return result.rowcount or 0
