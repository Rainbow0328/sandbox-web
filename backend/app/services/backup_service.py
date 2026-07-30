"""Backup service: delegates to the sandbox's history store for file backups.

The backup data lives inside the sandbox's own ``history.sqlite3`` database,
shared between the SDK and the Console via the ``SandboxHistoryStore``.
This service uses the cached store pool to avoid re-installing the helper
on every request.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.history.store_pool import get_history_store
from app.schemas.backup import (
    BackupBatchDeleteResponse,
    BackupCreateRequest,
    BackupCreateResponse,
    BackupDeleteByPathResponse,
    BackupDeleteResponse,
    BackupDetail,
    BackupDiffResponse,
    BackupFileListResponse,
    BackupItem,
    BackupListResponse,
    BackupRestoreResponse,
)
from app.services.file_service import get_sandbox_ref

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory diff cache:  { backup_id -> (timestamp, BackupDiffResponse) }
# ---------------------------------------------------------------------------
_diff_cache: dict[str, tuple[float, BackupDiffResponse]] = {}
_DIFF_CACHE_TTL = 300  # 5 minutes


async def list_backups(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    *,
    file_path: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> BackupListResponse:
    """List file backups for a sandbox."""
    try:
        ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
        store = await get_history_store(
            adapter, ref,
            connection_id=ref.provider_key,
            sandbox_id=ref.sandbox_id,
        )
        if store is None:
            return BackupListResponse(backups=[], total=0, limit=limit, offset=offset)
        result = await store.backup_list(
            file_path=file_path, limit=limit, offset=offset,
        )
        backups = [
            BackupItem(
                backup_id=b.get("backup_id", ""),
                file_path=b.get("file_path", ""),
                content_hash=b.get("content_hash", ""),
                content_size=int(b.get("content_size", 0)),
                encoding=b.get("encoding", "identity"),
                original_size=int(b.get("original_size", 0)),
                description=b.get("description", ""),
                trigger_type=b.get("trigger_type", "manual"),
                rule_name=b.get("rule_name"),
                actor_type=b.get("actor_type", "system"),
                actor_id=b.get("actor_id"),
                command=b.get("command"),
                created_at=b.get("created_at", ""),
            )
            for b in result.get("backups", [])
        ]
        return BackupListResponse(
            backups=backups,
            total=int(result.get("total", 0)),
            limit=int(result.get("limit", limit)),
            offset=int(result.get("offset", offset)),
        )
    except Exception as exc:
        logger.warning("Failed to list backups: %s", exc, exc_info=True)
        return BackupListResponse(backups=[], total=0, limit=limit, offset=offset)


async def list_backup_files(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
) -> BackupFileListResponse:
    """List distinct file paths that have backups."""
    try:
        ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
        store = await get_history_store(
            adapter, ref,
            connection_id=ref.provider_key,
            sandbox_id=ref.sandbox_id,
        )
        if store is None:
            return BackupFileListResponse(files=[], total=0)
        result = await store.backup_list_files()
        return BackupFileListResponse(
            files=result.get("files", []),
            total=int(result.get("total", 0)),
        )
    except Exception as exc:
        logger.warning("Failed to list backup files: %s", exc, exc_info=True)
        return BackupFileListResponse(files=[], total=0)


async def get_backup(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    backup_id: str,
    *,
    include_content: bool = True,
) -> BackupDetail | None:
    """Get a single backup by ID."""
    try:
        ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
        store = await get_history_store(
            adapter, ref,
            connection_id=ref.provider_key,
            sandbox_id=ref.sandbox_id,
        )
        if store is None:
            return None
        result = await store.backup_get(backup_id, include_content=include_content)
        if not result:
            return None
        return BackupDetail(
            backup_id=result.get("backup_id", ""),
            file_path=result.get("file_path", ""),
            content_hash=result.get("content_hash", ""),
            content_size=int(result.get("content_size", 0)),
            encoding=result.get("encoding", "identity"),
            original_size=int(result.get("original_size", 0)),
            description=result.get("description", ""),
            trigger_type=result.get("trigger_type", "manual"),
            rule_name=result.get("rule_name"),
            actor_type=result.get("actor_type", "system"),
            actor_id=result.get("actor_id"),
            command=result.get("command"),
            created_at=result.get("created_at", ""),
            content_base64=result.get("content_base64"),
        )
    except Exception as exc:
        logger.warning("Failed to get backup %s: %s", backup_id, exc, exc_info=True)
        return None


async def create_backup(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    request: BackupCreateRequest,
) -> BackupCreateResponse:
    """Create a manual backup of a file.

    Reads the file content from the sandbox via the adapter, then stores
    it as a backup record in the sandbox's history database.
    """
    import base64
    import hashlib
    from datetime import UTC, datetime

    from agent_sandbox_backends._internal.ids import uuid7

    try:
        ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)

        # Read file content via adapter.
        content = await adapter.read_file(ref, request.file_path)

        content_hash = hashlib.sha256(content).hexdigest()
        content_b64 = base64.b64encode(content).decode("ascii")
        backup_id = str(uuid7())
        created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")

        store = await get_history_store(
            adapter, ref,
            connection_id=ref.provider_key,
            sandbox_id=ref.sandbox_id,
        )
        if store is None:
            return BackupCreateResponse(
                backup_id=None,
                file_path=request.file_path,
                created=False,
                message="History store unavailable",
            )

        payload: dict[str, Any] = {
            "backup_id": backup_id,
            "file_path": request.file_path,
            "content_base64": content_b64,
            "content_hash": content_hash,
            "content_size": len(content),
            "created_at": created_at,
            "encoding": "identity",
            "original_size": len(content),
            "description": request.description or "manual backup",
            "trigger_type": "manual",
            "rule_name": "manual",
            "actor_type": "user",
            "actor_id": "console",
            "command": None,
            "max_backups_per_file": 15,
        }
        await store.backup_create(payload)
        return BackupCreateResponse(
            backup_id=backup_id,
            file_path=request.file_path,
            created=True,
        )
    except Exception as exc:
        logger.warning("Failed to create backup: %s", exc, exc_info=True)
        return BackupCreateResponse(
            backup_id=None,
            file_path=request.file_path,
            created=False,
            message=str(exc),
        )


async def restore_backup(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    backup_id: str,
) -> BackupRestoreResponse | None:
    """Restore (roll back) a file from a backup.

    Before overwriting the file, this function attempts to read the
    current file content and creates a ``pre_restore`` backup so the
    user can undo the rollback if needed.

    Optimization: if the current file content already matches an existing
    backup (i.e., the user is undoing a previous rollback), no new
    pre_restore backup is created — the existing backup already preserves
    that version.
    """
    import base64
    import hashlib
    from datetime import UTC, datetime

    from agent_sandbox_backends._internal.ids import uuid7

    from app.adapters.base import WriteFileRequest

    try:
        ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
        store = await get_history_store(
            adapter, ref,
            connection_id=ref.provider_key,
            sandbox_id=ref.sandbox_id,
        )
        if store is None:
            return None

        # 1. Fetch the target backup content.
        result = await store.backup_get_content(backup_id)
        if not result:
            return None
        content = base64.b64decode(result["content_base64"], validate=True)
        file_path = result["file_path"]

        # 2. Safety net: try to snapshot the *current* file before overwriting.
        pre_restore_backup_id: str | None = None
        try:
            current_content = await adapter.read_file(ref, file_path)
            current_hash = hashlib.sha256(current_content).hexdigest()
            target_hash = result.get("content_hash", "")
            # Only snapshot if the current content differs from the target backup.
            if current_hash != target_hash:
                # Check if the current content already exists as a backup.
                # This happens when undoing a rollback — the "current" version
                # was already saved as a previous backup, so no need to duplicate.
                existing = await store.backup_list(
                    file_path=file_path, limit=500,
                )
                already_backed_up = any(
                    b.get("content_hash") == current_hash
                    for b in existing.get("backups", [])
                )
                if not already_backed_up:
                    pre_restore_backup_id = str(uuid7())
                    now_iso = datetime.now(UTC).isoformat().replace("+00:00", "Z")
                    pre_payload: dict[str, Any] = {
                        "backup_id": pre_restore_backup_id,
                        "file_path": file_path,
                        "content_base64": base64.b64encode(current_content).decode("ascii"),
                        "content_hash": current_hash,
                        "content_size": len(current_content),
                        "created_at": now_iso,
                        "encoding": "identity",
                        "original_size": len(current_content),
                        "description": f"回滚前自动备份 (restore target: {backup_id})",
                        "trigger_type": "pre_restore",
                        "rule_name": "system",
                        "actor_type": "user",
                        "actor_id": "console",
                        "command": None,
                        "max_backups_per_file": 15,
                    }
                    await store.backup_create(pre_payload)
        except Exception:
            # File might not exist yet — that's fine, no snapshot needed.
            logger.debug("Pre-restore snapshot skipped for %s", file_path, exc_info=True)

        # 3. Write the backup content back to the sandbox.
        write_request = WriteFileRequest(path=file_path, content=content)
        await adapter.write_file(ref, write_request)

        message = "文件已回滚到选定备份版本"
        if pre_restore_backup_id:
            message += f"，回滚前已自动创建备份 ({pre_restore_backup_id[:8]}…)"

        return BackupRestoreResponse(
            backup_id=backup_id,
            file_path=file_path,
            content_hash=result.get("content_hash", ""),
            content_size=int(result.get("content_size", 0)),
            restored=True,
            pre_restore_backup_id=pre_restore_backup_id,
            message=message,
        )
    except Exception as exc:
        logger.warning("Failed to restore backup %s: %s", backup_id, exc, exc_info=True)
        return None


async def get_backup_diff(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    backup_id: str,
    *,
    side_by_side: bool = False,
) -> BackupDiffResponse | None:
    """Compute a git-style unified diff between a backup and the next version.

    The "next version" is:
      - The content of the next backup (by created_at) for the same file, if one exists.
      - The current file content, if this is the latest backup.

    Results are cached in-memory for ``_DIFF_CACHE_TTL`` seconds to avoid
    recomputing on every request.

    If ``side_by_side`` is True, the response also includes ``old_text`` and
    ``new_text`` so the frontend can render a two-column diff view.
    """
    import base64
    import difflib
    import hashlib

    cache_key = f"{backup_id}:{side_by_side}"
    cached = _diff_cache.get(cache_key)
    if cached and (time.time() - cached[0]) < _DIFF_CACHE_TTL:
        return cached[1]

    try:
        ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
        store = await get_history_store(
            adapter, ref,
            connection_id=ref.provider_key,
            sandbox_id=ref.sandbox_id,
        )
        if store is None:
            return None

        # 1. Get the target backup.
        backup = await store.backup_get(backup_id, include_content=True)
        if not backup:
            return None
        file_path = backup.get("file_path", "")
        backup_content = base64.b64decode(backup["content_base64"], validate=True)
        backup_hash = backup.get("content_hash", "")
        backup_created_at = backup.get("created_at", "")

        # 2. Find the next backup for the same file (created after this one).
        all_backups = await store.backup_list(file_path=file_path, limit=500)
        backups_list = all_backups.get("backups", [])
        # Sort by created_at ascending.
        backups_list.sort(key=lambda b: b.get("created_at", ""))

        next_backup = None
        for b in backups_list:
            if b.get("created_at", "") > backup_created_at:
                next_backup = b
                break

        # 3. Determine the "next" content.
        if next_backup is not None:
            # Fetch the next backup's content.
            next_detail = await store.backup_get(
                next_backup["backup_id"], include_content=True,
            )
            if not next_detail:
                return None
            next_content = base64.b64decode(
                next_detail["content_base64"], validate=True,
            )
            comparison_source = f"next backup {next_backup['backup_id'][:8]}…"
            is_latest = False
        else:
            # This is the latest backup — compare with current file content.
            try:
                next_content = await adapter.read_file(ref, file_path)
            except Exception:
                # File may have been deleted.
                return BackupDiffResponse(
                    backup_id=backup_id,
                    file_path=file_path,
                    diff=None,
                    has_diff=False,
                    comparison_source="file deleted",
                    is_binary=False,
                    is_latest=True,
                )
            comparison_source = "current file"
            is_latest = True

        # 4. Check if content is identical (no diff).
        next_hash = hashlib.sha256(next_content).hexdigest() if next_content else ""
        if backup_hash == next_hash:
            return BackupDiffResponse(
                backup_id=backup_id,
                file_path=file_path,
                diff=None,
                has_diff=False,
                comparison_source=comparison_source,
                is_binary=False,
                is_latest=is_latest,
            )

        # 5. Try to decode as UTF-8 for text diff.
        try:
            old_text = backup_content.decode("utf-8")
            new_text = next_content.decode("utf-8")
        except UnicodeDecodeError:
            return BackupDiffResponse(
                backup_id=backup_id,
                file_path=file_path,
                diff=None,
                has_diff=False,
                comparison_source=comparison_source,
                is_binary=True,
                is_latest=is_latest,
            )

        # 6. Compute unified diff.
        diff_lines = list(
            difflib.unified_diff(
                old_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"{file_path} (backup)",
                tofile=f"{file_path} ({comparison_source})",
            )
        )
        if diff_lines:
            diff_text = "".join(
                line if line.endswith("\n") else line + "\n"
                for line in diff_lines
            )
        else:
            diff_text = None

        response = BackupDiffResponse(
            backup_id=backup_id,
            file_path=file_path,
            diff=diff_text,
            has_diff=diff_text is not None,
            comparison_source=comparison_source,
            is_binary=False,
            is_latest=is_latest,
            old_text=old_text if side_by_side else None,
            new_text=new_text if side_by_side else None,
        )
        _diff_cache[cache_key] = (time.time(), response)
        return response
    except Exception as exc:
        logger.warning("Failed to get backup diff %s: %s", backup_id, exc, exc_info=True)
        return None


async def delete_backup(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    backup_id: str,
) -> BackupDeleteResponse | None:
    """Delete a single backup by ID."""
    try:
        ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
        store = await get_history_store(
            adapter, ref,
            connection_id=ref.provider_key,
            sandbox_id=ref.sandbox_id,
        )
        if store is None:
            return None
        result = await store.backup_delete(backup_id)
        return BackupDeleteResponse(
            backup_id=backup_id,
            deleted=bool(result.get("deleted")),
        )
    except Exception as exc:
        logger.warning("Failed to delete backup %s: %s", backup_id, exc, exc_info=True)
        return None


async def delete_backups_by_path(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    file_path: str,
) -> BackupDeleteByPathResponse | None:
    """Delete all backups for a given file path."""
    try:
        ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
        store = await get_history_store(
            adapter, ref,
            connection_id=ref.provider_key,
            sandbox_id=ref.sandbox_id,
        )
        if store is None:
            return None
        result = await store.backup_delete_by_path(file_path)
        return BackupDeleteByPathResponse(
            file_path=file_path,
            deleted=int(result.get("deleted", 0)),
        )
    except Exception as exc:
        logger.warning("Failed to delete backups for %s: %s", file_path, exc, exc_info=True)
        return None


async def batch_delete_backups(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    backup_ids: list[str],
) -> BackupBatchDeleteResponse:
    """Delete multiple backups by ID in a single call."""
    deleted = 0
    failed = 0
    details: list[dict[str, Any]] = []
    try:
        ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
        store = await get_history_store(
            adapter, ref,
            connection_id=ref.provider_key,
            sandbox_id=ref.sandbox_id,
        )
        if store is None:
            return BackupBatchDeleteResponse(deleted=0, failed=len(backup_ids))
        for bid in backup_ids:
            try:
                result = await store.backup_delete(bid)
                ok = bool(result.get("deleted"))
                if ok:
                    deleted += 1
                else:
                    failed += 1
                details.append({"backup_id": bid, "deleted": ok})
            except Exception as exc:
                failed += 1
                details.append({"backup_id": bid, "deleted": False, "error": str(exc)})
        return BackupBatchDeleteResponse(deleted=deleted, failed=failed, details=details)
    except Exception as exc:
        logger.warning("Failed to batch delete backups: %s", exc, exc_info=True)
        return BackupBatchDeleteResponse(deleted=deleted, failed=len(backup_ids) - deleted)


async def get_backup_content(
    session: AsyncSession,
    connection_id: str,
    sandbox_id: str,
    backup_id: str,
) -> tuple[bytes, str, str] | None:
    """Return (content_bytes, file_path, content_hash) for a backup.

    Used for backup export (download).
    """
    import base64

    try:
        ref, adapter, _ = await get_sandbox_ref(session, connection_id, sandbox_id)
        store = await get_history_store(
            adapter, ref,
            connection_id=ref.provider_key,
            sandbox_id=ref.sandbox_id,
        )
        if store is None:
            return None
        result = await store.backup_get(backup_id, include_content=True)
        if not result:
            return None
        content = base64.b64decode(result["content_base64"], validate=True)
        file_path = result.get("file_path", "backup")
        content_hash = result.get("content_hash", "")
        return (content, file_path, content_hash)
    except Exception as exc:
        logger.warning("Failed to get backup content %s: %s", backup_id, exc, exc_info=True)
        return None
