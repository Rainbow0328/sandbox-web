"""In-memory fake adapter for development.

This adapter implements the full ``SandboxAdapter`` protocol using
in-memory state. It allows the Web Console to run end-to-end without a real
sandbox environment. Once the SDK's OpenSandbox provider is ready, the factory
will prefer it and this adapter will remain for tests.
"""

from __future__ import annotations

import hashlib
import secrets
import time

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
    native_capability,
)


class FakeAdapter:
    """In-memory adapter that simulates a full sandbox environment."""

    def __init__(self, provider_name: str = "fake", provider_key: str = "fake") -> None:
        self.provider_name = provider_name
        self.provider_key = provider_key
        self._sandboxes: dict[str, SandboxInfo] = {}
        self._files: dict[str, dict[str, bytes]] = {}
        self._instance_counter = 0

    # --- Web-specific ---
    async def test_connection(self) -> ConnectionTestResult:
        return ConnectionTestResult(
            ok=True,
            message="Fake connection is always reachable",
            capabilities=self._capabilities(),
            version="fake-0.1.0",
        )

    async def list_sandboxes(self) -> list[SandboxInfo]:
        return list(self._sandboxes.values())

    # --- Lifecycle ---
    async def create_sandbox(self, request: CreateSandboxRequest) -> SandboxInfo:
        self._instance_counter += 1
        sid = f"sb-fake-{self._instance_counter:04d}"
        ref = SandboxRef(
            provider_name=self.provider_name,
            provider_key=self.provider_key,
            sandbox_id=sid,
            sandbox_instance_id=sid,
        )
        info = SandboxInfo(
            ref=ref,
            state=SandboxState.RUNNING,
            image=request.image,
            workdir=request.workdir,
        )
        self._sandboxes[sid] = info
        self._files[sid] = {}
        # Seed with a sample file.
        self._files[sid]["/workspace/README.md"] = b"# Sample Sandbox\n\nThis is a fake sandbox.\n"
        self._files[sid]["/workspace/app.py"] = b'print("Hello, World!")\n'
        return info

    async def get_sandbox(self, ref: SandboxRef) -> SandboxInfo:
        info = self._sandboxes.get(ref.sandbox_id)
        if info is None:
            raise KeyError(f"Sandbox {ref.sandbox_id} not found")
        return info

    async def pause_sandbox(self, ref: SandboxRef) -> SandboxInfo:
        info = self._sandboxes.get(ref.sandbox_id)
        if info is None:
            raise KeyError(f"Sandbox {ref.sandbox_id} not found")
        paused = SandboxInfo(
            ref=info.ref,
            state=SandboxState.PAUSED,
            image=info.image,
            workdir=info.workdir,
        )
        self._sandboxes[ref.sandbox_id] = paused
        return paused

    async def resume_sandbox(self, ref: SandboxRef) -> SandboxInfo:
        info = self._sandboxes.get(ref.sandbox_id)
        if info is None:
            raise KeyError(f"Sandbox {ref.sandbox_id} not found")
        running = SandboxInfo(
            ref=info.ref,
            state=SandboxState.RUNNING,
            image=info.image,
            workdir=info.workdir,
        )
        self._sandboxes[ref.sandbox_id] = running
        return running

    async def delete_sandbox(self, ref: SandboxRef) -> None:
        self._sandboxes.pop(ref.sandbox_id, None)
        self._files.pop(ref.sandbox_id, None)

    async def capabilities(self, ref: SandboxRef | None = None) -> Capabilities:
        return self._capabilities()

    # --- Filesystem ---
    async def list_files(self, ref: SandboxRef, path: str) -> list[FileEntry]:
        files = self._files.get(ref.sandbox_id, {})
        # Return files under the given path (simple prefix match).
        prefix = path.rstrip("/") + "/" if path != "/" else "/"
        entries: list[FileEntry] = []
        seen_dirs: set[str] = set()
        for fpath, content in files.items():
            if fpath.startswith(prefix) or (path == "/" and fpath.startswith("/")):
                remainder = fpath[len(prefix):] if path != "/" else fpath[1:]
                if "/" in remainder:
                    # It's a subdirectory.
                    dirname = remainder.split("/")[0]
                    full_dir = prefix + dirname
                    if full_dir not in seen_dirs:
                        seen_dirs.add(full_dir)
                        entries.append(FileEntry(path=full_dir, kind=FileKind.DIRECTORY, size=0))
                else:
                    entries.append(
                        FileEntry(
                            path=fpath,
                            kind=FileKind.FILE,
                            size=len(content),
                            content_hash=hashlib.sha256(content).hexdigest(),
                        )
                    )
        entries.sort(key=lambda e: e.path)
        return entries

    async def read_file(self, ref: SandboxRef, path: str) -> bytes:
        files = self._files.get(ref.sandbox_id, {})
        if path not in files:
            raise FileNotFoundError(f"File {path} not found in sandbox {ref.sandbox_id}")
        return files[path]

    async def write_file(self, ref: SandboxRef, request: WriteFileRequest) -> WriteFileResult:
        files = self._files.setdefault(ref.sandbox_id, {})
        old = files.get(request.path)
        previous_hash = hashlib.sha256(old).hexdigest() if old else None
        if request.expected_hash and previous_hash != request.expected_hash:
            from app.core.errors import FileConflictError

            raise FileConflictError(
                "File was modified by another writer",
                details={"expected": request.expected_hash, "actual": previous_hash},
            )
        files[request.path] = request.content
        entry = FileEntry(
            path=request.path,
            kind=FileKind.FILE,
            size=len(request.content),
            content_hash=hashlib.sha256(request.content).hexdigest(),
        )
        return WriteFileResult(entry=entry, previous_hash=previous_hash)

    async def delete_file(self, ref: SandboxRef, path: str) -> None:
        files = self._files.get(ref.sandbox_id, {})
        files.pop(path, None)

    # --- Command ---
    async def execute(self, ref: SandboxRef, request: ExecRequest) -> ExecResult:
        cmd_id = f"cmd-{secrets.token_hex(8)}"
        start = time.time()
        # Simulate common commands.
        stdout = b""
        stderr = b""
        exit_code = 0
        cmd = request.command.strip()
        if cmd.startswith("echo "):
            stdout = (cmd[5:] + "\n").encode()
        elif cmd == "ls" or cmd.startswith("ls "):
            files = self._files.get(ref.sandbox_id, {})
            paths = sorted(f.split("/")[-1] for f in files if f.startswith(request.cwd or "/"))
            stdout = ("  ".join(paths) + "\n").encode() if paths else b""
        elif cmd.startswith("cat "):
            fname = cmd[4:].strip()
            files = self._files.get(ref.sandbox_id, {})
            content = files.get(fname) or files.get(f"{request.cwd or '/'}/{fname}")
            if content:
                stdout = content
            else:
                stderr = f"cat: {fname}: No such file\n".encode()
                exit_code = 1
        elif cmd == "pwd":
            stdout = (request.cwd or "/").encode() + b"\n"
        elif cmd.startswith("python"):
            stdout = b"Python 3.12.0 (main, fake sandbox)\n"
        else:
            stdout = b"command executed (fake)\n"

        duration = int((time.time() - start) * 1000)
        return ExecResult(
            command_id=cmd_id,
            stdout=stdout,
            stderr=stderr,
            exit_code=exit_code,
            state=CommandState.SUCCEEDED,
            duration_ms=duration,
        )

    # --- Internal helpers ---
    def _capabilities(self) -> Capabilities:
        return Capabilities(
            filesystem=native_capability(),
            binary_files=native_capability(),
            atomic_rename=native_capability(),
            file_hash=native_capability(algorithm="sha256"),
            command_execution=native_capability(),
            streaming_output=native_capability(),
            command_stdin=native_capability(),
            pause_resume=native_capability(),
            bulk_upload=native_capability(max_files=100, max_bytes=104857600),
        )

    # --- Mock History (for development without real Sandbox SQLite) ---
    def get_history_events(self, ref: SandboxRef) -> list[dict]:
        """Return mock history events for the sandbox.

        In production, these would come from the Canonical History SQLite
        database inside the sandbox via history_helper.py. Here we synthesize
        events from the adapter's in-memory state.
        """
        import time

        events: list[dict] = []
        sb = self._sandboxes.get(ref.sandbox_id)
        if sb is None:
            return events

        seq = 1
        now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # sandbox.create event
        events.append({
            "event_id": f"evt_{ref.sandbox_id}_create",
            "source_seq": seq,
            "source": "console",
            "actor_type": "user",
            "actor_id": "admin",
            "operation_type": "sandbox.create",
            "status": "succeeded",
            "occurred_at": now_iso,
            "completed_at": now_iso,
            "duration_ms": 120,
            "request_json": {"image": sb.image, "workdir": sb.workdir},
            "schema_version": 1,
            "output_complete": 1,
            "history_storage_state": "complete",
        })
        seq += 1

        # file.write events for seeded files
        files = self._files.get(ref.sandbox_id, {})
        for fpath, content in sorted(files.items()):
            events.append({
                "event_id": f"evt_{ref.sandbox_id}_file_{hash(fpath) % 10000}",
                "source_seq": seq,
                "source": "sdk",
                "actor_type": "agent",
                "actor_id": "agent-1",
                "thread_id": "thread-1",
                "run_id": "run-1",
                "operation_type": "file.write",
                "status": "succeeded",
                "occurred_at": now_iso,
                "completed_at": now_iso,
                "duration_ms": 5,
                "request_json": {"path": fpath},
                "result_json": {
                    "size": len(content),
                    "hash": hashlib.sha256(content).hexdigest(),
                },
                "schema_version": 1,
                "output_complete": 1,
                "history_storage_state": "complete",
                "file_path": fpath,
                "file_change_type": "create",
                "after_hash": hashlib.sha256(content).hexdigest(),
                "after_size": len(content),
            })
            seq += 1

        # command execution event (simulated)
        events.append({
            "event_id": f"evt_{ref.sandbox_id}_cmd_demo",
            "source_seq": seq,
            "source": "sdk",
            "actor_type": "agent",
            "actor_id": "agent-1",
            "thread_id": "thread-1",
            "run_id": "run-1",
            "operation_type": "command.finish",
            "status": "succeeded",
            "occurred_at": now_iso,
            "completed_at": now_iso,
            "duration_ms": 1500,
            "request_json": {"command": "pytest", "cwd": sb.workdir},
            "result_json": {"exit_code": 0},
            "schema_version": 1,
            "output_complete": 1,
            "history_storage_state": "complete",
            "command": "pytest",
            "cwd": sb.workdir,
            "exit_code": 0,
        })

        return events
