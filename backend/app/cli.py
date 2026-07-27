"""CLI entry point for the ``sandbox-console-server`` console command.

Usage::

    sandbox-console-server                      # Start on default port 9090
    sandbox-console-server --port 3000          # Start on port 3000
    sandbox-console-server --host 127.0.0.1     # Bind to localhost only
    sandbox-console-server --dev                # Dev mode (vite + uvicorn)
    sandbox-console-server --build-only         # Only build frontend, don't start

The CLI auto-detects the frontend static directory in this order:

1. ``EXPLORER_STATIC_DIR`` environment variable (explicit override).
2. ``app/static/`` bundled inside the installed package (pip install).
3. ``frontend/dist/`` relative to the project root (development from source).

If no static directory is found, the backend starts in **API-only mode**
(the web UI is unavailable, but the REST API still works).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PORT = 9090
DEFAULT_HOST = "0.0.0.0"
DEFAULT_FRONTEND_PORT = 5173

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_windows() -> bool:
    return sys.platform == "win32"


def _detect_static_dir() -> str | None:
    """Auto-detect the frontend static directory.

    Returns the path as a string, or ``None`` if no static files are found.
    """
    # 1. Explicit env override.
    env_dir = os.environ.get("EXPLORER_STATIC_DIR", "")
    if env_dir and Path(env_dir).is_dir():
        return env_dir

    # 2. Bundled inside the installed package (pip install).
    bundled = Path(__file__).resolve().parent / "static"
    if bundled.is_dir():
        # Check for real content (not just .gitkeep).
        real_files = [f for f in bundled.rglob("*") if f.name != ".gitkeep"]
        if real_files:
            return str(bundled)

    # 3. Development: frontend/dist relative to project root.
    #    When running from source, the project root is 2 levels up from app/.
    dev_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if dev_dist.is_dir():
        return str(dev_dist)

    return None


def _detect_frontend_source() -> Path | None:
    """Locate the frontend source directory (for --dev mode)."""
    dev_frontend = Path(__file__).resolve().parent.parent.parent / "frontend"
    if (dev_frontend / "package.json").exists():
        return dev_frontend
    return None


def _load_env_file(env_path: Path) -> None:
    """Load a .env file into os.environ without overriding existing vars."""
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            if key not in os.environ:
                os.environ[key] = value
    except Exception:
        pass


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------


def _build_frontend() -> bool:
    """Build the frontend from source (requires Node.js)."""
    frontend_dir = _detect_frontend_source()
    if frontend_dir is None:
        print("[sandbox-console-server] Frontend source not found. Cannot build.")
        return False

    npm = "npm.cmd" if _is_windows() else "npm"
    shell = _is_windows()

    if not (frontend_dir / "node_modules").exists():
        print("[sandbox-console-server] Installing frontend dependencies...")
        result = subprocess.run(
            [npm, "install", "--legacy-peer-deps"],
            cwd=str(frontend_dir),
            shell=shell,
        )
        if result.returncode != 0:
            print("[sandbox-console-server] npm install failed.")
            return False

    print("[sandbox-console-server] Building frontend...")
    result = subprocess.run(
        [npm, "run", "build"],
        cwd=str(frontend_dir),
        shell=shell,
    )
    if result.returncode != 0:
        print("[sandbox-console-server] Frontend build failed.")
        return False

    print("[sandbox-console-server] Frontend build complete.")
    return True


# ---------------------------------------------------------------------------
# Start modes
# ---------------------------------------------------------------------------


def _start_production(port: int, host: str) -> None:
    """Start the backend serving bundled/pre-built frontend."""
    static_dir = _detect_static_dir()

    env = {
        "EXPLORER_PORT": str(port),
        "EXPLORER_HOST": host,
    }
    if static_dir:
        env["EXPLORER_STATIC_DIR"] = static_dir

    display_host = "localhost" if host in ("0.0.0.0", "::") else host

    if static_dir:
        print(f"[sandbox-console-server] Starting server on http://{display_host}:{port}")
        print(f"[sandbox-console-server] Static files: {static_dir}")
    else:
        print(f"[sandbox-console-server] Starting API-only server on http://{display_host}:{port}")
        print("[sandbox-console-server] No frontend static files found — web UI unavailable.")
        print("[sandbox-console-server] To build the frontend, run with --build-only from source.")

    cmd = [
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", host,
        "--port", str(port),
    ]
    proc = subprocess.Popen(
        cmd,
        env={**os.environ, **env},
        shell=_is_windows(),
    )
    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n[sandbox-console-server] Shutting down...")
        proc.terminate()
        proc.wait()


def _start_dev(port: int, host: str, frontend_port: int) -> None:
    """Start both frontend dev server and backend in parallel."""
    frontend_dir = _detect_frontend_source()
    if frontend_dir is None:
        print("[sandbox-console-server] --dev mode requires frontend source directory.")
        print("[sandbox-console-server] Run from the project root or install in editable mode: pip install -e .")
        sys.exit(1)

    display_host = "localhost" if host in ("0.0.0.0", "::") else host
    print(
        f"[sandbox-console-server] Dev mode: backend on http://{display_host}:{port}, "
        f"frontend on http://localhost:{frontend_port}"
    )

    # Start backend.
    backend_cmd = [
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", host,
        "--port", str(port),
        "--reload",
    ]
    print(f"[sandbox-console-server] Starting backend: {' '.join(backend_cmd)}")
    backend_proc = subprocess.Popen(
        backend_cmd,
        env={**os.environ, "EXPLORER_PORT": str(port), "EXPLORER_HOST": host},
        shell=_is_windows(),
    )

    # Start frontend dev server.
    npm = "npm.cmd" if _is_windows() else "npm"
    frontend_cmd = [npm, "run", "dev", "--", "--port", str(frontend_port)]
    print(f"[sandbox-console-server] Starting frontend: {' '.join(frontend_cmd)}")
    frontend_proc = subprocess.Popen(
        frontend_cmd,
        cwd=str(frontend_dir),
        env={
            **os.environ,
            "EXPLORER_PORT": str(port),
            "EXPLORER_FRONTEND_PORT": str(frontend_port),
        },
        shell=_is_windows(),
    )

    print(f"\n[sandbox-console-server] Backend:  http://{display_host}:{port}")
    print(f"[sandbox-console-server] Frontend: http://localhost:{frontend_port}")
    print("[sandbox-console-server] Press Ctrl+C to stop both.\n")

    try:
        while True:
            if backend_proc.poll() is not None:
                print("[sandbox-console-server] Backend exited.")
                break
            if frontend_proc.poll() is not None:
                print("[sandbox-console-server] Frontend exited.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[sandbox-console-server] Shutting down...")
    finally:
        for proc in [backend_proc, frontend_proc]:
            if proc.poll() is None:
                proc.terminate()
        for proc in [backend_proc, frontend_proc]:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point — invoked by the ``sandbox-console-server`` command."""
    # Load .env file from the current working directory if it exists.
    _load_env_file(Path.cwd() / ".env")

    parser = argparse.ArgumentParser(
        prog="sandbox-console-server",
        description="Sandbox Console — unified web UI for OpenSandbox management.",
    )
    parser.add_argument(
        "--port", type=int, default=None,
        help=f"Server port (env: EXPLORER_PORT, default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--host", type=str, default=None,
        help=f"Bind address (env: EXPLORER_HOST, default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--dev", action="store_true",
        help="Development mode: run frontend (vite) + backend (uvicorn) in parallel",
    )
    parser.add_argument(
        "--build-only", action="store_true",
        help="Only build the frontend, don't start the server",
    )
    parser.add_argument(
        "--frontend-port", type=int, default=None,
        help=f"Frontend dev server port (only used in --dev mode, default: {DEFAULT_FRONTEND_PORT})",
    )
    args = parser.parse_args()

    # Resolve: CLI arg > env var > default.
    port = args.port if args.port is not None else _env_int("EXPLORER_PORT", DEFAULT_PORT)
    host = args.host if args.host is not None else os.environ.get("EXPLORER_HOST", DEFAULT_HOST)
    frontend_port = (
        args.frontend_port
        if args.frontend_port is not None
        else _env_int("EXPLORER_FRONTEND_PORT", DEFAULT_FRONTEND_PORT)
    )

    if args.build_only:
        if not _build_frontend():
            sys.exit(1)
        return

    if args.dev:
        _start_dev(port=port, host=host, frontend_port=frontend_port)
    else:
        _start_production(port=port, host=host)


if __name__ == "__main__":
    main()
