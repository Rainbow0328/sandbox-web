"""FastAPI application factory and lifespan management."""

from __future__ import annotations

import contextlib
import logging
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text

from app.api.v1 import router as v1_router
from app.core.config import get_settings
from app.core.errors import ExplorerError, explorer_exception_handler
from app.core.logging import configure_logging
from app.db.base import Base
from app.db.engine import dispose_engine, get_engine, get_session_factory
from app.history.store_pool import close_all_stores
from app.models.system_meta import SystemMeta
from app.observability.metrics import metrics_endpoint
from app.services.connection_service import _adapter_cache

logger = logging.getLogger(__name__)


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler: converts any uncaught exception to a JSON error.

    This ensures SDK exceptions (e.g. SandboxNotFoundError) and other
    unexpected errors return structured JSON instead of a raw 500 traceback.
    """
    # Check if it's an SDK error with a known type name.
    exc_module = type(exc).__module__
    exc_name = type(exc).__name__

    # Map common SDK errors to appropriate HTTP status codes.
    status_code = 500
    code = "internal_error"

    if "NotFound" in exc_name:
        status_code = 404
        code = "not_found"
    elif "Timeout" in exc_name:
        status_code = 504
        code = "timeout"
    elif "Conflict" in exc_name or "Concurrent" in exc_name:
        status_code = 409
        code = "conflict"
    elif "Unreachable" in exc_name or "Connection" in exc_name:
        status_code = 503
        code = "connection_error"
    elif "Auth" in exc_name or "Permission" in exc_name or "Forbidden" in exc_name:
        status_code = 403
        code = "forbidden"

    logger.warning("Unhandled exception %s.%s: %s", exc_module, exc_name, exc)

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": str(exc),
                "details": {"exception_type": exc_name, "module": exc_module},
            }
        },
    )


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

    # Graceful shutdown: close all cached adapters + history stores + dispose engine.
    await close_all_stores()
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
        title="Sandbox Console",
        description="Web Console for observing and operating sandbox environments.",
        version="0.2.0",
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
    app.add_exception_handler(Exception, general_exception_handler)

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

    # Serve frontend static files.
    # Detection order: EXPLORER_STATIC_DIR env → bundled app/static → frontend/dist (dev).
    static_dir = os.environ.get("EXPLORER_STATIC_DIR", "")
    if static_dir and os.path.isdir(static_dir):
        _mount_static(app, static_dir)
    else:
        # Check for bundled static files inside the installed package.
        bundled = Path(__file__).resolve().parent / "static"
        if bundled.is_dir():
            real_files = [f for f in bundled.rglob("*") if f.name != ".gitkeep"]
            if real_files:
                _mount_static(app, str(bundled))

    return app


def _mount_static(app: FastAPI, static_dir: str) -> None:
    """Mount the SPA static files directory onto the FastAPI app."""
    from fastapi.staticfiles import StaticFiles
    from starlette.exceptions import HTTPException as StarletteHTTPException
    from starlette.responses import FileResponse

    class SPAStaticFiles(StaticFiles):
        """StaticFiles with SPA fallback: return index.html for unknown routes."""

        async def get_response(self, path: str, scope):
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as ex:
                if ex.status_code == 404 and not path.startswith("api/"):
                    return FileResponse(
                        os.path.join(static_dir, "index.html"),
                        media_type="text/html",
                    )
                raise

    app.mount("/", SPAStaticFiles(directory=static_dir, html=True), name="frontend")


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# Module-level app instance for ``uvicorn app.main:app``.
app = create_app()
