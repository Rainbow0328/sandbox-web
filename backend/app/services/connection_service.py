"""Connection service: CRUD, test_connection, and adapter construction."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import SandboxAdapter, create_adapter

# Import SandboxInfo for the list_sandboxes helper.
from app.adapters.base import SandboxInfo
from app.core.errors import ConnectionUnreachableError, ExplorerError
from app.core.security import decrypt_credentials, encrypt_credentials
from app.models.connection import Connection
from app.models.console_activity import ConsoleActivity
from app.models.consumer_cursor import ConsumerCursor
from app.models.history_output import HistoryOutputChunk
from app.models.history_projection import HistoryProjection
from app.schemas.connection import ConnectionCreate, ConnectionUpdate

SANDBOX_NAME_METADATA_KEY = "agent_sandbox.name"
LEGACY_SANDBOX_NAME_METADATA_KEY = "sandbox_name"


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _gen_id() -> str:
    """Generate a unique 26-char connection ID (ULID-like)."""
    return secrets.token_hex(13)


async def list_connections(session: AsyncSession) -> list[Connection]:
    """Return all registered connections."""
    result = await session.execute(select(Connection).order_by(Connection.created_at))
    return list(result.scalars().all())


async def get_connection(session: AsyncSession, connection_id: str) -> Connection:
    """Return a single connection by ID."""
    result = await session.execute(select(Connection).where(Connection.id == connection_id))
    connection = result.scalar_one_or_none()
    if connection is None:
        raise ExplorerError(
            f"Connection {connection_id} not found",
            status_code=404,
            code="connection_not_found",
        )
    return connection


async def create_connection(session: AsyncSession, request: ConnectionCreate) -> Connection:
    """Create a new connection."""
    now = _now_iso()
    connection = Connection(
        id=_gen_id(),
        name=request.name,
        provider_type=request.provider_type,
        endpoint=request.endpoint,
        auth_method=request.auth_method,
        encrypted_credentials=encrypt_credentials(request.credentials),
        default_workdir=request.default_workdir,
        enabled=True,
        created_at=now,
        updated_at=now,
    )
    session.add(connection)
    await session.commit()
    await session.refresh(connection)
    return connection


async def update_connection(
    session: AsyncSession, connection_id: str, request: ConnectionUpdate
) -> Connection:
    """Partially update a connection."""
    connection = await get_connection(session, connection_id)
    if request.name is not None:
        connection.name = request.name
    if request.endpoint is not None:
        connection.endpoint = request.endpoint
    if request.auth_method is not None:
        connection.auth_method = request.auth_method
    if request.credentials is not None:
        connection.encrypted_credentials = encrypt_credentials(request.credentials)
    if request.default_workdir is not None:
        connection.default_workdir = request.default_workdir
    if request.enabled is not None:
        connection.enabled = request.enabled
    connection.updated_at = _now_iso()
    await session.commit()
    await session.refresh(connection)
    # Invalidate adapter cache so updated credentials/endpoint take effect.
    old_adapter = _adapter_cache.pop(connection_id, None)
    if old_adapter and hasattr(old_adapter, "close"):
        try:
            await old_adapter.close()
        except Exception:
            pass  # Close failure is non-fatal.
    return connection


async def delete_connection(session: AsyncSession, connection_id: str) -> None:
    """Delete a connection and clean up all related Console-side data."""
    connection = await get_connection(session, connection_id)

    # Clean up orphaned projection, cursor, activity, and output chunk data.
    await session.execute(
        delete(HistoryProjection).where(HistoryProjection.connection_id == connection_id)
    )
    await session.execute(
        delete(ConsumerCursor).where(ConsumerCursor.connection_id == connection_id)
    )
    await session.execute(
        delete(ConsoleActivity).where(ConsoleActivity.connection_id == connection_id)
    )
    await session.execute(
        delete(HistoryOutputChunk).where(HistoryOutputChunk.connection_id == connection_id)
    )

    await session.delete(connection)
    await session.commit()
    # Invalidate adapter cache.
    old_adapter = _adapter_cache.pop(connection_id, None)
    if old_adapter and hasattr(old_adapter, "close"):
        try:
            await old_adapter.close()
        except Exception:
            pass  # Close failure is non-fatal.


_adapter_cache: dict[str, SandboxAdapter] = {}


def build_adapter(connection: Connection) -> SandboxAdapter:
    """Construct a SandboxAdapter from a Connection ORM instance.

    Adapters are cached by connection ID so that stateful adapters (e.g.
    FakeAdapter) persist their in-memory state across requests.
    """
    if connection.id in _adapter_cache:
        return _adapter_cache[connection.id]
    credentials = decrypt_credentials(connection.encrypted_credentials)
    adapter = create_adapter(
        provider_type=connection.provider_type,
        endpoint=connection.endpoint,
        credentials=credentials,
        provider_name=connection.name,
        provider_key=connection.id,
    )
    _adapter_cache[connection.id] = adapter
    return adapter


async def test_connection(session: AsyncSession, connection_id: str) -> dict[str, Any]:
    """Test the connection to a sandbox environment and cache capabilities."""
    connection = await get_connection(session, connection_id)
    adapter = build_adapter(connection)
    try:
        result = await adapter.test_connection()
    except Exception as exc:
        raise ConnectionUnreachableError(str(exc)) from exc

    # Cache capabilities in the connection row.
    if result.capabilities is not None:
        # Convert dataclass Capabilities to a serializable dict.
        from dataclasses import asdict

        connection.capabilities_cache = asdict(result.capabilities)
        connection.updated_at = _now_iso()
        await session.commit()

    return {
        "ok": result.ok,
        "message": result.message,
        "capabilities": connection.capabilities_cache,
        "version": result.version,
    }


async def list_sandboxes_for_connection(
    session: AsyncSession, connection_id: str
) -> list[SandboxInfo]:
    """List sandboxes on a specific connection."""
    connection = await get_connection(session, connection_id)
    adapter = build_adapter(connection)
    return await adapter.list_sandboxes()


async def list_all_sandboxes(session: AsyncSession) -> list[dict[str, Any]]:
    """Aggregate sandboxes across all enabled connections (parallel)."""
    import asyncio
    import logging
    logger = logging.getLogger(__name__)
    connections = await list_connections(session)

    async def _fetch_one(conn: Connection) -> list[dict[str, Any]]:
        if not conn.enabled:
            return []
        try:
            adapter = build_adapter(conn)
            sandboxes = await adapter.list_sandboxes()
            return [_sandbox_info_to_dict(sb, conn.id) for sb in sandboxes]
        except Exception as exc:
            logger.warning("list_all_sandboxes: connection %s failed: %s", conn.id, exc)
            return []

    # Fetch from all connections in parallel.
    results = await asyncio.gather(*[_fetch_one(c) for c in connections])
    all_sandboxes: list[dict[str, Any]] = []
    for batch in results:
        all_sandboxes.extend(batch)
    logger.info(
        "list_all_sandboxes: total %d sandboxes from %d connections",
        len(all_sandboxes), len(connections),
    )
    return all_sandboxes


def _sandbox_info_to_dict(sb: SandboxInfo, connection_id: str) -> dict[str, Any]:
    """Convert a SandboxInfo dataclass to a dict for the API response."""
    metadata = dict(sb.ref.metadata)
    return {
        "sandbox_id": sb.ref.sandbox_id,
        "connection_id": connection_id,
        "name": metadata.get(SANDBOX_NAME_METADATA_KEY)
        or metadata.get(LEGACY_SANDBOX_NAME_METADATA_KEY, ""),
        "state": sb.state.value if hasattr(sb.state, "value") else str(sb.state),
        "image": sb.image,
        "workdir": sb.workdir,
        "expires_at": None,
        "metadata": metadata,
    }
