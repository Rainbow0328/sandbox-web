"""File service: path normalization, symlink checks, and file CRUD."""

from __future__ import annotations

import difflib
import hashlib
import posixpath
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import SandboxAdapter
from app.adapters.base import FileKind, SandboxRef, WriteFileRequest
from app.core.errors import CommandPolicyDeniedError, PathEscapeError, SandboxNotFoundError
from app.gateway.policy import evaluate_file_policy
from app.history.writer import write_operation_to_sandbox_history
from app.models.connection import Connection
from app.models.console_activity import ConsoleActivity
from app.models.policy import ActiveWorkspace, PolicyRule
from app.schemas.file import (
    FileContentResponse,
    FileEntryResponse,
    FileListResponse,
    FileWriteResponse,
)
from app.services.connection_service import build_adapter

# In-memory cache for sandbox_instance_id lookups (avoids repeated list_sandboxes calls).
# Key: "connection_id:sandbox_id" -> sandbox_instance_id
_instance_id_cache: dict[str, str] = {}


def invalidate_instance_id_cache(
    connection_id: str | None = None, sandbox_id: str | None = None
) -> None:
    """Invalidate cached instance_id entries."""
    if connection_id is None:
        _instance_id_cache.clear()
    elif sandbox_id is None:
        # Remove all entries for this connection.
        prefix = f"{connection_id}:"
        keys_to_remove = [k for k in _instance_id_cache if k.startswith(prefix)]
        for k in keys_to_remove:
            del _instance_id_cache[k]
    else:
        _instance_id_cache.pop(f"{connection_id}:{sandbox_id}", None)


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def normalize_path(path: str, workdir: str = "/") -> str:
    """Normalize a POSIX path.

    Paths are normalized with ``posixpath.normpath`` to resolve ``..``
    segments.  When the path is empty or ``/`` it defaults to ``workdir``.
    Relative paths are resolved against ``workdir``.

    Unlike a strict jail, this function allows browsing any absolute path
    so users can explore the full filesystem (e.g. ``/home``, ``/etc``)
    when a sandbox was created externally with a custom working directory.

    However, ``..`` segments in the *original* path are rejected to prevent
    path traversal attacks.  Users can still access any directory by
    specifying its absolute path directly.
    """
    if not path or path == "/":
        return workdir

    # Reject paths containing .. segments to prevent traversal attacks.
    # Users should specify absolute paths directly instead.
    parts = path.split("/")
    if ".." in parts:
        raise PathEscapeError(
            f"Path '{path}' contains '..' segments",
            details={"path": path},
        )

    # Ensure path is absolute.
    if not path.startswith("/"):
        path = posixpath.join(workdir, path)

    normalized = posixpath.normpath(path)

    # Guard against trivial escape (e.g. "/../../etc") — normpath already
    # collapses leading ``..`` so the result always starts with ``/``.
    if not normalized.startswith("/"):
        normalized = "/" + normalized

    return normalized


async def get_sandbox_ref(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
) -> tuple[SandboxRef, SandboxAdapter, Connection]:
    """Resolve a (connection_id, sandbox_id) to a SandboxRef + adapter + connection.

    This is a shared helper used by file_service, command_service, etc.
    Uses an in-memory cache for sandbox_instance_id to avoid repeated list calls.
    """
    result = await session.execute(select(Connection).where(Connection.id == connection_id))
    connection = result.scalar_one_or_none()
    if connection is None:
        raise SandboxNotFoundError(
            f"Connection {connection_id} not found",
            details={"connection_id": connection_id},
        )

    adapter = build_adapter(connection)

    # Resolve the real sandbox_instance_id.
    # Use cache to avoid repeated list_sandboxes() calls.
    cache_key = f"{connection_id}:{sandbox_id}"
    instance_id = _instance_id_cache.get(cache_key)
    if instance_id is None:
        instance_id = sandbox_id
        if hasattr(adapter, "list_sandboxes"):
            try:
                sandboxes = await adapter.list_sandboxes()
                for sb in sandboxes:
                    if sb.ref.sandbox_id == sandbox_id:
                        instance_id = sb.ref.sandbox_instance_id
                        break
            except Exception:
                pass  # Fall back to sandbox_id if list fails.
        _instance_id_cache[cache_key] = instance_id

    ref = SandboxRef(
        provider_name=connection.name,
        provider_key=connection.id,
        sandbox_id=sandbox_id,
        sandbox_instance_id=instance_id,
    )
    return ref, adapter, connection


async def _log_activity(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    actor_id: str,
    operation_type: str,
    status: str,
    request: dict | None = None,
    result: dict | None = None,
    duration_ms: int | None = None,
    event_id: str | None = None,
    history_state: str = "pending",
) -> ConsoleActivity:
    """Write a console_activities row and return the ORM instance.

    ``event_id`` links this activity to the sandbox's Canonical History event.
    ``history_state`` tracks the write-to-sandbox-history lifecycle:
      - ``pending``: write not yet attempted
      - ``written``: successfully written to sandbox SQLite
      - ``failed``: write attempted but failed
    """
    activity = ConsoleActivity(
        connection_id=connection_id,
        sandbox_id=sandbox_id,
        actor_id=actor_id,
        operation_type=operation_type,
        status=status,
        request_json=request,
        result_json=result,
        occurred_at=_now_iso(),
        completed_at=_now_iso(),
        duration_ms=duration_ms,
        event_id=event_id,
        history_state=history_state,
    )
    session.add(activity)
    await session.commit()
    return activity


async def list_files(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    path: str,
    actor_id: str = "admin",
) -> FileListResponse:
    """List files in a directory."""
    ref, adapter, connection = await get_sandbox_ref(session, connection_id, sandbox_id)
    workdir = connection.default_workdir or "/"
    norm_path = normalize_path(path, workdir)

    # Policy check
    rules = await _load_rules_for_sandbox(session, sandbox_id)
    decision = evaluate_file_policy(
        path=norm_path, operation="file.list", actor_id=actor_id, rules=rules,
    )
    if decision.result == "deny":
        raise CommandPolicyDeniedError(decision.reason)

    # Gracefully handle non-existent directories: return an empty list
    # instead of propagating a 500 error.
    try:
        entries = await adapter.list_files(ref, norm_path)
    except Exception:
        entries = []

    # NOTE: file.list is a read-only operation — not logged to history.

    return FileListResponse(
        path=norm_path,
        entries=[
            FileEntryResponse(
                path=e.path,
                kind=e.kind if isinstance(e.kind, FileKind) else FileKind(e.kind),
                size=e.size,
                content_hash=e.content_hash,
            )
            for e in entries
        ],
    )


async def read_file(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    path: str,
    actor_id: str = "admin",
) -> FileContentResponse:
    """Read file content."""
    ref, adapter, connection = await get_sandbox_ref(session, connection_id, sandbox_id)
    workdir = connection.default_workdir or "/"
    norm_path = normalize_path(path, workdir)

    # Policy check
    rules = await _load_rules_for_sandbox(session, sandbox_id)
    decision = evaluate_file_policy(
        path=norm_path, operation="file.read", actor_id=actor_id, rules=rules,
    )
    if decision.result == "deny":
        raise CommandPolicyDeniedError(decision.reason)

    content_bytes = await adapter.read_file(ref, norm_path)
    content_hash = hashlib.sha256(content_bytes).hexdigest()

    # Try to decode as UTF-8; if it fails, mark as binary.
    try:
        content_text = content_bytes.decode("utf-8")
        is_binary = False
    except UnicodeDecodeError:
        content_text = ""
        is_binary = True

    # NOTE: file.read is a read-only operation — not logged to history.

    return FileContentResponse(
        path=norm_path,
        content=content_text,
        content_hash=content_hash,
        size=len(content_bytes),
        is_binary=is_binary,
    )


async def write_file(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    path: str,
    content: str,
    expected_hash: str | None = None,
    actor_id: str = "admin",
) -> FileWriteResponse:
    """Write file content with optimistic concurrency control."""
    ref, adapter, connection = await get_sandbox_ref(session, connection_id, sandbox_id)
    workdir = connection.default_workdir or "/"
    norm_path = normalize_path(path, workdir)

    # Policy check
    rules = await _load_rules_for_sandbox(session, sandbox_id)
    decision = evaluate_file_policy(
        path=norm_path, operation="file.write", actor_id=actor_id, rules=rules,
    )
    if decision.result == "deny":
        raise CommandPolicyDeniedError(decision.reason)

    content_bytes = content.encode("utf-8")
    request = WriteFileRequest(
        path=norm_path,
        content=content_bytes,
        expected_hash=expected_hash,
    )

    # For edits (expected_hash is set), read old content to generate
    # a unified diff instead of recording the full file content.
    is_edit = expected_hash is not None
    diff_text: str | None = None
    diff_truncated = False
    if is_edit:
        try:
            old_bytes = await adapter.read_file(ref, norm_path)
            try:
                old_text = old_bytes.decode("utf-8")
                new_text = content
                diff_lines = list(
                    difflib.unified_diff(
                        old_text.splitlines(keepends=True),
                        new_text.splitlines(keepends=True),
                        fromfile=f"{norm_path} (before)",
                        tofile=f"{norm_path} (after)",
                    )
                )
                if diff_lines:
                    # Ensure every line ends with \n — difflib omits trailing
                    # \n on the last content line when the source text doesn't
                    # end with a newline, causing lines like "-hello+world"
                    # to concatenate.
                    diff_text = "".join(
                        line if line.endswith("\n") else line + "\n"
                        for line in diff_lines
                    )
                    _MAX_DIFF = 65536
                    diff_truncated = len(diff_text.encode("utf-8")) > _MAX_DIFF
                    if diff_truncated:
                        diff_text = diff_text[:_MAX_DIFF]
                        diff_text += "\n... [diff truncated]\n"
            except UnicodeDecodeError:
                pass  # Binary file, skip diff.
        except Exception:
            pass  # File may not exist yet; skip diff.

    result = await adapter.write_file(ref, request)

    # Log activity — history_state stays "pending" until history writer updates it.
    _MAX_CONTENT_PREVIEW = 10_000

    # Build result payload: include diff for edits, content preview for new files.
    result_payload: dict = {
        "hash": result.entry.content_hash,
        "previous_hash": result.previous_hash,
        "after_hash": result.entry.content_hash,
        "after_size": len(content_bytes),
        "before_hash": result.previous_hash,
    }
    if is_edit and diff_text:
        result_payload["diff"] = diff_text
        result_payload["diff_truncated"] = diff_truncated
    else:
        result_payload["content"] = content[:_MAX_CONTENT_PREVIEW]
        result_payload["content_truncated"] = len(content) > _MAX_CONTENT_PREVIEW
        result_payload["content_size"] = len(content)

    activity = await _log_activity(
        session, connection_id, sandbox_id, actor_id,
        "file.write", "succeeded",
        {"path": norm_path, "expected_hash": expected_hash},
        result_payload,
    )

    # Best-effort write to sandbox history.
    await write_operation_to_sandbox_history(
        session, ref, adapter, activity,
        operation_type="file.write",
        status="succeeded",
        request_payload={"path": norm_path, "expected_hash": expected_hash},
        result_payload=result_payload,
        file_path=norm_path,
        file_change_type="write",
        before_hash=result.previous_hash,
        after_hash=result.entry.content_hash,
        after_size=len(content_bytes),
    )

    return FileWriteResponse(
        path=norm_path,
        content_hash=result.entry.content_hash,
        size=len(content_bytes),
        previous_hash=result.previous_hash,
    )


async def delete_file(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    path: str,
    actor_id: str = "admin",
) -> None:
    """Delete a file."""
    ref, adapter, connection = await get_sandbox_ref(session, connection_id, sandbox_id)
    workdir = connection.default_workdir or "/"
    norm_path = normalize_path(path, workdir)

    # Policy check
    rules = await _load_rules_for_sandbox(session, sandbox_id)
    decision = evaluate_file_policy(
        path=norm_path, operation="file.delete", actor_id=actor_id, rules=rules,
    )
    if decision.result == "deny":
        raise CommandPolicyDeniedError(decision.reason)

    await adapter.delete_file(ref, norm_path)

    activity = await _log_activity(
        session, connection_id, sandbox_id, actor_id,
        "file.delete", "succeeded", {"path": norm_path},
    )

    # Best-effort write to sandbox history.
    await write_operation_to_sandbox_history(
        session, ref, adapter, activity,
        operation_type="file.delete",
        status="succeeded",
        request_payload={"path": norm_path},
        file_path=norm_path,
        file_change_type="delete",
    )


async def download_file(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    path: str,
) -> tuple[bytes, str, int]:
    """Download a file as raw bytes. Returns (content, hash, size)."""
    ref, adapter, connection = await get_sandbox_ref(session, connection_id, sandbox_id)
    workdir = connection.default_workdir or "/"
    norm_path = normalize_path(path, workdir)

    content = await adapter.read_file(ref, norm_path)
    content_hash = hashlib.sha256(content).hexdigest()
    return content, content_hash, len(content)


async def upload_file(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    path: str,
    content: bytes,
    actor_id: str = "admin",
) -> FileWriteResponse:
    """Upload a file (binary content)."""
    ref, adapter, connection = await get_sandbox_ref(session, connection_id, sandbox_id)
    workdir = connection.default_workdir or "/"
    norm_path = normalize_path(path, workdir)

    request = WriteFileRequest(path=norm_path, content=content)
    result = await adapter.write_file(ref, request)

    activity = await _log_activity(
        session, connection_id, sandbox_id, actor_id,
        "file.upload", "succeeded",
        {"path": norm_path, "size": len(content)},
        {"hash": result.entry.content_hash},
    )

    # Best-effort write to sandbox history.
    await write_operation_to_sandbox_history(
        session, ref, adapter, activity,
        operation_type="file.upload",
        status="succeeded",
        request_payload={"path": norm_path, "size": len(content)},
        result_payload={"hash": result.entry.content_hash},
        file_path=norm_path,
        file_change_type="upload",
        after_hash=result.entry.content_hash,
        after_size=len(content),
    )

    return FileWriteResponse(
        path=norm_path,
        content_hash=result.entry.content_hash,
        size=len(content),
        previous_hash=result.previous_hash,
    )


async def _load_rules_for_sandbox(
    session: AsyncSession,
    sandbox_id: str,
) -> list[dict]:
    """Load policy rules applicable to a sandbox.

    Returns group-level rules + sandbox-level overrides.
    """
    ws_result = await session.execute(
        select(ActiveWorkspace).where(
            ActiveWorkspace.sandbox_id == sandbox_id,
            ActiveWorkspace.active == True,  # noqa: E712
        )
    )
    ws = ws_result.scalar_one_or_none()
    if ws is None or ws.group_id is None:
        return []

    rules_result = await session.execute(
        select(PolicyRule)
        .where(
            PolicyRule.group_id == ws.group_id,
            (PolicyRule.sandbox_id.is_(None)) | (PolicyRule.sandbox_id == sandbox_id),
        )
        .order_by(PolicyRule.priority.desc())
    )
    rules = rules_result.scalars().all()
    return [
        {
            "id": r.id,
            "rule_type": r.rule_type,
            "pattern": r.pattern,
            "effect": r.effect,
            "operations": r.operations,
            "priority": r.priority,
            "description": r.description,
        }
        for r in rules
    ]
