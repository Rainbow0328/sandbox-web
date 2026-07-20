"""FastAPI application factory and lifespan management."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from datetime import UTC

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.v1 import router as v1_router
from app.core.config import get_settings
from app.core.errors import ExplorerError, explorer_exception_handler
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.engine import dispose_engine, get_engine
from app.observability.metrics import metrics_endpoint


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup and shutdown lifecycle."""
    settings = get_settings()
    configure_logging(debug=False)

    # Create database tables (v0.1: use metadata.create_all until Alembic is wired).
    engine = get_engine()

    # --- Schema migration: detect old schema and reset ---
    # If the legacy ``providers`` table exists, the database predates the
    # Provider→Connection refactoring. Drop all tables and recreate.
    async with engine.begin() as conn:
        result = await conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='providers'")
        )
        if result.scalar_one_or_none() is not None:
            await conn.run_sync(Base.metadata.drop_all)
            # Drop orphaned legacy tables not in current metadata.
            for legacy in ["providers", "provider_sandboxes", "provider_capabilities"]:
                await conn.execute(text(f"DROP TABLE IF EXISTS {legacy}"))

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Persist deployment_id to system_meta if not already present.
    from sqlalchemy import select

    from app.db.engine import get_session_factory
    from app.models.system_meta import SystemMeta

    factory = get_session_factory()
    async with factory() as session:
        existing = await session.execute(
            select(SystemMeta).where(SystemMeta.key == "deployment_id")
        )
        stored = existing.scalar_one_or_none()
        if stored is None:
            session.add(
                SystemMeta(
                    key="deployment_id",
                    value=settings.deployment_id,
                    updated_at=_now_iso(),
                )
            )
            await session.commit()
        else:
            # Override settings with persisted value for Consumer ID stability.
            settings.deployment_id = stored.value

    yield

    # Graceful shutdown: close all cached adapters + dispose engine.
    from app.services.connection_service import _adapter_cache

    for adapter in _adapter_cache.values():
        if hasattr(adapter, "close"):
            try:
                await adapter.close()
            except Exception:
                pass
    _adapter_cache.clear()
    await dispose_engine()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="Sandbox Explorer",
        description="Web Console for observing and operating sandbox environments.",
        version="0.1.0",
        lifespan=lifespan,
    )

    # CORS
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Exception handlers
    app.add_exception_handler(ExplorerError, explorer_exception_handler)

    # API routes
    app.include_router(v1_router)

    # Health checks
    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict:
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    async def readyz() -> JSONResponse:
        try:
            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return JSONResponse({"status": "ready"})
        except Exception as exc:
            return JSONResponse({"status": "not ready", "error": str(exc)}, status_code=503)

    @app.get("/metrics", tags=["health"])
    async def metrics():
        return await metrics_endpoint()

    # Serve frontend static files if the directory exists.
    import os

    static_dir = os.environ.get("EXPLORER_STATIC_DIR", "")
    if static_dir and os.path.isdir(static_dir):
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")

    return app


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# Module-level app instance for ``uvicorn app.main:app``.
app = create_app()
