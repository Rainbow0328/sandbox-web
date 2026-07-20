"""Sandbox service: lifecycle operations (create, pause, resume, delete, capabilities)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import Capabilities, CreateSandboxRequest, SandboxInfo
from app.schemas.connection import ConnectionCreate
from app.services.connection_service import build_adapter, create_connection, get_connection
from app.services.file_service import _log_activity, get_sandbox_ref, invalidate_instance_id_cache

SANDBOX_NAME_METADATA_KEY = "agent_sandbox.name"
LEGACY_SANDBOX_NAME_METADATA_KEY = "sandbox_name"


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sandbox_info_to_dict(sb: SandboxInfo, connection_id: str) -> dict:
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


async def get_sandbox(
    session: AsyncSession, connection_id: str, sandbox_id: str
) -> dict:
    """Get a single sandbox by ID."""
    ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
    info = await adapter.get_sandbox(ref)
    return _sandbox_info_to_dict(info, connection_id)


async def create_sandbox(
    session: AsyncSession, connection_id: str, image: str, workdir: str,
    ttl_seconds: int | None = None,
    name: str = "",
) -> dict:
    """Create a new sandbox on the given connection."""
    connection = await get_connection(session, connection_id)
    adapter = build_adapter(connection)
    workdir = workdir or connection.default_workdir or "/workspace"
    request = CreateSandboxRequest(
        image=image,
        workdir=workdir,
    )
    # Store name and TTL in metadata.
    if name:
        request.metadata[SANDBOX_NAME_METADATA_KEY] = name
    if ttl_seconds is not None:
        request.metadata["sandbox_ttl_seconds"] = str(ttl_seconds)
    info = await adapter.create_sandbox(request)

    # Cache the instance_id for future lookups.
    from app.services.file_service import _instance_id_cache
    _instance_id_cache[f"{connection_id}:{info.ref.sandbox_id}"] = info.ref.sandbox_instance_id

    # Ensure workdir exists in the sandbox (Docker image may not have it).
    try:
        from app.adapters.base import ExecRequest
        await adapter.execute(info.ref, ExecRequest(
            command=f"mkdir -p {workdir}",
            cwd="/",
            timeout_seconds=10,
        ))
    except Exception:
        pass  # Non-fatal: workdir may already exist or mkdir unsupported.

    activity = await _log_activity(
        session, connection_id, info.ref.sandbox_id, "admin",
        "sandbox.create", "succeeded",
        {"image": image, "workdir": workdir},
    )

    # Best-effort write to sandbox history.
    from app.history.writer import write_operation_to_sandbox_history
    await write_operation_to_sandbox_history(
        session, info.ref, adapter, activity,
        operation_type="sandbox.create",
        status="succeeded",
        request_payload={"image": image, "workdir": workdir},
    )

    return _sandbox_info_to_dict(info, connection_id)


async def create_sandbox_direct(
    session: AsyncSession,
    *,
    endpoint: str,
    api_key: str = "",
    provider_type: str = "opensandbox",
    image: str = "python:3.12",
    workdir: str = "/workspace",
    name: str = "",
    ttl_seconds: int | None = None,
    save_connection: bool = True,
) -> dict:
    """Create a sandbox directly with endpoint + API key.

    If ``save_connection`` is true, a Connection record is auto-created
    (name derived from endpoint) so the sandbox can be managed later.
    Then delegates to ``create_sandbox``.
    """
    if save_connection:
        # Auto-create a connection record.
        from urllib.parse import urlparse

        parsed = urlparse(endpoint)
        host = parsed.hostname or endpoint
        conn_name = f"{host}-{endpoint[-6:] if len(endpoint) > 6 else endpoint}"

        conn_create = ConnectionCreate(
            name=conn_name,
            provider_type=provider_type,
            endpoint=endpoint,
            auth_method="api_key",
            credentials={"api_key": api_key} if api_key else {},
            default_workdir=workdir,
        )
        connection = await create_connection(session, conn_create)
        connection_id = connection.id
    else:
        # Ephemeral: create a temporary Connection-like object without persisting.
        # We still need a connection_id for activity logging, so create and mark disabled.
        from urllib.parse import urlparse

        parsed = urlparse(endpoint)
        host = parsed.hostname or endpoint
        conn_name = f"ephemeral-{host}"

        conn_create = ConnectionCreate(
            name=conn_name,
            provider_type=provider_type,
            endpoint=endpoint,
            auth_method="api_key",
            credentials={"api_key": api_key} if api_key else {},
            default_workdir=workdir,
        )
        connection = await create_connection(session, conn_create)
        connection_id = connection.id

    return await create_sandbox(
        session, connection_id, image, workdir,
        ttl_seconds=ttl_seconds,
        name=name,
    )


async def pause_sandbox(
    session: AsyncSession, connection_id: str, sandbox_id: str
) -> dict:
    """Pause a sandbox."""
    ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
    info = await adapter.pause_sandbox(ref)
    activity = await _log_activity(
        session, connection_id, sandbox_id, "admin",
        "sandbox.pause", "succeeded",
    )

    from app.history.writer import write_operation_to_sandbox_history
    await write_operation_to_sandbox_history(
        session, ref, adapter, activity,
        operation_type="sandbox.pause",
        status="succeeded",
    )

    return _sandbox_info_to_dict(info, connection_id)


async def resume_sandbox(
    session: AsyncSession, connection_id: str, sandbox_id: str
) -> dict:
    """Resume a paused sandbox."""
    ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
    info = await adapter.resume_sandbox(ref)
    activity = await _log_activity(
        session, connection_id, sandbox_id, "admin",
        "sandbox.resume", "succeeded",
    )

    from app.history.writer import write_operation_to_sandbox_history
    await write_operation_to_sandbox_history(
        session, ref, adapter, activity,
        operation_type="sandbox.resume",
        status="succeeded",
    )

    return _sandbox_info_to_dict(info, connection_id)


async def delete_sandbox(
    session: AsyncSession, connection_id: str, sandbox_id: str
) -> None:
    """Delete a sandbox."""
    ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)

    # Log before deleting (after delete, sandbox history is gone).
    activity = await _log_activity(
        session, connection_id, sandbox_id, "admin",
        "sandbox.delete", "succeeded",
    )

    from app.history.writer import write_operation_to_sandbox_history
    await write_operation_to_sandbox_history(
        session, ref, adapter, activity,
        operation_type="sandbox.delete",
        status="succeeded",
    )

    await adapter.delete_sandbox(ref)
    # Invalidate instance_id cache after deletion.
    invalidate_instance_id_cache(connection_id, sandbox_id)


async def get_capabilities(
    session: AsyncSession, connection_id: str, sandbox_id: str
) -> Capabilities:
    """Get capabilities for a sandbox."""
    ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
    return await adapter.capabilities(ref)
