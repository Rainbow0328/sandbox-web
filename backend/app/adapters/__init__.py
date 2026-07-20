"""Sandbox Connection adapter layer.

Adapters bridge the Console's domain types to the SDK's provider implementations.
The term "Connection" here refers to a configured sandbox environment connection —
not to be confused with the SDK's ``provider_name`` (vendor type) or
``provider_key`` (logical instance identifier used internally by the SDK).
"""

from app.adapters.base import (
    Capabilities,
    CommandState,
    ConnectionTestResult,
    CreateSandboxRequest,
    ExecRequest,
    ExecResult,
    FileEntry,
    FileKind,
    SandboxAdapter,
    SandboxInfo,
    SandboxRef,
    SandboxState,
    WriteFileRequest,
    WriteFileResult,
)
from app.adapters.factory import create_adapter
from app.adapters.fake import FakeAdapter
from app.adapters.opensandbox import OpenSandboxConsoleAdapter

__all__ = [
    "Capabilities",
    "CommandState",
    "ConnectionTestResult",
    "CreateSandboxRequest",
    "ExecRequest",
    "ExecResult",
    "FakeAdapter",
    "FileEntry",
    "FileKind",
    "OpenSandboxConsoleAdapter",
    "SandboxAdapter",
    "SandboxInfo",
    "SandboxRef",
    "SandboxState",
    "WriteFileRequest",
    "WriteFileResult",
    "create_adapter",
]
