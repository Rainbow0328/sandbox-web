"""Sandboxes routes: cross-connection list + lifecycle operations."""

from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app.core.deps import ActorDep, SessionDep
from app.schemas.sandbox import SandboxInfo, SandboxListResponse
from app.services import connection_service, sandbox_service

router = APIRouter(tags=["sandboxes"])


class CreateSandboxRequest(BaseModel):
    """Request body for POST /connections/{id}/sandboxes."""

    image: str = Field(default="python:3.12")
    workdir: str = Field(default="/")
    name: str = Field(default="", description="User-friendly sandbox name")
    ttl_seconds: int | None = Field(
        default=None,
        description="Sandbox TTL in seconds. If set, sandbox auto-deletes after this duration. "
        "If not set, server default applies.",
    )


class CreateSandboxDirectRequest(BaseModel):
    """Request body for POST /sandboxes — create without a pre-registered connection."""

    endpoint: str = Field(..., description="Sandbox server endpoint URL")
    api_key: str = Field(default="", description="API key for authentication")
    provider_type: str = Field(default="opensandbox")
    image: str = Field(default="python:3.12")
    workdir: str = Field(default="/")
    name: str = Field(default="", description="User-friendly sandbox name")
    ttl_seconds: int | None = Field(default=None)
    save_connection: bool = Field(
        default=True,
        description="If true, auto-create a Connection record for future reuse.",
    )


@router.get("/sandboxes", response_model=SandboxListResponse)
async def list_sandboxes(session: SessionDep, actor: ActorDep) -> SandboxListResponse:
    """List sandboxes across all enabled connections (default homepage data)."""
    items = await connection_service.list_all_sandboxes(session)
    return SandboxListResponse(
        items=[SandboxInfo(**item) for item in items],
        total=len(items),
        next_page_token=None,
    )


@router.post(
    "/connections/{connection_id}/sandboxes",
    response_model=SandboxInfo,
    status_code=201,
)
async def create_sandbox(
    connection_id: str,
    request: CreateSandboxRequest,
    session: SessionDep,
    actor: ActorDep,
) -> SandboxInfo:
    """Create a new sandbox on the given connection."""
    result = await sandbox_service.create_sandbox(
        session, connection_id, request.image, request.workdir,
        ttl_seconds=request.ttl_seconds,
        name=request.name,
    )
    return SandboxInfo(**result)


@router.post(
    "/sandboxes",
    response_model=SandboxInfo,
    status_code=201,
)
async def create_sandbox_direct(
    request: CreateSandboxDirectRequest,
    session: SessionDep,
    actor: ActorDep,
) -> SandboxInfo:
    """Create a sandbox directly with endpoint + API key, without a pre-registered connection.

    If ``save_connection`` is true (default), a Connection record is auto-created
    so the sandbox can be managed later. Otherwise, an ephemeral connection is used.
    """
    result = await sandbox_service.create_sandbox_direct(
        session,
        endpoint=request.endpoint,
        api_key=request.api_key,
        provider_type=request.provider_type,
        image=request.image,
        workdir=request.workdir,
        name=request.name,
        ttl_seconds=request.ttl_seconds,
        save_connection=request.save_connection,
    )
    return SandboxInfo(**result)


@router.get(
    "/connections/{connection_id}/sandboxes/{sandbox_id}",
    response_model=SandboxInfo,
)
async def get_sandbox(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> SandboxInfo:
    """Get a single sandbox by ID."""
    result = await sandbox_service.get_sandbox(session, connection_id, sandbox_id)
    return SandboxInfo(**result)


@router.get(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/capabilities",
)
async def get_capabilities(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> dict:
    """Get capabilities for a sandbox."""
    caps = await sandbox_service.get_capabilities(session, connection_id, sandbox_id)
    return asdict(caps)


@router.post(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/pause",
    response_model=SandboxInfo,
)
async def pause_sandbox(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> SandboxInfo:
    """Pause a sandbox."""
    result = await sandbox_service.pause_sandbox(session, connection_id, sandbox_id)
    return SandboxInfo(**result)


@router.post(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/resume",
    response_model=SandboxInfo,
)
async def resume_sandbox(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> SandboxInfo:
    """Resume a paused sandbox."""
    result = await sandbox_service.resume_sandbox(session, connection_id, sandbox_id)
    return SandboxInfo(**result)


@router.delete(
    "/connections/{connection_id}/sandboxes/{sandbox_id}",
    status_code=200,
    response_class=Response,
)
async def delete_sandbox(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> None:
    """Delete a sandbox."""
    await sandbox_service.delete_sandbox(session, connection_id, sandbox_id)
