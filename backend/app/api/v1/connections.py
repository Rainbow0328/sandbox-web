"""Connection routes: CRUD and test_connection."""

from __future__ import annotations

from fastapi import APIRouter, Response

from app.core.deps import ActorDep, SessionDep
from app.schemas.connection import (
    ConnectionCreate,
    ConnectionResponse,
    ConnectionTestResult,
    ConnectionUpdate,
)
from app.services import connection_service

router = APIRouter(prefix="/connections", tags=["connections"])


def _to_response(connection) -> ConnectionResponse:
    """Convert a Connection ORM instance to a ConnectionResponse."""
    return ConnectionResponse(
        id=connection.id,
        name=connection.name,
        provider_type=connection.provider_type,
        endpoint=connection.endpoint,
        auth_method=connection.auth_method,
        default_workdir=connection.default_workdir,
        enabled=connection.enabled,
        capabilities_cache=connection.capabilities_cache,
        created_at=connection.created_at,
        updated_at=connection.updated_at,
    )


@router.get("", response_model=list[ConnectionResponse])
async def list_connections(session: SessionDep, actor: ActorDep) -> list[ConnectionResponse]:
    """List all registered connections."""
    connections = await connection_service.list_connections(session)
    return [_to_response(c) for c in connections]


@router.post("", response_model=ConnectionResponse, status_code=201)
async def create_connection(
    request: ConnectionCreate, session: SessionDep, actor: ActorDep
) -> ConnectionResponse:
    """Register a new connection."""
    connection = await connection_service.create_connection(session, request)
    return _to_response(connection)


@router.get("/{connection_id}", response_model=ConnectionResponse)
async def get_connection(
    connection_id: str, session: SessionDep, actor: ActorDep
) -> ConnectionResponse:
    """Get a single connection by ID."""
    connection = await connection_service.get_connection(session, connection_id)
    return _to_response(connection)


@router.patch("/{connection_id}", response_model=ConnectionResponse)
async def update_connection(
    connection_id: str,
    request: ConnectionUpdate,
    session: SessionDep,
    actor: ActorDep,
) -> ConnectionResponse:
    """Partially update a connection."""
    connection = await connection_service.update_connection(session, connection_id, request)
    return _to_response(connection)


@router.delete("/{connection_id}", status_code=200, response_class=Response)
async def delete_connection(connection_id: str, session: SessionDep, actor: ActorDep) -> None:
    """Delete a connection and clean up all related data."""
    await connection_service.delete_connection(session, connection_id)


@router.post("/{connection_id}/test", response_model=ConnectionTestResult)
async def test_connection(
    connection_id: str, session: SessionDep, actor: ActorDep
) -> ConnectionTestResult:
    """Test the connection to a sandbox environment and cache capabilities."""
    result = await connection_service.test_connection(session, connection_id)
    return ConnectionTestResult(**result)
