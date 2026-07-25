"""Command service: foreground/background execution and result storage."""

from __future__ import annotations

import asyncio
import secrets
import time
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import ExecRequest
from app.core.config import get_settings
from app.core.errors import CommandPolicyDeniedError
from app.gateway.policy import evaluate_command_policy
from app.history.writer import write_operation_to_sandbox_history
from app.schemas.command import (
    CommandCreateRequest,
    CommandCreateResponse,
    CommandResponse,
    CommandStatus,
)
from app.services.file_service import _log_activity, get_sandbox_ref

# In-memory store for command results (v0.1: no persistence needed for
# foreground commands; background commands are also short-lived with FakeAdapter).
_command_store: dict[str, CommandResponse] = {}

# In-memory event queues for SSE streaming: command_id -> list of events.
_event_queues: dict[str, list[dict]] = {}


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _gen_command_id() -> str:
    return f"cmd-{secrets.token_hex(12)}"


async def execute_command(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    request: CommandCreateRequest,
    actor_id: str = "admin",
) -> CommandCreateResponse:
    """Execute a command and store the result.

    For v0.1 with FakeAdapter, both foreground and background modes execute
    synchronously and store the full result. The SSE endpoint replays events
    from the store.
    """
    ref, adapter, connection = await get_sandbox_ref(session, connection_id, sandbox_id)

    command_id = _gen_command_id()
    cwd = request.cwd or connection.default_workdir or "/"

    settings = get_settings()
    timeout = request.timeout_seconds or settings.command_default_timeout_seconds

    # Evaluate command policy (§9.3, §15.4) — v0.1 defaults to allow.
    decision = evaluate_command_policy(
        command=request.command, cwd=cwd, actor_id=actor_id,
    )
    if decision.result == "deny":
        await _log_activity(
            session, connection_id, sandbox_id, actor_id,
            "command.finish", "denied",
            {"command": request.command, "reason": decision.reason},
        )
        raise CommandPolicyDeniedError(decision.reason)

    # Build exec request.
    exec_request = ExecRequest(
        command=request.command,
        cwd=cwd,
        env=request.env,
        timeout_seconds=timeout,
    )

    # Initialize event queue for SSE.
    _event_queues[command_id] = []

    # Execute — use execute_stream if available (real-time output via callback),
    # otherwise fall back to synchronous execute (FakeAdapter).
    start = time.time()
    try:
        if hasattr(adapter, "execute_stream"):
            # Real-time streaming: callback pushes events as they arrive.
            stdout_parts: list[bytes] = []
            stderr_parts: list[bytes] = []

            async def _on_output(stream: str, data: bytes) -> None:
                _event_queues[command_id].append({
                    "type": "output",
                    "stream": stream,
                    "data": data.decode("utf-8", errors="replace"),
                })
                if stream == "stdout":
                    stdout_parts.append(data)
                else:
                    stderr_parts.append(data)

            result = await asyncio.wait_for(
                adapter.execute_stream(ref, exec_request, _on_output),
                timeout=timeout,
            )
        else:
            # Synchronous execution (FakeAdapter).
            result = await asyncio.wait_for(
                adapter.execute(ref, exec_request),
                timeout=timeout,
            )
            # Push buffered output for SSE replay.
            if result.stdout:
                _event_queues[command_id].append({
                    "type": "output", "stream": "stdout",
                    "data": result.stdout_text,
                })
            if result.stderr:
                _event_queues[command_id].append({
                    "type": "output", "stream": "stderr",
                    "data": result.stderr_text,
                })

        duration_ms = int((time.time() - start) * 1000)

        status = CommandStatus.SUCCEEDED if result.exit_code == 0 else CommandStatus.FAILED

        # Push finished event.
        _event_queues[command_id].append({
            "type": "finished",
            "exit_code": result.exit_code,
            "duration_ms": duration_ms,
            "status": status.value,
        })

        response = CommandResponse(
            command_id=command_id,
            remote_command_id=result.command_id,
            status=status,
            exit_code=result.exit_code,
            duration_ms=duration_ms,
            stdout=result.stdout_text,
            stderr=result.stderr_text,
            command=request.command,
            cwd=cwd,
            mode=request.mode,
        )

    except TimeoutError:
        duration_ms = int((time.time() - start) * 1000)
        _event_queues[command_id].append({"type": "timeout", "duration_ms": duration_ms})
        response = CommandResponse(
            command_id=command_id,
            status=CommandStatus.TIMEOUT,
            duration_ms=duration_ms,
            command=request.command,
            cwd=cwd,
            mode=request.mode,
        )

    # Store result.
    _command_store[command_id] = response

    # Truncate output for storage (10KB limit per stream).
    _MAX_OUTPUT = 10_000
    stdout_preview = (response.stdout or "")[:_MAX_OUTPUT]
    stderr_preview = (response.stderr or "")[:_MAX_OUTPUT]
    output_truncated = (
        len(response.stdout or "") > _MAX_OUTPUT
        or len(response.stderr or "") > _MAX_OUTPUT
    )

    # Log command finish — history_state stays "pending" until history writer updates it.
    activity = await _log_activity(
        session, connection_id, sandbox_id, actor_id,
        "command.finish", response.status.value,
        {"command": request.command, "cwd": cwd},
        {
            "exit_code": response.exit_code,
            "duration_ms": response.duration_ms,
            "stdout": stdout_preview,
            "stderr": stderr_preview,
            "output_truncated": output_truncated,
        },
        duration_ms=response.duration_ms,
    )

    # Best-effort write to sandbox history.
    await write_operation_to_sandbox_history(
        session, ref, adapter, activity,
        operation_type="command.finish",
        status=response.status.value,
        request_payload={"command": request.command, "cwd": cwd},
        result_payload={
            "exit_code": response.exit_code,
            "duration_ms": response.duration_ms,
            "stdout": stdout_preview,
            "stderr": stderr_preview,
            "output_truncated": output_truncated,
        },
        command=request.command,
        cwd=cwd,
        exit_code=response.exit_code,
        duration_ms=response.duration_ms,
    )

    return CommandCreateResponse(
        command_id=command_id,
        status=response.status,
        mode=request.mode,
    )


async def get_command(command_id: str) -> CommandResponse | None:
    """Get a command's status and result by ID."""
    return _command_store.get(command_id)


def get_command_events(command_id: str) -> list[dict]:
    """Get all buffered SSE events for a command (for replay)."""
    return _event_queues.get(command_id, [])


def has_command_events(command_id: str) -> bool:
    """Check if a command has an event queue."""
    return command_id in _event_queues
