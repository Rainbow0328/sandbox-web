#!/usr/bin/env python3
"""Sandbox Console — Unified Startup Script.

Usage:
    python start.py              # Production mode: build frontend + serve from backend
    python start.py --dev        # Dev mode: run frontend (vite) + backend (uvicorn) in parallel
    python start.py --build-only # Only build frontend, don't start server

The script auto-detects the environment:
    - If frontend/dist exists, uses it (production mode)
    - If --dev, starts both vite and uvicorn
    - Otherwise, builds frontend first, then starts uvicorn

Port configuration priority (highest to lowest):
    1. CLI flags:  --port, --host, --frontend-port
    2. Environment variables:  EXPLORER_PORT, EXPLORER_HOST, EXPLORER_FRONTEND_PORT
    3. .env file (in project root)
    4. Built-in defaults:  backend=8080, host=0.0.0.0, frontend=5173

Environment variables (EXPLORER_* prefix) are passed through to the backend.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

# Project root is where this script lives.
ROOT = Path(__file__).parent.resolve()
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
FRONTEND_DIST = FRONTEND_DIR / "dist"
ENV_FILE = ROOT / ".env"

# Default values.
DEFAULT_BACKEND_PORT = 8080
DEFAULT_BACKEND_HOST = "0.0.0.0"
DEFAULT_FRONTEND_PORT = 5173


def is_windows() -> bool:
    return sys.platform == "win32"


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a simple .env file and return key-value pairs.

    Only sets values that are NOT already present in os.environ, so real
    environment variables always take precedence over .env file values.
    """
    result: dict[str, str] = {}
    if not path.exists():
        return result
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            # Strip surrounding quotes.
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
                value = value[1:-1]
            result[key] = value
    except Exception:
        pass
    return result


def apply_env_file() -> None:
    """Load .env file values into os.environ (without overriding existing vars)."""
    for key, value in load_env_file(ENV_FILE).items():
        if key not in os.environ:
            os.environ[key] = value


def env_or_default(key: str, default: str) -> str:
    """Return env var value or default."""
    return os.environ.get(key, default)


def env_int(key: str, default: int) -> int:
    """Return env var as int or default."""
    try:
        return int(os.environ.get(key, str(default)))
    except (ValueError, TypeError):
        return default


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> subprocess.Popen:
    """Start a subprocess and return the process handle."""
    shell = is_windows()
    return subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        env={**os.environ, **(env or {})},
        shell=shell,
    )


def build_frontend() -> bool:
    """Build the frontend if npm is available."""
    print("[start] Building frontend...")
    if not FRONTEND_DIR.exists():
        print("[start] Frontend directory not found, skipping build.")
        return False

    # Check if node_modules exists.
    if not (FRONTEND_DIR / "node_modules").exists():
        print("[start] Installing frontend dependencies...")
        npm_cmd = "npm.cmd" if is_windows() else "npm"
        result = subprocess.run(
            [npm_cmd, "install", "--legacy-peer-deps"],
            cwd=str(FRONTEND_DIR),
            shell=is_windows(),
        )
        if result.returncode != 0:
            print("[start] Failed to install frontend dependencies.")
            return False

    npm_cmd = "npm.cmd" if is_windows() else "npm"
    result = subprocess.run(
        [npm_cmd, "run", "build"],
        cwd=str(FRONTEND_DIR),
        shell=is_windows(),
    )
    if result.returncode != 0:
        print("[start] Frontend build failed.")
        return False

    print("[start] Frontend build complete.")
    return True


def start_production(port: int, host: str) -> None:
    """Start the backend serving the built frontend."""
    # Ensure frontend is built.
    if not FRONTEND_DIST.exists():
        if not build_frontend():
            print("[start] Cannot start without frontend build. Run 'python start.py --build-only' first.")
            sys.exit(1)

    env = {
        "EXPLORER_STATIC_DIR": str(FRONTEND_DIST),
        "EXPLORER_PORT": str(port),
        "EXPLORER_HOST": host,
    }

    print(f"[start] Starting production server on http://{host}:{port}")
    print(f"[start] Static files: {FRONTEND_DIST}")

    # Use uvicorn directly.
    cmd = [
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", host,
        "--port", str(port),
    ]
    proc = run(cmd, cwd=BACKEND_DIR, env=env)
    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n[start] Shutting down...")
        proc.terminate()
        proc.wait()


def start_dev(port: int, host: str, frontend_port: int) -> None:
    """Start both frontend dev server and backend in parallel."""
    print(f"[start] Dev mode: backend on :{port}, frontend on :{frontend_port}")

    # Start backend.
    backend_env = {
        "EXPLORER_PORT": str(port),
        "EXPLORER_HOST": host,
    }
    backend_cmd = [
        sys.executable, "-m", "uvicorn",
        "app.main:app",
        "--host", host,
        "--port", str(port),
        "--reload",
    ]
    print(f"[start] Starting backend: {' '.join(backend_cmd)}")
    backend_proc = run(backend_cmd, cwd=BACKEND_DIR, env=backend_env)

    # Start frontend dev server.
    # Pass backend port to vite so the proxy target can be configured dynamically.
    npm_cmd = "npm.cmd" if is_windows() else "npm"
    frontend_cmd = [npm_cmd, "run", "dev", "--", "--port", str(frontend_port)]
    print(f"[start] Starting frontend: {' '.join(frontend_cmd)}")
    frontend_proc = run(
        frontend_cmd,
        cwd=FRONTEND_DIR,
        env={
            "EXPLORER_PORT": str(port),
            "EXPLORER_FRONTEND_PORT": str(frontend_port),
        },
    )

    print(f"\n[start] Backend:  http://{host}:{port}")
    print(f"[start] Frontend: http://localhost:{frontend_port}")
    print("[start] Press Ctrl+C to stop both.\n")

    try:
        # Wait for either to exit.
        while True:
            if backend_proc.poll() is not None:
                print("[start] Backend exited.")
                break
            if frontend_proc.poll() is not None:
                print("[start] Frontend exited.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[start] Shutting down...")
    finally:
        for proc in [backend_proc, frontend_proc]:
            if proc.poll() is None:
                proc.terminate()
        for proc in [backend_proc, frontend_proc]:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def main() -> None:
    # Load .env file first so env vars / defaults can use those values.
    apply_env_file()

    parser = argparse.ArgumentParser(description="Sandbox Console unified startup.")
    parser.add_argument("--dev", action="store_true", help="Development mode (parallel frontend + backend)")
    parser.add_argument("--build-only", action="store_true", help="Only build frontend, don't start server")
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"Backend port (env: EXPLORER_PORT, default: {DEFAULT_BACKEND_PORT})",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help=f'Backend host (env: EXPLORER_HOST, default: {DEFAULT_BACKEND_HOST})',
    )
    parser.add_argument(
        "--frontend-port",
        type=int,
        default=None,
        help=f"Frontend dev port (env: EXPLORER_FRONTEND_PORT, default: {DEFAULT_FRONTEND_PORT})",
    )
    args = parser.parse_args()

    # Resolve final values: CLI arg > env var > .env file > default.
    backend_port = args.port if args.port is not None else env_int("EXPLORER_PORT", DEFAULT_BACKEND_PORT)
    backend_host = args.host if args.host is not None else env_or_default("EXPLORER_HOST", DEFAULT_BACKEND_HOST)
    frontend_port = (
        args.frontend_port
        if args.frontend_port is not None
        else env_int("EXPLORER_FRONTEND_PORT", DEFAULT_FRONTEND_PORT)
    )

    if args.build_only:
        build_frontend()
        return

    if args.dev:
        start_dev(port=backend_port, host=backend_host, frontend_port=frontend_port)
    else:
        start_production(port=backend_port, host=backend_host)


if __name__ == "__main__":
    main()
