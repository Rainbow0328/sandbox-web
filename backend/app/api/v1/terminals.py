"""Terminal routes: create session and WebSocket endpoint."""

from __future__ import annotations

import secrets

from fastapi import APIRouter, WebSocket
from pydantic import BaseModel

from app.core.deps import ActorDep, SessionDep
from app.realtime import handle_terminal_websocket

router = APIRouter(tags=["terminals"])


class TerminalCreateResponse(BaseModel):
    """Response for POST /terminals."""

    terminal_id: str
    ws_url: str


@router.post(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/terminals",
    response_model=TerminalCreateResponse,
    status_code=201,
)
async def create_terminal(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> TerminalCreateResponse:
    """Create a new terminal session for a sandbox."""
    terminal_id = f"tty-{secrets.token_hex(8)}"
    ws_url = f"/api/v1/connections/{connection_id}/sandboxes/{sandbox_id}/terminals/{terminal_id}/ws"
    return TerminalCreateResponse(terminal_id=terminal_id, ws_url=ws_url)


@router.websocket(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/terminals/{terminal_id}/ws",
)
async def terminal_websocket(
    websocket: WebSocket,
    connection_id: str,
    sandbox_id: str,
    terminal_id: str,
) -> None:
    """WebSocket endpoint for terminal I/O."""
    await handle_terminal_websocket(websocket, connection_id, sandbox_id)
