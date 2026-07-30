"""Backup routes: list, get, create, restore, delete, diff, export file backups."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response

from app.core.deps import ActorDep, SessionDep
from app.schemas.backup import (
    BackupBatchDeleteRequest,
    BackupBatchDeleteResponse,
    BackupCreateRequest,
    BackupCreateResponse,
    BackupDeleteByPathResponse,
    BackupDeleteResponse,
    BackupDetail,
    BackupDiffResponse,
    BackupFileListResponse,
    BackupListResponse,
    BackupRestoreResponse,
)
from app.services import backup_service

router = APIRouter(tags=["backups"])


@router.get(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/backups",
    response_model=BackupListResponse,
)
async def list_backups(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
    file_path: str | None = Query(None, description="Filter by file path"),
    limit: int = Query(100, ge=1, le=500, description="Max results"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> BackupListResponse:
    """List file backups for a sandbox."""
    return await backup_service.list_backups(
        session, connection_id, sandbox_id,
        file_path=file_path, limit=limit, offset=offset,
    )


@router.get(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/backups/files",
    response_model=BackupFileListResponse,
)
async def list_backup_files(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> BackupFileListResponse:
    """List distinct file paths that have backups."""
    return await backup_service.list_backup_files(session, connection_id, sandbox_id)


@router.get(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/backups/{backup_id}",
    response_model=BackupDetail,
)
async def get_backup(
    connection_id: str,
    sandbox_id: str,
    backup_id: str,
    session: SessionDep,
    actor: ActorDep,
    include_content: bool = Query(False, description="Include file content in response"),
) -> BackupDetail:
    """Get a single backup by ID."""
    result = await backup_service.get_backup(
        session, connection_id, sandbox_id, backup_id,
        include_content=include_content,
    )
    if result is None:
        from app.core.errors import ExplorerError

        raise ExplorerError(
            f"Backup {backup_id} not found",
            status_code=404,
            code="backup_not_found",
        )
    return result


@router.post(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/backups",
    response_model=BackupCreateResponse,
)
async def create_backup(
    connection_id: str,
    sandbox_id: str,
    request: BackupCreateRequest,
    session: SessionDep,
    actor: ActorDep,
) -> BackupCreateResponse:
    """Create a manual backup of a file."""
    return await backup_service.create_backup(
        session, connection_id, sandbox_id, request,
    )


@router.post(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/backups/{backup_id}/restore",
    response_model=BackupRestoreResponse,
)
async def restore_backup(
    connection_id: str,
    sandbox_id: str,
    backup_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> BackupRestoreResponse:
    """Restore a file from a backup."""
    result = await backup_service.restore_backup(
        session, connection_id, sandbox_id, backup_id,
    )
    if result is None:
        from app.core.errors import ExplorerError

        raise ExplorerError(
            f"Backup {backup_id} not found or restore failed",
            status_code=404,
            code="backup_not_found",
        )
    return result


@router.get(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/backups/{backup_id}/diff",
    response_model=BackupDiffResponse,
)
async def get_backup_diff(
    connection_id: str,
    sandbox_id: str,
    backup_id: str,
    session: SessionDep,
    actor: ActorDep,
    side_by_side: bool = Query(False, description="Include old_text/new_text for two-column diff"),
) -> BackupDiffResponse:
    """Get a git-style diff between a backup and the next version.

    Results are cached server-side for 5 minutes. Pass ``side_by_side=true``
    to also receive ``old_text`` and ``new_text`` for rendering a two-column
    diff view in the frontend.
    """
    result = await backup_service.get_backup_diff(
        session, connection_id, sandbox_id, backup_id,
        side_by_side=side_by_side,
    )
    if result is None:
        from app.core.errors import ExplorerError

        raise ExplorerError(
            f"Backup {backup_id} not found or diff failed",
            status_code=404,
            code="backup_not_found",
        )
    return result


@router.get(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/backups/{backup_id}/export",
)
async def export_backup(
    connection_id: str,
    sandbox_id: str,
    backup_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> Response:
    """Download a backup's file content as an attachment."""
    result = await backup_service.get_backup_content(
        session, connection_id, sandbox_id, backup_id,
    )
    if result is None:
        from app.core.errors import ExplorerError

        raise ExplorerError(
            f"Backup {backup_id} not found",
            status_code=404,
            code="backup_not_found",
        )
    content, file_path, _content_hash = result
    # Extract just the filename for the download header.
    filename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
    return Response(
        content=content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


@router.delete(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/backups/{backup_id}",
    response_model=BackupDeleteResponse,
)
async def delete_backup(
    connection_id: str,
    sandbox_id: str,
    backup_id: str,
    session: SessionDep,
    actor: ActorDep,
) -> BackupDeleteResponse:
    """Delete a single backup by ID."""
    result = await backup_service.delete_backup(
        session, connection_id, sandbox_id, backup_id,
    )
    if result is None:
        from app.core.errors import ExplorerError

        raise ExplorerError(
            f"Backup {backup_id} not found",
            status_code=404,
            code="backup_not_found",
        )
    return result


@router.delete(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/backups",
    response_model=BackupDeleteByPathResponse,
)
async def delete_backups_by_path(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
    file_path: str = Query(..., description="Delete all backups for this file path"),
) -> BackupDeleteByPathResponse:
    """Delete all backups for a given file path."""
    result = await backup_service.delete_backups_by_path(
        session, connection_id, sandbox_id, file_path,
    )
    if result is None:
        from app.core.errors import ExplorerError

        raise ExplorerError(
            "Failed to delete backups",
            status_code=500,
            code="backup_delete_failed",
        )
    return result


@router.post(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/backups/batch-delete",
    response_model=BackupBatchDeleteResponse,
)
async def batch_delete_backups(
    connection_id: str,
    sandbox_id: str,
    request: BackupBatchDeleteRequest,
    session: SessionDep,
    actor: ActorDep,
) -> BackupBatchDeleteResponse:
    """Delete multiple backups by ID in a single call."""
    return await backup_service.batch_delete_backups(
        session, connection_id, sandbox_id, request.backup_ids,
    )
