"""History routes: unified history, event detail, sync, availability."""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.deps import ActorDep, SessionDep
from app.schemas.history import (
    HistoryAvailability,
    HistoryEventDetail,
    HistoryResponse,
)
from app.services import history_service

router = APIRouter(tags=["history"])


@router.get(
    "/sandboxes/{connection_id}/{sandbox_id}/history",
    response_model=HistoryResponse,
)
async def get_history(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
    operation_type: str | None = Query(None, description="Filter by operation type (command, file_write, etc.)"),
    status: str | None = Query(None, description="Filter by status (succeeded, failed, etc.)"),
    actor_id: str | None = Query(None, description="Filter by actor ID (which agent/user)"),
    source: str | None = Query(None, description="Filter by source (console, agent, etc.)"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
) -> HistoryResponse:
    """Get unified history for a sandbox with optional filtering."""
    return await history_service.get_history(
        session, connection_id, sandbox_id,
        operation_type=operation_type,
        status=status,
        actor_id=actor_id,
        source=source,
        limit=limit,
    )


@router.get(
    "/sandboxes/{connection_id}/{sandbox_id}/history/events/{event_id}",
    response_model=HistoryEventDetail,
)
async def get_history_event(
    connection_id: str,
    sandbox_id: str,
    event_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> HistoryEventDetail:
    """Get detailed view of a single history event."""
    result = await history_service.get_history_event(
        session, connection_id, sandbox_id, event_id,
    )
    if result is None:
        from app.core.errors import ExplorerError

        raise ExplorerError(
            f"Event {event_id} not found",
            status_code=404,
            code="event_not_found",
        )
    return result


@router.post(
    "/sandboxes/{connection_id}/{sandbox_id}/history/sync",
)
async def sync_history(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> dict:
    """Trigger an immediate history sync for a sandbox."""
    return await history_service.sync_history(session, connection_id, sandbox_id)


@router.get(
    "/sandboxes/{connection_id}/{sandbox_id}/history/availability",
    response_model=HistoryAvailability,
)
async def get_availability(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> HistoryAvailability:
    """Check history helper availability for a sandbox."""
    return await history_service.get_availability(session, connection_id, sandbox_id)
