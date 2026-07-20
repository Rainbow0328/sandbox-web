"""Command routes: execute, status, cancel, and SSE stream."""

from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.deps import ActorDep, SessionDep
from app.schemas.command import (
    CommandCreateRequest,
    CommandCreateResponse,
    CommandResponse,
)
from app.services import command_service

router = APIRouter(tags=["commands"])


@router.post(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/commands",
    response_model=CommandCreateResponse,
    status_code=201,
)
async def create_command(
    connection_id: str,
    sandbox_id: str,
    request: CommandCreateRequest,
    session: SessionDep,
    actor: ActorDep,
) -> CommandCreateResponse:
    """Execute a command (foreground or background mode)."""
    return await command_service.execute_command(
        session, connection_id, sandbox_id, request, actor,
    )


@router.get(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/commands/{command_id}",
    response_model=CommandResponse,
)
async def get_command(
    connection_id: str,
    sandbox_id: str,
    command_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> CommandResponse:
    """Get command status and result."""
    result = await command_service.get_command(command_id)
    if result is None:
        from app.core.errors import ExplorerError

        raise ExplorerError(
            f"Command {command_id} not found",
            status_code=404,
            code="command_not_found",
        )
    return result


@router.post(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/commands/{command_id}/cancel",
)
async def cancel_command(
    connection_id: str,
    sandbox_id: str,
    command_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> dict:
    """Cancel a running command (v0.1: FakeAdapter runs synchronously, so this is a no-op)."""
    return {"ok": True, "message": "Command cancellation not supported with FakeAdapter"}


@router.get(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/commands/{command_id}/stream",
)
async def stream_command(
    connection_id: str,
    sandbox_id: str,
    command_id: str,
    actor: ActorDep,
) -> StreamingResponse:
    """SSE stream for command output.

    Replays buffered events from the command store. For v0.1 with FakeAdapter,
    events are available immediately after execution. The stream sends all
    buffered events and then closes.
    """

    async def event_generator():
        # Send buffered events.
        events = command_service.get_command_events(command_id)
        for event in events:
            yield f"data: {json.dumps(event)}\n\n"

        # Send a final close event.
        yield f"data: {json.dumps({'type': 'stream_end'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
