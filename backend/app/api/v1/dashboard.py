"""Dashboard routes: aggregated overview metrics for the console UI.

Endpoints:
  GET /dashboard/overview  — counts, breakdowns, recent activity
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from app.core.deps import ActorDep, SessionDep
from app.services import dashboard_service

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/overview")
async def get_overview(session: SessionDep, actor: ActorDep) -> dict[str, Any]:
    """Return aggregated dashboard metrics.

    Includes:
    - Total/enabled connections, sandboxes by state, active workspaces.
    - Policy groups, rules (allow/deny counts).
    - Agent registrations (total / online).
    - Operation stats: by type, by status, by source, top actors, recent 20.
    - Sandbox summary list for quick navigation.
    """
    return await dashboard_service.get_overview(session)
