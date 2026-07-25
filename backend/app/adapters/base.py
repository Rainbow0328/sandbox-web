"""SandboxAdapter protocol and shared domain types.

These types mirror the SDK's ``agent_sandbox_backends.domain`` models so that
the Web Console can run independently during development. Once the SDK is fully
wired, the adapter implementations will delegate to the SDK's provider classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class SandboxState(StrEnum):
    CREATING = "creating"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"
    FAILED = "failed"
    UNKNOWN = "unknown"
    DELETED = "deleted"


class CommandState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"
    UNKNOWN = "unknown"


class FileKind(StrEnum):
    FILE = "file"
    DIRECTORY = "directory"
    SYMLINK = "symlink"
    OTHER = "other"


class CapabilitySupport(StrEnum):
    NATIVE = "native"
    EMULATED = "emulated"
    UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# Identity & Sandbox
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SandboxRef:
    """Reference to a specific sandbox instance on a specific connection."""

    provider_name: str
    provider_key: str
    sandbox_id: str
    sandbox_instance_id: str
    endpoint_fingerprint: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class CreateSandboxRequest:
    image: str = "python:3.12"
    workdir: str = "/"
    env: dict[str, str] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)
    idempotency_key: str | None = None


@dataclass(frozen=True)
class SandboxInfo:
    ref: SandboxRef
    state: SandboxState
    image: str | None = None
    workdir: str = "/"
    created_at: str | None = None  # RFC3339
    expires_at: str | None = None  # RFC3339


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Capability:
    supported: bool
    strength: CapabilitySupport = CapabilitySupport.NATIVE
    limits: dict[str, Any] = field(default_factory=dict)
    reason: str | None = None
    source: str = "provider"


def native_capability(**limits: Any) -> Capability:
    return Capability(supported=True, strength=CapabilitySupport.NATIVE, limits=limits)


def unavailable_capability(reason: str) -> Capability:
    return Capability(supported=False, strength=CapabilitySupport.UNAVAILABLE, reason=reason)


@dataclass(frozen=True)
class Capabilities:
    filesystem: Capability
    binary_files: Capability
    atomic_rename: Capability
    file_hash: Capability
    command_execution: Capability
    streaming_output: Capability
    command_stdin: Capability
    pause_resume: Capability
    bulk_upload: Capability

    @classmethod
    def all_native(cls) -> Capabilities:
        """Capabilities where everything is natively supported."""
        return cls(
            filesystem=native_capability(),
            binary_files=native_capability(),
            atomic_rename=native_capability(),
            file_hash=native_capability(algorithm="sha256"),
            command_execution=native_capability(),
            streaming_output=native_capability(),
            command_stdin=native_capability(),
            pause_resume=native_capability(),
            bulk_upload=native_capability(max_files=100, max_bytes=100 * 1024 * 1024),
        )


# ---------------------------------------------------------------------------
# Files
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FileEntry:
    path: str
    kind: FileKind
    size: int
    content_hash: str | None = None


@dataclass(frozen=True)
class WriteFileRequest:
    path: str
    content: bytes
    expected_hash: str | None = None


@dataclass(frozen=True)
class WriteFileResult:
    entry: FileEntry
    previous_hash: str | None = None
    cas_strength: str = "native"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ExecRequest:
    command: str
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    timeout_seconds: float | None = None
    stdin: bytes | None = None
    idempotency_key: str | None = None


@dataclass(frozen=True)
class ExecResult:
    command_id: str
    stdout: bytes = b""
    stderr: bytes = b""
    exit_code: int | None = None
    state: CommandState = CommandState.SUCCEEDED
    duration_ms: int = 0

    @property
    def stdout_text(self) -> str:
        return self.stdout.decode("utf-8", errors="replace")

    @property
    def stderr_text(self) -> str:
        return self.stderr.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Connection test result
# ---------------------------------------------------------------------------

@dataclass
class ConnectionTestResult:
    """Result of ``test_connection`` — the one method unique to SandboxAdapter."""

    ok: bool
    message: str = ""
    capabilities: Capabilities | None = None
    version: str | None = None


# ---------------------------------------------------------------------------
# Sandbox adapter protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class SandboxAdapter(Protocol):
    """Protocol for all sandbox adapters used by the Web Console."""

    provider_name: str
    provider_key: str

    # --- Web-specific ---
    async def test_connection(self) -> ConnectionTestResult: ...

    async def list_sandboxes(self) -> list[SandboxInfo]: ...

    # --- Lifecycle ---
    async def create_sandbox(self, request: CreateSandboxRequest) -> SandboxInfo: ...

    async def get_sandbox(self, ref: SandboxRef) -> SandboxInfo: ...

    async def pause_sandbox(self, ref: SandboxRef) -> SandboxInfo: ...

    async def resume_sandbox(self, ref: SandboxRef) -> SandboxInfo: ...

    async def delete_sandbox(self, ref: SandboxRef) -> None: ...

    async def capabilities(self, ref: SandboxRef | None = None) -> Capabilities: ...

    # --- Filesystem ---
    async def list_files(self, ref: SandboxRef, path: str) -> list[FileEntry]: ...

    async def read_file(self, ref: SandboxRef, path: str) -> bytes: ...

    async def write_file(self, ref: SandboxRef, request: WriteFileRequest) -> WriteFileResult: ...

    async def delete_file(self, ref: SandboxRef, path: str) -> None: ...

    # --- Command ---
    async def execute(self, ref: SandboxRef, request: ExecRequest) -> ExecResult: ...
