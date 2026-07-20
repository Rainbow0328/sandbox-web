"""File routes: list, read, write, delete, upload, download."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, Query, Response, UploadFile
from fastapi.responses import StreamingResponse

from app.core.deps import ActorDep, SessionDep
from app.schemas.file import (
    FileContentResponse,
    FileListResponse,
    FileWriteRequest,
    FileWriteResponse,
)
from app.services import file_service

router = APIRouter(tags=["files"])


@router.get(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/files",
    response_model=FileListResponse,
)
async def list_files(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
    path: str = Query(default="/", description="Directory path to list"),
) -> FileListResponse:
    """List files in a directory."""
    return await file_service.list_files(session, connection_id, sandbox_id, path, actor)


@router.get(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/file",
    response_model=FileContentResponse,
)
async def read_file(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
    path: str = Query(..., description="File path to read"),
) -> FileContentResponse:
    """Read file content."""
    return await file_service.read_file(session, connection_id, sandbox_id, path, actor)


@router.put(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/file",
    response_model=FileWriteResponse,
)
async def write_file(
    connection_id: str,
    sandbox_id: str,
    request: FileWriteRequest,
    session: SessionDep,
    actor: ActorDep,
    path: str = Query(..., description="File path to write"),
    if_match: str | None = Query(default=None, alias="If-Match", description="Expected content hash"),
) -> FileWriteResponse:
    """Write file content with optimistic concurrency (If-Match hash)."""
    expected_hash = if_match or request.expected_hash
    return await file_service.write_file(
        session, connection_id, sandbox_id, path, request.content, expected_hash, actor,
    )


@router.delete(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/file",
    status_code=200,
    response_class=Response,
)
async def delete_file(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
    path: str = Query(..., description="File path to delete"),
) -> None:
    """Delete a file."""
    await file_service.delete_file(session, connection_id, sandbox_id, path, actor)


@router.post(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/upload",
    response_model=FileWriteResponse,
)
async def upload_file(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
    file: UploadFile = File(...),
    path: str = Form(..., description="Destination path in the sandbox"),
) -> FileWriteResponse:
    """Upload a file (multipart) with size limit enforcement."""
    from app.core.config import get_settings
    from app.core.errors import ExplorerError

    settings = get_settings()
    max_bytes = settings.max_upload_bytes

    # Read in chunks to enforce size limit without loading entire file first.
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(64 * 1024)  # 64KB chunks
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise ExplorerError(
                f"File exceeds maximum upload size ({max_bytes} bytes)",
                status_code=413,
                code="file_too_large",
                details={"max_bytes": max_bytes, "received": total},
            )
        chunks.append(chunk)
    content = b"".join(chunks)

    return await file_service.upload_file(
        session, connection_id, sandbox_id, path, content, actor,
    )


@router.get(
    "/connections/{connection_id}/sandboxes/{sandbox_id}/download",
)
async def download_file(
    connection_id: str,
    sandbox_id: str,
    session: SessionDep,
    actor: ActorDep,
    path: str = Query(..., description="File path to download"),
) -> StreamingResponse:
    """Download a file as raw bytes."""
    content, content_hash, size = await file_service.download_file(
        session, connection_id, sandbox_id, path,
    )
    filename = path.rsplit("/", 1)[-1] if "/" in path else path
    return StreamingResponse(
        iter([content]),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Hash": content_hash,
            "X-Content-Size": str(size),
        },
    )
