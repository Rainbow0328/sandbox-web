"""Application configuration loaded from environment and optional YAML."""

from __future__ import annotations

import secrets
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for the Sandbox Explorer.

    Values are resolved with priority: environment variable > explorer.yaml > default.
    """

    model_config = SettingsConfigDict(
        env_prefix="EXPLORER_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Deployment identity ---
    public_url: str = "http://localhost:9090"
    admin_token: str = Field(default="", description="Admin bearer token (empty = auth disabled)")
    master_key: str = Field(
        default="0" * 64,
        description="Fernet master key (32-byte hex). Defaults to all-zeros for dev.",
    )

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./data/explorer.db"
    database_echo: bool = False

    # --- Server ---
    host: str = "0.0.0.0"
    port: int = 9090
    workers: int = 1

    # --- History ---
    min_schema: int = 1
    max_schema: int = 1
    sync_query_limit: int = 500
    helper_query_max_bytes: int = 4 * 1024 * 1024
    helper_envelope_max_bytes: int = 1024 * 1024
    sync_interval_seconds: int = 2

    # --- Realtime ---
    heartbeat_interval_seconds: int = 15
    heartbeat_miss_count: int = 3
    command_default_timeout_seconds: int = 300
    command_max_timeout_seconds: int = 3600
    pty_session_timeout_seconds: int = 1800

    # --- Files ---
    max_upload_bytes: int = 100 * 1024 * 1024

    # --- CORS ---
    cors_origins: list[str] = Field(default_factory=list)

    # --- Deployment metadata (generated once, persisted in DB) ---
    deployment_id: str = ""

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v or []

    @property
    def sqlite_path(self) -> Path:
        """Extract the filesystem path from a sqlite+aiosqlite URL."""
        url = self.database_url
        prefix = "sqlite+aiosqlite:///"
        if url.startswith(prefix):
            return Path(url[len(prefix):])
        prefix2 = "sqlite:///"
        if url.startswith(prefix2):
            return Path(url[len(prefix2):])
        return Path("./data/explorer.db")

    def ensure_sqlite_dir(self) -> None:
        """Create parent directory for SQLite database if needed."""
        p = self.sqlite_path
        p.parent.mkdir(parents=True, exist_ok=True)


def _generate_deployment_id() -> str:
    """Generate a random deployment identifier (ULID-like)."""
    ts = int(time.time())
    rand = secrets.token_hex(8)
    return f"dep_{ts:x}_{rand}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached Settings instance.

    The cache is cleared on reload by calling ``get_settings.cache_clear()``.
    """
    settings = Settings()

    # Ensure SQLite directory exists before the engine connects.
    settings.ensure_sqlite_dir()

    # Generate a deployment_id if not set (persisted to system_meta later).
    if not settings.deployment_id:
        settings.deployment_id = _generate_deployment_id()

    return settings


def reload_settings() -> Settings:
    """Clear the cache and return fresh settings (mainly for testing)."""
    get_settings.cache_clear()
    return get_settings()
