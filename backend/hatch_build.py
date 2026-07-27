"""Hatchling build hook: builds the frontend and embeds it into the wheel.

When the wheel is built (``python -m build`` or ``pip install .``), this hook:

1. Detects the frontend source directory (``../frontend`` relative to the
   ``backend/`` project root, or ``../../frontend`` if building from a
   nested location).
2. Runs ``npm install`` and ``npm run build`` to produce ``frontend/dist/``.
3. Copies the built files into ``app/static/`` so they are bundled inside
   the Python wheel.

If Node.js / npm is not available, or the frontend source is missing, the
hook checks whether ``app/static/`` already contains a pre-built frontend
(e.g., copied manually).  If so, that copy is used.  Otherwise, the hook
prints a warning and continues — the backend will start in API-only mode
without the web UI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


def _find_frontend_dir(project_root: Path) -> Path | None:
    """Locate the frontend source directory."""
    # Standard layout: project_root is backend/, frontend is sibling.
    candidates = [
        project_root.parent / "frontend",
        project_root / "frontend",
    ]
    for cand in candidates:
        if (cand / "package.json").exists():
            return cand
    return None


def _npm_available() -> str | None:
    """Return the npm command if available, else None."""
    cmd = "npm.cmd" if sys.platform == "win32" else "npm"
    try:
        subprocess.run(
            [cmd, "--version"],
            capture_output=True,
            check=True,
            shell=sys.platform == "win32",
        )
        return cmd
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None


class CustomBuildHook(BuildHookInterface):
    """Build the frontend and embed it into the wheel."""

    PLUGIN_NAME = "build-frontend"

    def initialize(self, version: str, build_data: dict) -> None:
        project_root = Path(self.root)
        static_dir = project_root / "app" / "static"

        frontend_dir = _find_frontend_dir(project_root)

        if frontend_dir is not None:
            npm = _npm_available()
            if npm is not None:
                self._build_and_copy(frontend_dir, static_dir, npm)
            else:
                print("[build-frontend] npm not found — skipping frontend build")
                self._use_existing_or_warn(static_dir)
        else:
            print("[build-frontend] frontend source not found — skipping build")
            self._use_existing_or_warn(static_dir)

        # Ensure the static directory is included in the wheel.
        # Since app/static/ is inside the ``app`` package, hatchling will include
        # it automatically — but only if the files are not gitignored.  We declare
        # it as an artifact so hatchling knows these are build outputs.
        if static_dir.exists() and any(static_dir.iterdir()):
            artifacts = build_data.setdefault("artifacts", [])
            artifacts.append("app/static/")
            print(f"[build-frontend] Bundled static files from {static_dir}")
        else:
            print("[build-frontend] No static files — wheel will be API-only")

    def _build_and_copy(
        self, frontend_dir: Path, static_dir: Path, npm: str
    ) -> None:
        """Run npm install + build, then copy dist to app/static."""
        shell = sys.platform == "win32"

        # Install dependencies if needed.
        if not (frontend_dir / "node_modules").exists():
            print("[build-frontend] Installing frontend dependencies...")
            result = subprocess.run(
                [npm, "install", "--legacy-peer-deps"],
                cwd=str(frontend_dir),
                shell=shell,
            )
            if result.returncode != 0:
                print("[build-frontend] npm install failed — skipping frontend")
                return

        # Build the frontend.
        print("[build-frontend] Building frontend (npm run build)...")
        result = subprocess.run(
            [npm, "run", "build"],
            cwd=str(frontend_dir),
            shell=shell,
        )
        if result.returncode != 0:
            print("[build-frontend] npm run build failed — skipping frontend")
            return

        dist_dir = frontend_dir / "dist"
        if not dist_dir.exists():
            print("[build-frontend] dist/ not found after build — skipping")
            return

        # Copy dist → app/static (replace existing).
        if static_dir.exists():
            shutil.rmtree(static_dir)
        shutil.copytree(dist_dir, static_dir)
        print(f"[build-frontend] Copied {dist_dir} → {static_dir}")

    def _use_existing_or_warn(self, static_dir: Path) -> None:
        """Check if app/static already has pre-built files."""
        if static_dir.exists() and any(static_dir.iterdir()):
            # Skip .gitkeep files.
            real_files = [f for f in static_dir.rglob("*") if f.name != ".gitkeep"]
            if real_files:
                print(f"[build-frontend] Using pre-built static files in {static_dir}")
                return
        print("[build-frontend] No pre-built frontend found — wheel will be API-only")
