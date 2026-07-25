"""History writer: writes Console operations to sandbox Canonical History.

This module reuses the SDK's ``SandboxHistoryStore`` to write Console-originated
operations (commands, file writes, lifecycle actions) into the sandbox's own
SQLite database. This ensures that Console operations appear in the sandbox's
unified history alongside SDK/agent operations.

Design principles:
- **Best-effort**: If the write fails, the Console operation still succeeds.
  The ``console_activities`` row retains ``history_state = "failed"`` for retry.
- **SDK reuse**: We do not re-implement history encoding — we delegate to the
  SDK's ``SandboxHistoryStore`` which handles helper installation, transport,
  and encoding.
- **Identity alignment**: The ``event_id`` returned by the SDK is stored back
  into the ``console_activities`` row for deduplication during history merge.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import SandboxAdapter, SandboxRef
from app.models.console_activity import ConsoleActivity

logger = logging.getLogger(__name__)


async def write_operation_to_sandbox_history(
    session: AsyncSession,
    ref: SandboxRef,
    adapter: SandboxAdapter,
    activity: ConsoleActivity,
    *,
    operation_type: str,
    status: str,
    request_payload: dict[str, Any] | None = None,
    result_payload: dict[str, Any] | None = None,
    command: str | None = None,
    cwd: str | None = None,
    exit_code: int | None = None,
    duration_ms: int | None = None,
    file_path: str | None = None,
    file_change_type: str | None = None,
    before_hash: str | None = None,
    after_hash: str | None = None,
    before_size: int | None = None,
    after_size: int | None = None,
) -> str | None:
    """Write a Console operation to the sandbox's Canonical History.

    Returns the ``event_id`` on success, or ``None`` on failure.

    On success, updates the ``console_activities`` row's ``event_id`` and
    ``history_state`` fields.

    On failure, sets ``history_state = "failed"`` and logs the error.
    The operation itself is NOT affected — this is best-effort.
    """
    # Only attempt for adapters that support SDK history (OpenSandbox).
    # FakeAdapter has no real sandbox SQLite, so skip silently.
    from app.adapters.opensandbox import OpenSandboxConsoleAdapter

    if not isinstance(adapter, OpenSandboxConsoleAdapter):
        # FakeAdapter or unknown — mark as "written" since there's no sandbox SQLite.
        activity.history_state = "written"
        await session.commit()
        return None

    store = None
    try:
        from app.history.store_pool import get_history_store
        store = await get_history_store(adapter, ref, connection_id=ref.provider_key, sandbox_id=ref.sandbox_id)
        if store is None:
            return None

        # Build the SDK OperationEvent object.
        event = _build_operation_event(
            operation_type=operation_type,
            status=status,
            actor_id=activity.actor_id,
            request_payload=request_payload,
            result_payload=result_payload,
            occurred_at=activity.occurred_at,
            duration_ms=duration_ms or activity.duration_ms,
            command=command,
            cwd=cwd,
            exit_code=exit_code,
            file_path=file_path,
            file_change_type=file_change_type,
            before_hash=before_hash,
            after_hash=after_hash,
            before_size=before_size,
            after_size=after_size,
        )

        # Write to sandbox history via the SDK store's append() method.
        event_id = await _write_event(store, event, ref)

        if event_id:
            # Update the console_activities row with the event_id and mark as written.
            activity.event_id = event_id
            activity.history_state = "written"
            await session.commit()
            logger.info(
                "write_operation_to_sandbox_history: wrote event %s for %s on sandbox %s",
                event_id, operation_type, ref.sandbox_id,
            )
            return event_id
        else:
            activity.history_state = "failed"
            await session.commit()
            return None

    except Exception as exc:
        logger.warning(
            "write_operation_to_sandbox_history: failed for %s on sandbox %s: %s",
            operation_type, ref.sandbox_id, exc,
        )
        try:
            activity.history_state = "failed"
            await session.commit()
        except Exception:
            pass
        return None


def _build_operation_event(
    *,
    operation_type: str,
    status: str,
    actor_id: str,
    request_payload: dict[str, Any] | None = None,
    result_payload: dict[str, Any] | None = None,
    occurred_at: str,
    duration_ms: int | None = None,
    command: str | None = None,
    cwd: str | None = None,
    exit_code: int | None = None,
    file_path: str | None = None,
    file_change_type: str | None = None,
    before_hash: str | None = None,
    after_hash: str | None = None,
    before_size: int | None = None,
    after_size: int | None = None,
) -> Any:
    """Build an SDK ``OperationEvent`` object for the history store.

    The SDK's ``SandboxHistoryStore.append()`` expects an ``OperationEvent``
    pydantic model, not a raw dict.  We construct it here using the SDK's
    own domain types so encoding is handled correctly.
    """
    from agent_sandbox_backends.domain.context import ActorContext
    from agent_sandbox_backends.history.encoding import (
        OperationEvent,
        OperationStatus,
    )

    # Map our status strings to SDK OperationStatus enum.
    status_lower = status.lower()
    if status_lower in ("succeeded", "success", "completed"):
        op_status = OperationStatus.SUCCEEDED
    elif status_lower in ("failed", "error"):
        op_status = OperationStatus.FAILED
    elif status_lower in ("running", "pending", "started"):
        op_status = OperationStatus.STARTED
    elif status_lower in ("cancelled", "canceled"):
        op_status = OperationStatus.CANCELLED
    elif status_lower == "timeout":
        op_status = OperationStatus.TIMEOUT
    else:
        op_status = OperationStatus.SUCCEEDED

    # Parse the ISO timestamp.
    try:
        if occurred_at.endswith("Z"):
            occurred_dt = datetime.fromisoformat(occurred_at.replace("Z", "+00:00"))
        else:
            occurred_dt = datetime.fromisoformat(occurred_at)
    except Exception:
        occurred_dt = datetime.now(timezone.utc)

    # Build request payload with command/file info embedded.
    request: dict[str, Any] = dict(request_payload or {})
    if command is not None:
        request["command"] = command
    if cwd is not None:
        request["cwd"] = cwd
    if exit_code is not None:
        request["exit_code"] = exit_code
    if file_path is not None:
        request["file_path"] = file_path
    if file_change_type is not None:
        request["file_change_type"] = file_change_type

    # Build result payload.
    result: dict[str, Any] | None = dict(result_payload) if result_payload else None
    if after_hash is not None:
        result = result or {}
        result["after_hash"] = after_hash
    if before_hash is not None:
        result = result or {}
        result["before_hash"] = before_hash

    actor = ActorContext(
        actor_type="user",
        actor_id=actor_id,
    )

    event_id = str(uuid.uuid4())

    return OperationEvent(
        event_id=event_id,
        occurred_at=occurred_dt,
        operation_type=operation_type,
        status=op_status,
        actor=actor,
        request=request,
        result=result,
        duration_ms=duration_ms,
        schema_version=1,
    )


async def _write_event(store, event: Any, ref: SandboxRef) -> str | None:
    """Write an operation event to the sandbox history store.

    The SDK's helper requires a STARTED event to exist before a COMPLETED
    event can be applied.  Console operations only create a single terminal
    event, so we synthesize a STARTED event first, then send the real
    COMPLETED event.

    Returns the ``event_id`` on success, or ``None`` on failure.
    """
    try:
        from agent_sandbox_backends.domain.operations import OperationStatus

        event_id = getattr(event, "event_id", None)

        # If the event is terminal, send a STARTED first so the helper
        # can create the history_events row before we update it.
        if event.status != OperationStatus.STARTED:
            started_event = event.model_copy(update={
                "status": OperationStatus.STARTED,
                "result": None,
                "duration_ms": None,
                "error_code": None,
            })
            try:
                await store.append(started_event)
            except Exception as started_exc:
                # STARTED might fail if the event already exists (e.g.
                # from a previous retry).  Log and continue — the
                # COMPLETED event will still work.
                logger.debug(
                    "_write_event: STARTED phase failed (may be OK): %s",
                    started_exc,
                )

        # Now send the real (terminal) event.
        await store.append(event)
        logger.info(
            "_write_event: successfully wrote event %s for sandbox %s",
            event_id, ref.sandbox_id,
        )
        return event_id
    except Exception as exc:
        logger.warning("_write_event: failed to write event: %s", exc)
        return None
