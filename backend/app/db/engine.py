"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the cached async engine, creating it on first access."""
    global _engine, _session_factory
    if _engine is None:
        settings = get_settings()
        engine_kwargs: dict = {
            "echo": settings.database_echo,
            "future": True,
        }
        # SQLite needs special handling for async + file path.
        if settings.database_url.startswith("sqlite"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_async_engine(settings.database_url, **engine_kwargs)
        _session_factory = async_sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the cached session factory."""
    if _session_factory is None:
        get_engine()
    return _session_factory  # type: ignore[return-value]


async def get_session() -> AsyncSession:
    """FastAPI dependency: yield an async session."""
    factory = get_session_factory()
    async with factory() as session:
        yield session


async def dispose_engine() -> None:
    """Dispose the engine (for graceful shutdown / tests)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _session_factory = None
