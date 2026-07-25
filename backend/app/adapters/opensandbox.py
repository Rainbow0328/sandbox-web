"""OpenSandbox adapter — wraps the SDK's OpenSandboxProvider.

This adapter bridges our ``SandboxAdapter`` protocol to the SDK's
``SandboxProvider`` protocol. It handles type conversion between our
dataclass domain types and the SDK's pydantic domain models, and exposes
``execute_stream`` for real-time SSE streaming.

(对齐 §4.2 Provider Adapter Pattern)
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import asdict
from typing import Any
from urllib.parse import urlparse

from agent_sandbox_backends.domain.capabilities import Capabilities as SDKCapabilities
from agent_sandbox_backends.domain.commands import (
    CommandStream as SDKCommandStream,
)
from agent_sandbox_backends.domain.commands import (
    ExecRequest as SDKExecRequest,
)
from agent_sandbox_backends.domain.commands import (
    ExecResult as SDKExecResult,
)
from agent_sandbox_backends.domain.files import (
    FileEntry as SDKFileEntry,
)
from agent_sandbox_backends.domain.files import (
    FileKind as SDKFileKind,
)
from agent_sandbox_backends.domain.files import (
    WriteFileRequest as SDKWriteFileRequest,
)
from agent_sandbox_backends.domain.identity import SandboxRef as SDKSandboxRef
from agent_sandbox_backends.domain.sandbox import (
    CreateSandboxRequest as SDKCreateSandboxRequest,
)
from agent_sandbox_backends.domain.sandbox import (
    SandboxInfo as SDKSandboxInfo,
)
from agent_sandbox_backends.domain.sandbox import (
    SandboxState as SDKSandboxState,
)
from agent_sandbox_backends.providers.opensandbox import OpenSandboxProvider

# SDK version for test_connection reporting.
from agent_sandbox_backends.version import SDK_VERSION

from app.adapters.base import (
    Capabilities,
    CommandState,
    ConnectionTestResult,
    CreateSandboxRequest,
    ExecRequest,
    ExecResult,
    FileEntry,
    FileKind,
    SandboxInfo,
    SandboxRef,
    SandboxState,
    WriteFileRequest,
    WriteFileResult,
)
from app.core.errors import (
    CapabilityUnavailableError,
    FileConflictError,
    SandboxNotFoundError,
)


def _convert_sdk_error(exc: Exception) -> Exception:
    """Convert SDK exceptions to ExplorerError subclasses for better HTTP mapping."""
    exc_name = type(exc).__name__
    msg = str(exc)

    if "NotFound" in exc_name or "SANDBOX_NOT_FOUND" in msg or "FILE_NOT_FOUND" in msg:
        return SandboxNotFoundError(msg, details={"sdk_error": exc_name})
    if "Conflict" in exc_name or "Concurrent" in exc_name:
        return FileConflictError(msg, details={"sdk_error": exc_name})
    if "UnsupportedCapability" in exc_name:
        return CapabilityUnavailableError(msg, details={"sdk_error": exc_name})
    # Default: return original exception (will be caught by general handler).
    return exc


class OpenSandboxConsoleAdapter:
    """Adapter that wraps the SDK's ``OpenSandboxProvider``.

    All lifecycle, filesystem, and command operations are delegated to the
    SDK provider. Type conversion between our dataclass models and the SDK's
    pydantic models is handled transparently.
    """

    def __init__(
        self,
        *,
        provider_name: str = "opensandbox",
        provider_key: str = "opensandbox-default",
        api_key: str | None = None,
        domain: str | None = None,
        protocol: str = "http",
        endpoint: str = "",
        credentials: dict[str, Any] | None = None,
    ) -> None:
        self.provider_name = provider_name
        self.provider_key = provider_key

        # Extract connection params from credentials/endpoint.
        creds = credentials or {}
        resolved_api_key = api_key or creds.get("api_key")
        resolved_domain = domain or creds.get("domain")
        if not resolved_domain and endpoint:
            # Parse endpoint URL to extract domain.
            # e.g., "http://localhost:8080" -> domain="localhost:8080", protocol="http"
            # Also handle bare "host:port" without scheme.
            # If endpoint lacks a scheme, prepend http:// so urlparse can
            # correctly separate hostname and port.
            raw = endpoint.strip()
            if "://" not in raw:
                raw = f"http://{raw}"

            parsed = urlparse(raw)
            resolved_domain = parsed.hostname
            if parsed.port:
                resolved_domain = f"{resolved_domain}:{parsed.port}"
            if parsed.scheme:
                protocol = parsed.scheme

        # Use the SDK's default provider_key ("opensandbox-default") for the
        # underlying provider, NOT connection.id.  This is critical for history:
        # the SDK's SandboxBackend initialises the sandbox's history SQLite with
        # provider_key="opensandbox-default" in the history_meta table.  If
        # Console uses a different provider_key, the history helper's identity
        # check (initialize → "History identity conflict for provider_key")
        # rejects the init call, and Console cannot read or write the shared
        # history database.
        #
        # self.provider_key (connection.id) is retained for Console's internal
        # bookkeeping (cache keys, ref tracking) but is NEVER passed to the SDK.
        self._provider = OpenSandboxProvider(
            provider_key="opensandbox-default",
            api_key=resolved_api_key,
            domain=resolved_domain,
            protocol=protocol,
            use_server_proxy=True,
        )

    # --- Type conversion helpers ---

    def _to_sdk_ref(self, ref: SandboxRef) -> SDKSandboxRef:
        return SDKSandboxRef(
            provider_name=self._provider.provider_name,
            provider_key=self._provider.provider_key,
            sandbox_id=ref.sandbox_id,
            sandbox_instance_id=ref.sandbox_instance_id,
            endpoint_fingerprint=self._provider._endpoint_fingerprint(),
            metadata=dict(ref.metadata),
        )

    @staticmethod
    def _from_sdk_ref(ref: SDKSandboxRef) -> SandboxRef:
        return SandboxRef(
            provider_name=ref.provider_name,
            provider_key=ref.provider_key,
            sandbox_id=ref.sandbox_id,
            sandbox_instance_id=ref.sandbox_instance_id,
            metadata=dict(ref.metadata),
        )

    @staticmethod
    def _from_sdk_info(info: SDKSandboxInfo) -> SandboxInfo:
        state_map = {
            SDKSandboxState.CREATING: SandboxState.CREATING,
            SDKSandboxState.RUNNING: SandboxState.RUNNING,
            SDKSandboxState.PAUSED: SandboxState.PAUSED,
            SDKSandboxState.STOPPING: SandboxState.STOPPING,
            SDKSandboxState.STOPPED: SandboxState.STOPPED,
            SDKSandboxState.FAILED: SandboxState.FAILED,
            SDKSandboxState.UNKNOWN: SandboxState.UNKNOWN,
            SDKSandboxState.DELETED: SandboxState.DELETED,
        }
        # Convert datetime to ISO string for the Console dataclass.
        created_at = info.created_at.isoformat() if info.created_at else None
        expires_at = info.expires_at.isoformat() if info.expires_at else None
        return SandboxInfo(
            ref=OpenSandboxConsoleAdapter._from_sdk_ref(info.ref),
            state=state_map.get(info.state, SandboxState.UNKNOWN),
            image=info.image,
            workdir=info.workdir,
            created_at=created_at,
            expires_at=expires_at,
        )

    @staticmethod
    def _to_sdk_exec_request(request: ExecRequest) -> SDKExecRequest:
        return SDKExecRequest(
            command=request.command,
            cwd=request.cwd,
            env=dict(request.env),
            timeout_seconds=request.timeout_seconds,
            stdin=request.stdin,
            idempotency_key=request.idempotency_key,
        )

    @staticmethod
    def _from_sdk_exec_result(result: SDKExecResult) -> ExecResult:
        state_map = {
            "queued": CommandState.QUEUED,
            "running": CommandState.RUNNING,
            "succeeded": CommandState.SUCCEEDED,
            "failed": CommandState.FAILED,
            "cancelled": CommandState.CANCELLED,
            "timeout": CommandState.TIMEOUT,
            "unknown": CommandState.UNKNOWN,
        }
        return ExecResult(
            command_id=result.command_id,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
            state=state_map.get(result.state.value, CommandState.UNKNOWN),
            duration_ms=result.duration_ms,
        )

    @staticmethod
    def _from_sdk_file_entry(entry: SDKFileEntry) -> FileEntry:
        kind_map = {
            SDKFileKind.FILE: FileKind.FILE,
            SDKFileKind.DIRECTORY: FileKind.DIRECTORY,
            SDKFileKind.SYMLINK: FileKind.SYMLINK,
            SDKFileKind.OTHER: FileKind.OTHER,
        }
        return FileEntry(
            path=entry.path,
            kind=kind_map.get(entry.kind, FileKind.OTHER),
            size=entry.size,
            content_hash=entry.content_hash,
        )

    @staticmethod
    def _from_sdk_capabilities(caps: SDKCapabilities) -> Capabilities:
        """Convert SDK Capabilities (pydantic) to our Capabilities (dataclass)."""
        # SDK Capabilities is a pydantic model with the same structure.
        # Use model_dump() to get a dict, then reconstruct our dataclass.
        caps_dict = caps.model_dump() if hasattr(caps, "model_dump") else asdict(caps)
        return Capabilities(**caps_dict)

    # --- Web-specific ---

    async def test_connection(self) -> ConnectionTestResult:
        """Test connection by calling capabilities() on the provider."""
        try:
            caps = await self._provider.capabilities()
            return ConnectionTestResult(
                ok=True,
                message="OpenSandbox connection is reachable",
                capabilities=self._from_sdk_capabilities(caps),
                version=SDK_VERSION,
            )
        except Exception as exc:
            return ConnectionTestResult(
                ok=False,
                message=f"Connection failed: {exc}",
                capabilities=None,
                version=SDK_VERSION,
            )

    async def list_sandboxes(self) -> list[SandboxInfo]:
        infos = await self._provider.list()
        return [self._from_sdk_info(info) for info in infos]

    # --- Lifecycle ---

    async def create_sandbox(self, request: CreateSandboxRequest) -> SandboxInfo:
        sdk_request = SDKCreateSandboxRequest(
            image=request.image,
            workdir=request.workdir,
            metadata=dict(request.metadata) if request.metadata else {},
        )
        ref = await self._provider.create(sdk_request)
        # SDK's create() returns SandboxRef; call get() for full info.
        info = await self._provider.get(ref)
        return self._from_sdk_info(info)

    async def get_sandbox(self, ref: SandboxRef) -> SandboxInfo:
        sdk_ref = self._to_sdk_ref(ref)
        try:
            info = await self._provider.get(sdk_ref)
            return self._from_sdk_info(info)
        except Exception as exc:
            raise _convert_sdk_error(exc) from exc

    async def pause_sandbox(self, ref: SandboxRef) -> SandboxInfo:
        sdk_ref = self._to_sdk_ref(ref)
        try:
            info = await self._provider.pause(sdk_ref)
            return self._from_sdk_info(info)
        except Exception as exc:
            raise _convert_sdk_error(exc) from exc

    async def resume_sandbox(self, ref: SandboxRef) -> SandboxInfo:
        sdk_ref = self._to_sdk_ref(ref)
        try:
            info = await self._provider.resume(sdk_ref)
            return self._from_sdk_info(info)
        except Exception as exc:
            raise _convert_sdk_error(exc) from exc

    async def delete_sandbox(self, ref: SandboxRef) -> None:
        sdk_ref = self._to_sdk_ref(ref)
        try:
            await self._provider.delete(sdk_ref)
        except Exception as exc:
            raise _convert_sdk_error(exc) from exc

    async def capabilities(self, ref: SandboxRef | None = None) -> Capabilities:
        sdk_ref = self._to_sdk_ref(ref) if ref else None
        caps = await self._provider.capabilities(sdk_ref)
        return self._from_sdk_capabilities(caps)

    # --- Filesystem ---

    async def list_files(self, ref: SandboxRef, path: str) -> list[FileEntry]:
        sdk_ref = self._to_sdk_ref(ref)
        try:
            entries = await self._provider.list_files(sdk_ref, path)
            return [self._from_sdk_file_entry(e) for e in entries]
        except Exception as exc:
            raise _convert_sdk_error(exc) from exc

    async def read_file(self, ref: SandboxRef, path: str) -> bytes:
        sdk_ref = self._to_sdk_ref(ref)
        try:
            return await self._provider.read_file(sdk_ref, path)
        except Exception as exc:
            raise _convert_sdk_error(exc) from exc

    async def write_file(self, ref: SandboxRef, request: WriteFileRequest) -> WriteFileResult:
        sdk_ref = self._to_sdk_ref(ref)
        sdk_request = SDKWriteFileRequest(
            path=request.path,
            content=request.content,
            expected_hash=request.expected_hash,
        )
        try:
            result = await self._provider.write_file(sdk_ref, sdk_request)
        except Exception as exc:
            raise _convert_sdk_error(exc) from exc
        return WriteFileResult(
            entry=self._from_sdk_file_entry(result.entry),
            previous_hash=result.previous_hash,
            cas_strength=getattr(result, "cas_strength", "native"),
        )

    async def delete_file(self, ref: SandboxRef, path: str) -> None:
        sdk_ref = self._to_sdk_ref(ref)
        try:
            await self._provider.delete_file(sdk_ref, path)
        except Exception as exc:
            raise _convert_sdk_error(exc) from exc

    # --- Command ---

    async def execute(self, ref: SandboxRef, request: ExecRequest) -> ExecResult:
        sdk_ref = self._to_sdk_ref(ref)
        sdk_request = self._to_sdk_exec_request(request)
        try:
            result = await self._provider.execute(sdk_ref, sdk_request)
        except Exception as exc:
            raise _convert_sdk_error(exc) from exc
        return self._from_sdk_exec_result(result)

    async def execute_stream(
        self,
        ref: SandboxRef,
        request: ExecRequest,
        on_output: Callable[[str, bytes], Awaitable[None]],
    ) -> ExecResult:
        """Execute with real-time streaming output via callback.

        This is the SDK's ``execute_stream`` method, exposed for the
        Web Console's SSE endpoint to provide real-time output.
        """
        sdk_ref = self._to_sdk_ref(ref)
        sdk_request = self._to_sdk_exec_request(request)

        async def sdk_callback(stream: SDKCommandStream, data: bytes) -> None:
            await on_output(stream.value, data)

        result = await self._provider.execute_stream(sdk_ref, sdk_request, sdk_callback)
        return self._from_sdk_exec_result(result)

    async def close(self) -> None:
        """Close the underlying provider."""
        await self._provider.close()

    async def get_endpoint(self, ref: SandboxRef, port: int) -> dict:
        """Get the accessible URL for a port inside the sandbox."""
        sdk_ref = self._to_sdk_ref(ref)
        sandbox = await self._provider._get_sandbox(sdk_ref)
        endpoint = await sandbox.get_endpoint(port)
        return {"endpoint": endpoint.endpoint, "headers": dict(endpoint.headers)}

    # --- SDK access for history integration ---

    @property
    def sdk_provider(self):
        """Expose the underlying SDK provider for history transport."""
        return self._provider

    def to_sdk_ref(self, ref: SandboxRef) -> SDKSandboxRef:
        """Convert our SandboxRef to SDK's SandboxRef."""
        return self._to_sdk_ref(ref)
