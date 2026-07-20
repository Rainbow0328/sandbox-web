"""History service: sync from adapter, upsert projection, serve unified history.

This service merges two data sources for the History Tab:
1. **history_projection**: synced from the sandbox's Canonical History SQLite
   via the SDK's ``SandboxHistoryStore``. This is the primary source.
2. **console_activities**: Console's own audit log. Activities with
   ``history_state != "written"`` (i.e., not yet confirmed in sandbox history)
   are shown as fallback entries to prevent history gaps.

Deduplication: when a ``console_activity`` has an ``event_id`` that also exists
in ``history_projection``, the projection (sandbox-sourced) entry takes precedence.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.fake import FakeAdapter
from app.adapters.opensandbox import OpenSandboxConsoleAdapter
from app.models.console_activity import ConsoleActivity
from app.models.consumer_cursor import ConsumerCursor
from app.models.history_projection import HistoryProjection
from app.schemas.history import (
    HistoryAvailability,
    HistoryEvent,
    HistoryEventDetail,
    HistoryResponse,
)
from app.services.file_service import get_sandbox_ref


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


async def sync_history(
    session: AsyncSession, connection_id: str, sandbox_id: str
) -> dict:
    """Sync history events from the adapter into the local projection.

    Correct flow:
      1. get_sandbox_ref returns real ref with correct instance_id.
      2. Read cursor: acknowledged_seq (confirmed) + pending_seq (unACK'd).
      3. If pending_seq exists, retry ACK first.
      4. Query changes → get_operation → map → upsert.
      5. Write pending_seq → commit → ACK → confirmed.
    """
    from app.core.config import get_settings

    ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
    instance_id = ref.sandbox_instance_id
    settings = get_settings()
    stable_consumer_id = f"console:{settings.deployment_id}"

    # Get current cursor (acknowledged_seq = confirmed, pending_seq = unACK'd).
    cursor_result = await session.execute(
        select(ConsumerCursor)
        .where(
            ConsumerCursor.connection_id == connection_id,
            ConsumerCursor.sandbox_id == sandbox_id,
            ConsumerCursor.sandbox_instance_id == instance_id,
        )
    )
    cursor = cursor_result.scalar_one_or_none()
    after_seq = cursor.acknowledged_seq if cursor else 0
    consumer_id = cursor.consumer_id if cursor else stable_consumer_id

    # Retry pending ACK if previous sync committed but ACK failed.
    if (
        isinstance(adapter, OpenSandboxConsoleAdapter)
        and cursor
        and cursor.pending_seq is not None
    ):
        retry_store = None
        try:
            retry_store = await _create_sdk_store(adapter, ref)
            await retry_store.acknowledge(consumer_id, cursor.pending_seq)
            cursor.acknowledged_seq = cursor.pending_seq
            cursor.pending_seq = None
            await session.commit()
            after_seq = cursor.acknowledged_seq
        except Exception:
            # ACK still failing — STOP sync, don't overwrite pending_seq.
            return {
                "synced": 0,
                "status": "ack_pending",
                "pending_seq": cursor.pending_seq,
            }
        finally:
            if retry_store is not None:
                try:
                    await retry_store.close()
                except Exception:
                    pass

    # --- Branch by adapter type ---
    sdk_store = None
    if isinstance(adapter, OpenSandboxConsoleAdapter):
        result = await _sync_from_sdk(adapter, ref, after_seq)
        events = result["operations"]
        next_seq = result["next_change_seq"]
        reset_required = result["reset_required"]
        sdk_store = result["store"]
    elif isinstance(adapter, FakeAdapter):
        events = adapter.get_history_events(ref)
        next_seq = max((e.get("source_seq", 0) for e in events), default=0)
        reset_required = False
    else:
        events = []
        next_seq = 0
        reset_required = False

    # Handle reset_required: clear local projection, restart from 0.
    if reset_required:
        await _clear_projection(session, connection_id, sandbox_id, instance_id)
        after_seq = 0

    # Upsert operations to local projection.
    upserted = 0
    for event in events:
        await _upsert_projection(session, connection_id, sandbox_id, instance_id, event)
        upserted += 1

    # Write pending_seq (committed but not yet ACK'd) — dual cursor.
    await _update_cursor_with_pending(
        session, connection_id, sandbox_id, instance_id, consumer_id, next_seq,
    )

    # Commit local transaction FIRST — before ACK.
    await session.commit()

    # ACK AFTER commit — on success, promote pending → confirmed.
    # ACK and close are SEPARATE: store must close even with no new data.
    try:
        if sdk_store and next_seq > after_seq:
            await sdk_store.acknowledge(consumer_id, next_seq)
            # ACK succeeded: promote pending_seq → acknowledged_seq.
            cursor_result2 = await session.execute(
                select(ConsumerCursor)
                .where(
                    ConsumerCursor.connection_id == connection_id,
                    ConsumerCursor.sandbox_id == sandbox_id,
                    ConsumerCursor.sandbox_instance_id == instance_id,
                )
            )
            cursor2 = cursor_result2.scalar_one_or_none()
            if cursor2:
                cursor2.acknowledged_seq = next_seq
                cursor2.pending_seq = None
                await session.commit()
    except Exception:
        pass  # ACK failed: pending_seq stays; next sync will retry.
    finally:
        if sdk_store is not None:
            try:
                await sdk_store.close()
            except Exception:
                pass

    return {"synced": upserted, "total": len(events)}


async def _create_sdk_store(adapter: OpenSandboxConsoleAdapter, ref):
    """Create a SandboxHistoryStore for ACK retry."""
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


async def _sync_from_sdk(
    adapter: OpenSandboxConsoleAdapter,
    ref,
    after_seq: int,
) -> dict:
    """Query real history from SDK with correct Change→Operation flow.

    1. query_changes() returns Change notifications (event_id + source_seq).
    2. For each event_id, call get_operation() to get full Operation data.
    3. Map SDK Operation format to Web Projection format.
    4. Paginate until next_change_seq >= max_change_seq.
    5. Return operations + metadata for upsert + ACK.

    Does NOT ACK — caller ACKs after local commit.
    """
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

        all_operations: list[dict] = []
        current_seq = after_seq
        max_seq = after_seq
        reset_required = False
        operation_error = None

        while True:
            response = await store.query_changes(
                after_change_seq=current_seq, limit=200,
            )

            if not isinstance(response, dict):
                break

            changes = response.get("changes", [])
            next_seq = response.get("next_change_seq", current_seq)
            max_seq = response.get("max_change_seq", current_seq)
            reset_required = response.get("reset_required", False)

            # If reset_required, restart from 0 after clearing.
            if reset_required and current_seq > 0:
                all_operations = []
                current_seq = 0
                continue  # Re-query from seq=0.

            # Get full Operation for each Change's event_id.
            # Stop on first failure — don't ACK past unprocessed changes.
            last_success_seq = current_seq
            for change in changes:
                event_id = change.get("event_id")
                if not event_id:
                    continue
                try:
                    op = await store.get_operation(event_id)
                    mapped = _map_sdk_operation(op, change.get("source_seq", 0))
                    all_operations.append(mapped)
                    last_success_seq = change.get("source_seq", next_seq)
                except Exception as exc:
                    operation_error = str(exc)
                    break  # Break for loop.

            current_seq = last_success_seq

            # Stop on operation error — prevent infinite loop on same failure.
            if operation_error is not None:
                break

            # Stop when no more changes or all consumed.
            if not changes or next_seq >= max_seq:
                break

        return {
            "operations": all_operations,
            "next_change_seq": current_seq,
            "max_change_seq": max_seq,
            "reset_required": reset_required,
            "store": store,
        }

    except Exception:
        # If store was created but we failed, close it to prevent leak.
        try:
            if "store" in dir() and store is not None:
                await store.close()
        except Exception:
            pass
        return {
            "operations": [],
            "next_change_seq": after_seq,
            "max_change_seq": after_seq,
            "reset_required": False,
            "store": None,
        }


def _map_sdk_operation(op: dict, source_seq: int) -> dict:
    """Map SDK get_operation() response to Web Projection format."""
    cmd = op.get("command") or {}
    file_op = op.get("file_operation") or {}

    mapped = {
        "event_id": op.get("event_id", ""),
        "source_seq": source_seq,
        "source": op.get("source", "console"),
        "actor_type": op.get("actor_type", "user"),
        "actor_id": op.get("actor_id"),
        "thread_id": op.get("thread_id"),
        "run_id": op.get("run_id"),
        "correlation_id": op.get("correlation_id"),
        "operation_type": op.get("operation_type", ""),
        "status": op.get("status", "unknown"),
        "occurred_at": op.get("occurred_at", ""),
        "completed_at": op.get("completed_at"),
        "duration_ms": op.get("duration_ms"),
        "request_json": op.get("request"),
        "result_json": op.get("result"),
        "schema_version": op.get("schema_version", 1),
        "output_complete": cmd.get("output_complete", 1),
        "history_storage_state": cmd.get("history_storage_state", "complete"),
    }

    # Extract command fields from nested command dict.
    if cmd:
        mapped["command"] = cmd.get("command")
        mapped["cwd"] = cmd.get("cwd")
        mapped["exit_code"] = cmd.get("exit_code")
        mapped["timeout_ms"] = cmd.get("timeout_ms")
        mapped["environment_json"] = cmd.get("environment_json")

    # Extract file operation fields from nested file_operation dict.
    if file_op:
        mapped["file_path"] = file_op.get("file_path") or file_op.get("path")
        mapped["file_change_type"] = file_op.get("change_type") or file_op.get("operation")
        mapped["before_hash"] = file_op.get("before_hash")
        mapped["after_hash"] = file_op.get("after_hash")
        mapped["before_size"] = file_op.get("before_size")
        mapped["after_size"] = file_op.get("after_size")

    return mapped


async def _clear_projection(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    instance_id: str,
) -> None:
    """Clear all projections for a sandbox instance (for reset_required)."""
    from sqlalchemy import delete

    await session.execute(
        delete(HistoryProjection)
        .where(
            HistoryProjection.connection_id == connection_id,
            HistoryProjection.sandbox_id == sandbox_id,
            HistoryProjection.sandbox_instance_id == instance_id,
        )
    )


async def _upsert_projection(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    sandbox_instance_id: str,
    event: dict,
) -> None:
    """Upsert a single event into history_projection (idempotent by event_id)."""
    result = await session.execute(
        select(HistoryProjection)
        .where(
            HistoryProjection.connection_id == connection_id,
            HistoryProjection.sandbox_id == sandbox_id,
            HistoryProjection.sandbox_instance_id == sandbox_instance_id,
            HistoryProjection.event_id == event["event_id"],
        )
    )
    existing = result.scalar_one_or_none()

    if existing is None:
        # Insert new projection.
        proj = HistoryProjection(
            connection_id=connection_id,
            sandbox_id=sandbox_id,
            sandbox_instance_id=sandbox_instance_id,
            event_id=event["event_id"],
            source_seq=event.get("source_seq", 0),
            source=event.get("source", "console"),
            actor_type=event.get("actor_type", "user"),
            actor_id=event.get("actor_id"),
            thread_id=event.get("thread_id"),
            run_id=event.get("run_id"),
            correlation_id=event.get("correlation_id"),
            operation_type=event["operation_type"],
            status=event["status"],
            occurred_at=event["occurred_at"],
            completed_at=event.get("completed_at"),
            duration_ms=event.get("duration_ms"),
            request_json=event.get("request_json"),
            result_json=event.get("result_json"),
            schema_version=event.get("schema_version", 1),
            output_complete=event.get("output_complete", 1),
            history_storage_state=event.get("history_storage_state", "complete"),
            command=event.get("command"),
            cwd=event.get("cwd"),
            exit_code=event.get("exit_code"),
            environment_json=event.get("environment_json"),
            timeout_ms=event.get("timeout_ms"),
            file_path=event.get("file_path"),
            file_change_type=event.get("file_change_type"),
            before_hash=event.get("before_hash"),
            after_hash=event.get("after_hash"),
            before_size=event.get("before_size"),
            after_size=event.get("after_size"),
        )
        session.add(proj)
    elif event.get("source_seq", 0) > existing.source_seq:
        # Update all fields with newer source_seq (unified _apply_fields).
        _apply_operation_to_projection(existing, event)
    # If source_seq is equal or lower, skip (idempotent).


async def _update_cursor(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    instance_id: str,
    seq: int,
) -> None:
    """Update or create the consumer cursor."""
    result = await session.execute(
        select(ConsumerCursor)
        .where(
            ConsumerCursor.connection_id == connection_id,
            ConsumerCursor.sandbox_id == sandbox_id,
            ConsumerCursor.sandbox_instance_id == instance_id,
        )
    )
    cursor = result.scalar_one_or_none()
    now = _now_iso()

    if cursor is None:
        from app.core.config import get_settings

        settings = get_settings()
        cursor = ConsumerCursor(
            connection_id=connection_id,
            sandbox_id=sandbox_id,
            sandbox_instance_id=instance_id,
            consumer_id=f"console:{settings.deployment_id}",
            acknowledged_seq=seq,
            last_synced_at=now,
        )
        session.add(cursor)
    else:
        cursor.acknowledged_seq = max(cursor.acknowledged_seq, seq)
        cursor.last_synced_at = now


def _apply_operation_to_projection(proj: HistoryProjection, event: dict) -> None:
    """Apply operation fields to a projection (unified for insert and update)."""
    proj.source_seq = event.get("source_seq", proj.source_seq)
    proj.status = event.get("status", proj.status)
    proj.completed_at = event.get("completed_at", proj.completed_at)
    proj.duration_ms = event.get("duration_ms", proj.duration_ms)
    proj.request_json = event.get("request_json", proj.request_json)
    proj.result_json = event.get("result_json", proj.result_json)
    proj.schema_version = event.get("schema_version", proj.schema_version)
    proj.output_complete = event.get("output_complete", proj.output_complete)
    proj.history_storage_state = event.get(
        "history_storage_state", proj.history_storage_state,
    )
    proj.command = event.get("command", proj.command)
    proj.cwd = event.get("cwd", proj.cwd)
    proj.exit_code = event.get("exit_code", proj.exit_code)
    proj.environment_json = event.get("environment_json", proj.environment_json)
    proj.timeout_ms = event.get("timeout_ms", proj.timeout_ms)
    proj.file_path = event.get("file_path", proj.file_path)
    proj.file_change_type = event.get("file_change_type", proj.file_change_type)
    proj.before_hash = event.get("before_hash", proj.before_hash)
    proj.after_hash = event.get("after_hash", proj.after_hash)
    proj.before_size = event.get("before_size", proj.before_size)
    proj.after_size = event.get("after_size", proj.after_size)


async def _update_cursor_with_pending(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    instance_id: str,
    consumer_id: str,
    seq: int,
) -> None:
    """Write pending_seq (committed but not yet ACK'd) — dual cursor."""
    result = await session.execute(
        select(ConsumerCursor)
        .where(
            ConsumerCursor.connection_id == connection_id,
            ConsumerCursor.sandbox_id == sandbox_id,
            ConsumerCursor.sandbox_instance_id == instance_id,
        )
    )
    cursor = result.scalar_one_or_none()
    now = _now_iso()

    if cursor is None:
        cursor = ConsumerCursor(
            connection_id=connection_id,
            sandbox_id=sandbox_id,
            sandbox_instance_id=instance_id,
            consumer_id=consumer_id,
            acknowledged_seq=0,
            pending_seq=seq,
            last_synced_at=now,
        )
        session.add(cursor)
    else:
        cursor.pending_seq = seq
        cursor.last_synced_at = now


async def get_history(
    session: AsyncSession, connection_id: str, sandbox_id: str,
    operation_type: str | None = None,
    status: str | None = None,
    actor_id: str | None = None,
    source: str | None = None,
    limit: int = 100,
) -> HistoryResponse:
    """Get unified history for a sandbox — pure database read, no network sync.

    Merges two sources:
    1. history_projection (synced from sandbox Canonical History) — primary.
    2. console_activities with history_state != "written" — fallback for gaps.

    Use POST /history/sync to trigger a manual sync from the sandbox.
    """
    # Build query for projection (primary source).
    query = (
        select(HistoryProjection)
        .where(
            HistoryProjection.connection_id == connection_id,
            HistoryProjection.sandbox_id == sandbox_id,
        )
    )
    if operation_type is not None:
        query = query.where(HistoryProjection.operation_type == operation_type)
    if status is not None:
        query = query.where(HistoryProjection.status == status)
    if actor_id is not None:
        query = query.where(HistoryProjection.actor_id == actor_id)
    if source is not None:
        query = query.where(HistoryProjection.source == source)

    query = query.order_by(HistoryProjection.occurred_at.desc()).limit(limit)
    result = await session.execute(query)
    projections = result.scalars().all()

    # Collect event_ids from projection for dedup with console_activities.
    projection_event_ids = {p.event_id for p in projections}

    items = [
        HistoryEvent(
            event_id=p.event_id,
            source_seq=p.source_seq,
            source=p.source,
            actor_type=p.actor_type,
            actor_id=p.actor_id,
            thread_id=p.thread_id,
            run_id=p.run_id,
            operation_type=p.operation_type,
            status=p.status,
            occurred_at=p.occurred_at,
            completed_at=p.completed_at,
            duration_ms=p.duration_ms,
            command=p.command,
            cwd=p.cwd,
            exit_code=p.exit_code,
            file_path=p.file_path,
            file_change_type=p.file_change_type,
            output_complete=p.output_complete,
            history_storage_state=p.history_storage_state,
        )
        for p in projections
    ]

    # --- Fallback: query console_activities not yet in projection ---
    # These are activities whose history_state != "written" (pending or failed),
    # meaning they haven't been confirmed in the sandbox's Canonical History yet.
    # We exclude activities that already have an event_id present in the projection.
    fallback_query = (
        select(ConsoleActivity)
        .where(
            ConsoleActivity.connection_id == connection_id,
            ConsoleActivity.sandbox_id == sandbox_id,
            ConsoleActivity.history_state != "written",
        )
    )
    if operation_type is not None:
        fallback_query = fallback_query.where(ConsoleActivity.operation_type == operation_type)
    if status is not None:
        fallback_query = fallback_query.where(ConsoleActivity.status == status)
    if actor_id is not None:
        fallback_query = fallback_query.where(ConsoleActivity.actor_id == actor_id)

    fallback_query = fallback_query.order_by(ConsoleActivity.occurred_at.desc()).limit(limit)
    fallback_result = await session.execute(fallback_query)
    fallback_activities = fallback_result.scalars().all()

    for act in fallback_activities:
        # Skip if this activity's event_id is already in projection (dedup).
        if act.event_id and act.event_id in projection_event_ids:
            continue

        items.append(HistoryEvent(
            event_id=act.event_id or f"console-{act.id}",
            source_seq=0,
            source="console",
            actor_type="user",
            actor_id=act.actor_id,
            thread_id=None,
            run_id=None,
            operation_type=act.operation_type,
            status=act.status,
            occurred_at=act.occurred_at,
            completed_at=act.completed_at,
            duration_ms=act.duration_ms,
            command=act.request_json.get("command") if act.request_json else None,
            cwd=act.request_json.get("cwd") if act.request_json else None,
            exit_code=act.result_json.get("exit_code") if act.result_json else None,
            file_path=act.request_json.get("path") if act.request_json else None,
            file_change_type=None,
            output_complete=1,
            history_storage_state="pending",
        ))

    # Sort merged items by occurred_at descending.
    items.sort(key=lambda e: e.occurred_at, reverse=True)

    # Limit after merge.
    items = items[:limit]

    # Get last_synced_at from cursor.
    cursor_result = await session.execute(
        select(ConsumerCursor)
        .where(
            ConsumerCursor.connection_id == connection_id,
            ConsumerCursor.sandbox_id == sandbox_id,
        )
    )
    cursor = cursor_result.scalar_one_or_none()

    # Determine coverage: if we have a cursor with synced data, coverage is full.
    # Otherwise, only console activities are available.
    if cursor and cursor.last_synced_at:
        coverage = "Connection/Sandbox history"
        history_source = "sandbox"
        helper_status = "available"
    else:
        coverage = "Connection only"
        history_source = "console"
        helper_status = "available"  # Available but not yet synced

    return HistoryResponse(
        coverage=coverage,
        source=history_source,
        helper_status=helper_status,
        items=items,
        total=len(items),
        last_synced_at=cursor.last_synced_at if cursor else None,
    )


async def get_history_event(
    session: AsyncSession, connection_id: str, sandbox_id: str, event_id: str
) -> HistoryEventDetail | None:
    """Get detailed view of a single history event.

    Checks projection first, then falls back to console_activities.
    """
    # Try projection first.
    result = await session.execute(
        select(HistoryProjection)
        .where(
            HistoryProjection.connection_id == connection_id,
            HistoryProjection.sandbox_id == sandbox_id,
            HistoryProjection.event_id == event_id,
        )
    )
    p = result.scalar_one_or_none()

    if p is not None:
        event = HistoryEvent(
            event_id=p.event_id,
            source_seq=p.source_seq,
            source=p.source,
            actor_type=p.actor_type,
            actor_id=p.actor_id,
            thread_id=p.thread_id,
            run_id=p.run_id,
            operation_type=p.operation_type,
            status=p.status,
            occurred_at=p.occurred_at,
            completed_at=p.completed_at,
            duration_ms=p.duration_ms,
            command=p.command,
            cwd=p.cwd,
            exit_code=p.exit_code,
            file_path=p.file_path,
            file_change_type=p.file_change_type,
            output_complete=p.output_complete,
            history_storage_state=p.history_storage_state,
        )

        stdout = None
        stderr = None
        if p.result_json:
            stdout = p.result_json.get("stdout")
            stderr = p.result_json.get("stderr")

        return HistoryEventDetail(
            event=event,
            stdout=stdout,
            stderr=stderr,
            request=p.request_json,
            result=p.result_json,
        )

    # Fallback: try console_activities by event_id or console-{id} format.
    if event_id.startswith("console-"):
        try:
            act_id = int(event_id.split("-", 1)[1])
            act_result = await session.execute(
                select(ConsoleActivity).where(ConsoleActivity.id == act_id)
            )
            act = act_result.scalar_one_or_none()
        except (ValueError, IndexError):
            act = None
    else:
        act_result = await session.execute(
            select(ConsoleActivity).where(
                ConsoleActivity.connection_id == connection_id,
                ConsoleActivity.sandbox_id == sandbox_id,
                ConsoleActivity.event_id == event_id,
            )
        )
        act = act_result.scalar_one_or_none()

    if act is None:
        return None

    event = HistoryEvent(
        event_id=act.event_id or f"console-{act.id}",
        source_seq=0,
        source="console",
        actor_type="user",
        actor_id=act.actor_id,
        thread_id=None,
        run_id=None,
        operation_type=act.operation_type,
        status=act.status,
        occurred_at=act.occurred_at,
        completed_at=act.completed_at,
        duration_ms=act.duration_ms,
        command=act.request_json.get("command") if act.request_json else None,
        cwd=act.request_json.get("cwd") if act.request_json else None,
        exit_code=act.result_json.get("exit_code") if act.result_json else None,
        file_path=act.request_json.get("path") if act.request_json else None,
        file_change_type=None,
        output_complete=1,
        history_storage_state="pending",
    )

    stdout = None
    stderr = None
    if act.result_json:
        stdout = act.result_json.get("stdout")
        stderr = act.result_json.get("stderr")

    return HistoryEventDetail(
        event=event,
        stdout=stdout,
        stderr=stderr,
        request=act.request_json,
        result=act.result_json,
    )


async def get_availability(
    session: AsyncSession, connection_id: str, sandbox_id: str
) -> HistoryAvailability:
    """Check history helper availability for a sandbox."""
    cursor_result = await session.execute(
        select(ConsumerCursor)
        .where(
            ConsumerCursor.connection_id == connection_id,
            ConsumerCursor.sandbox_id == sandbox_id,
        )
    )
    cursor = cursor_result.scalar_one_or_none()

    # Check adapter type — determine history availability.
    _, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
    if isinstance(adapter, (FakeAdapter, OpenSandboxConsoleAdapter)):
        return HistoryAvailability(
            available=True,
            reason=None,
            last_synced_at=cursor.last_synced_at if cursor else None,
        )
    else:
        return HistoryAvailability(
            available=False,
            reason="History Helper is not yet implemented for this connection type",
            last_synced_at=cursor.last_synced_at if cursor else None,
        )
