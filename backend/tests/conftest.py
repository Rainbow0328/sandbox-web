"""Test configuration and fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure backend app is importable.
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# Set test environment variables before importing app modules.
os.environ.setdefault("EXPLORER_ADMIN_TOKEN", "test-admin-token-1234567890")
os.environ.setdefault("EXPLORER_MASTER_KEY", "a" * 64)
os.environ.setdefault("EXPLORER_DATABASE_URL", "sqlite+aiosqlite:///./data/test_explorer.db")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client():
    """Create an async HTTP client for the FastAPI app."""
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # Startup: create tables.
        from app.db.base import Base
        from app.db.engine import get_engine

        engine = get_engine()
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        yield c

        # Cleanup: drop tables and dispose engine.
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        from app.db.engine import dispose_engine

        await dispose_engine()


@pytest_asyncio.fixture
async def auth_token(client: AsyncClient):
    """Login and return a session token."""
    token = os.environ.get("EXPLORER_ADMIN_TOKEN", "test-admin-token-1234567890")
    resp = await client.post(
        "/api/v1/auth/login",
        json={"token": token},
    )
    assert resp.status_code == 200
    return resp.json()["session_token"]


@pytest_asyncio.fixture
async def auth_headers(auth_token: str):
    """Return Authorization headers for authenticated requests."""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest_asyncio.fixture
async def connection_id(client: AsyncClient, auth_headers: dict):
    """Create a fake connection and return its ID."""
    resp = await client.post(
        "/api/v1/connections",
        json={
            "name": "test-fake",
            "provider_type": "fake",
            "endpoint": "http://localhost",
            "auth_method": "api_key",
            "credentials": {"api_key": "test"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()["id"]


@pytest_asyncio.fixture
async def sandbox_id(client: AsyncClient, auth_headers: dict, connection_id: str):
    """Create a sandbox and return its ID."""
    resp = await client.post(
        f"/api/v1/connections/{connection_id}/sandboxes",
        json={"image": "python:3.12", "workdir": "/workspace"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()["sandbox_id"]
