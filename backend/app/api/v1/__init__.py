"""API v1 router aggregation."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.auth import router as auth_router
from app.api.v1.dashboard import router as dashboard_router
from app.api.v1.backups import router as backups_router
from app.api.v1.commands import router as commands_router
from app.api.v1.connections import router as connections_router
from app.api.v1.files import router as files_router
from app.api.v1.history import router as history_router
from app.api.v1.policies import router as policies_router
from app.api.v1.sandboxes import router as sandboxes_router
from app.api.v1.terminals import router as terminals_router

router = APIRouter(prefix="/api/v1")
router.include_router(auth_router)
router.include_router(dashboard_router)
router.include_router(connections_router)
router.include_router(sandboxes_router)
router.include_router(files_router)
router.include_router(commands_router)
router.include_router(history_router)
router.include_router(backups_router)
router.include_router(terminals_router)
router.include_router(policies_router)

__all__ = ["router"]
