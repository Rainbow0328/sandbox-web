"""Custom exceptions and their HTTP status code / error body mapping."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class ExplorerError(Exception):
    """Base error for all Sandbox Explorer domain errors."""

    code = "explorer_error"
    status_code = 500
    message = "Internal error"

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        self.message = message or self.message
        self.details = details or {}
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        super().__init__(self.message)


# --- Connection errors ---
class ConnectionUnreachableError(ExplorerError):
    code = "connection_unreachable"
    status_code = 503
    message = "Connection is unreachable"


class ConnectionAuthError(ExplorerError):
    code = "connection_auth_error"
    status_code = 401
    message = "Connection authentication failed"


# --- Sandbox errors ---
class SandboxNotFoundError(ExplorerError):
    code = "sandbox_not_found"
    status_code = 404
    message = "Sandbox not found"


class CapabilityUnavailableError(ExplorerError):
    code = "capability_unavailable"
    status_code = 422
    message = "Capability not available for this connection"


# --- File errors ---
class PathEscapeError(ExplorerError):
    code = "path_escape"
    status_code = 400
    message = "Path escapes the allowed directory"


class FileConflictError(ExplorerError):
    code = "file_conflict"
    status_code = 409
    message = "File was modified by another writer"


# --- History errors ---
class HistorySchemaUnsupportedError(ExplorerError):
    code = "history_schema_unsupported"
    status_code = 422
    message = "Unsupported history schema version"


class HistoryIdentityMismatchError(ExplorerError):
    code = "history_identity_mismatch"
    status_code = 409
    message = "History identity mismatch"


class HistoryHelperUnavailableError(ExplorerError):
    code = "history_helper_unavailable"
    status_code = 503
    message = "History unavailable"


class HistoryConfigRevisionConflictError(ExplorerError):
    code = "history_config_revision_conflict"
    status_code = 409
    message = "History configuration changed"


# --- Command errors ---
class CommandPolicyDeniedError(ExplorerError):
    code = "command_policy_denied"
    status_code = 403
    message = "Command denied by policy"


class CommandTimeoutError(ExplorerError):
    code = "command_timeout"
    status_code = 504
    message = "Command timed out"


# --- Auth errors ---
class AuthenticationError(ExplorerError):
    code = "authentication_failed"
    status_code = 401
    message = "Authentication failed"


async def explorer_exception_handler(request: Request, exc: ExplorerError) -> JSONResponse:
    """Convert an ExplorerError into a structured JSON error response."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )
