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
        store = await _create_sdk_store(adapter, ref)
        if store is None:
            return None

        # Build the operation event payload for the SDK.
        event = _build_operation_event(
            operation_type=operation_type,
            status=status,
            actor_id=activity.actor_id,
            request_payload=request_payload,
            result_payload=result_payload,
            occurred_at=activity.occurred_at,
            completed_at=activity.completed_at,
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

        # Write to sandbox history via the SDK store.
        event_id = await _write_event(store, event)

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

    finally:
        if store is not None:
            try:
                await store.close()
            except Exception:
                pass


async def _create_sdk_store(adapter, ref):
    """Create a SandboxHistoryStore for writing to sandbox history."""
    try:
        from agent_sandbox_backends.history.config import (
            HistoryConfig,
            HistoryConsistency,
            HistoryMode,
        )
        from agent_sandbox_backends.history.provider_transport import (
            ProviderHistoryHelperTransport,
        )
        from agent_sandbox_backends.history.sandbox import SandboxHistoryStore
        from agent_sandbox_backends.version import SDK_VERSION

        sdk_provider = adapter.sdk_provider
        sdk_ref = adapter.to_sdk_ref(ref)
        transport = ProviderHistoryHelperTransport(sdk_provider, sdk_ref)
        store = SandboxHistoryStore(
            transport,
            sdk_version=SDK_VERSION,
            config=HistoryConfig(
                mode=HistoryMode.SANDBOX,
                consistency=HistoryConsistency.BEST_EFFORT,
            ),
        )
        await store.initialize()
        return store
    except Exception as exc:
        logger.warning("_create_sdk_store: failed to create store: %s", exc)
        return None


def _build_operation_event(
    *,
    operation_type: str,
    status: str,
    actor_id: str,
    request_payload: dict[str, Any] | None = None,
    result_payload: dict[str, Any] | None = None,
    occurred_at: str,
    completed_at: str | None = None,
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
) -> dict[str, Any]:
    """Build an operation event dict for the SDK's history store.

    The structure mirrors the SDK's ``OperationEvent`` schema, with Console
    as the source.
    """
    event: dict[str, Any] = {
        "source": "console",
        "actor_type": "user",
        "actor_id": actor_id,
        "operation_type": operation_type,
        "status": status,
        "occurred_at": occurred_at,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "request": request_payload,
        "result": result_payload,
        "schema_version": 1,
    }

    # Attach command fields if present.
    if command is not None or cwd is not None or exit_code is not None:
        event["command"] = {
            "command": command,
            "cwd": cwd,
            "exit_code": exit_code,
            "output_complete": 1,
            "history_storage_state": "complete",
        }

    # Attach file operation fields if present.
    if file_path is not None or file_change_type is not None:
        event["file_operation"] = {
            "file_path": file_path,
            "change_type": file_change_type,
            "before_hash": before_hash,
            "after_hash": after_hash,
            "before_size": before_size,
            "after_size": after_size,
        }

    return event


async def _write_event(store, event: dict[str, Any]) -> str | None:
    """Write an operation event to the sandbox history store.

    Uses the SDK's ``record_operation`` method if available.
    Returns the ``event_id`` on success, or ``None`` on failure.
    """
    try:
        # The SDK's SandboxHistoryStore may expose different write methods
        # depending on version. We try the most likely ones.
        if hasattr(store, "record_operation"):
            result = await store.record_operation(event)
            if isinstance(result, dict):
                return result.get("event_id")
            elif isinstance(result, str):
                return result
        elif hasattr(store, "write_operation"):
            result = await store.write_operation(event)
            if isinstance(result, dict):
                return result.get("event_id")
            elif isinstance(result, str):
                return result
        elif hasattr(store, "append_operation"):
            result = await store.append_operation(event)
            if isinstance(result, dict):
                return result.get("event_id")
            elif isinstance(result, str):
                return result
        else:
            logger.warning(
                "_write_event: SandboxHistoryStore has no known write method "
                "(record_operation/write_operation/append_operation)"
            )
            return None
    except Exception as exc:
        logger.warning("_write_event: failed to write event: %s", exc)
        return None
