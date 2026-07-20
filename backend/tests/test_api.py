"""Integration tests for Sandbox Explorer API — covers §19.3 acceptance checklist."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

# ---------------------------------------------------------------------------
# Health checks (§19.3 item 1, 12)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_healthz(client: AsyncClient):
    """§19.3: /healthz returns 200."""
    resp = await client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readyz(client: AsyncClient):
    """§19.3: /readyz returns ready (DB connection works)."""
    resp = await client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_metrics(client: AsyncClient):
    """§19.3: /metrics returns Prometheus text format."""
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert "text/plain" in resp.headers.get("content-type", "")


# ---------------------------------------------------------------------------
# Auth (§19.3 item 2, 12)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient):
    """§19.3: Admin Token login succeeds."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"token": "test-admin-token-1234567890"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "session_token" in data
    assert data["actor_id"] == "admin"


@pytest.mark.asyncio
async def test_login_failure(client: AsyncClient):
    """Invalid token is rejected."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"token": "wrong-token"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_me(client: AsyncClient, auth_headers: dict):
    """§19.3: GET /auth/me returns current actor."""
    resp = await client.get("/api/v1/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["actor_id"] == "admin"


@pytest.mark.asyncio
async def test_unauthorized_request(client: AsyncClient):
    """§19.3: WebSocket/proxy auth — unauthenticated requests are rejected."""
    resp = await client.get("/api/v1/connections")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Connections (§19.3 item 2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_connections_empty(client: AsyncClient, auth_headers: dict):
    """List connections returns empty initially."""
    resp = await client.get("/api/v1/connections", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_create_connection(client: AsyncClient, auth_headers: dict):
    """Create a connection."""
    resp = await client.post(
        "/api/v1/connections",
        json={
            "name": "test-connection",
            "provider_type": "fake",
            "endpoint": "http://localhost",
            "auth_method": "api_key",
            "credentials": {"api_key": "key123"},
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "test-connection"
    assert data["provider_type"] == "fake"
    assert data["enabled"] is True


@pytest.mark.asyncio
async def test_test_connection(client: AsyncClient, auth_headers: dict, connection_id: str):
    """§19.3: test_connection returns capabilities."""
    resp = await client.post(f"/api/v1/connections/{connection_id}/test", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["capabilities"] is not None


# ---------------------------------------------------------------------------
# Sandboxes (§19.3 item 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_sandbox(client: AsyncClient, auth_headers: dict, connection_id: str):
    """Create a sandbox."""
    resp = await client.post(
        f"/api/v1/connections/{connection_id}/sandboxes",
        json={"image": "python:3.12", "workdir": "/workspace"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["state"] == "running"
    assert data["image"] == "python:3.12"


@pytest.mark.asyncio
async def test_get_sandbox(
    client: AsyncClient, auth_headers: dict, connection_id: str, sandbox_id: str
):
    """Get a sandbox by ID."""
    resp = await client.get(
        f"/api/v1/connections/{connection_id}/sandboxes/{sandbox_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["sandbox_id"] == sandbox_id


@pytest.mark.asyncio
async def test_get_capabilities(
    client: AsyncClient, auth_headers: dict, connection_id: str, sandbox_id: str
):
    """§19.3: Get capabilities for a sandbox."""
    resp = await client.get(
        f"/api/v1/connections/{connection_id}/sandboxes/{sandbox_id}/capabilities",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    caps = resp.json()
    assert caps["filesystem"]["supported"] is True
    assert caps["command_execution"]["supported"] is True


@pytest.mark.asyncio
async def test_pause_resume_sandbox(
    client: AsyncClient, auth_headers: dict, connection_id: str, sandbox_id: str
):
    """Pause and resume a sandbox."""
    # Pause
    resp = await client.post(
        f"/api/v1/connections/{connection_id}/sandboxes/{sandbox_id}/pause",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "paused"

    # Resume
    resp = await client.post(
        f"/api/v1/connections/{connection_id}/sandboxes/{sandbox_id}/resume",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["state"] == "running"


# ---------------------------------------------------------------------------
# Files (§19.3 item 5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_files(
    client: AsyncClient, auth_headers: dict, connection_id: str, sandbox_id: str
):
    """§19.3: List files in a sandbox."""
    resp = await client.get(
        f"/api/v1/connections/{connection_id}/sandboxes/{sandbox_id}/files?path=/workspace",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    entries = resp.json()["entries"]
    assert len(entries) >= 2  # README.md and app.py


@pytest.mark.asyncio
async def test_read_file(
    client: AsyncClient, auth_headers: dict, connection_id: str, sandbox_id: str
):
    """§19.3: Read file content."""
    resp = await client.get(
        f"/api/v1/connections/{connection_id}/sandboxes/{sandbox_id}/file?path=/workspace/app.py",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "content" in data
    assert "content_hash" in data
    assert data["is_binary"] is False


@pytest.mark.asyncio
async def test_write_file(
    client: AsyncClient, auth_headers: dict, connection_id: str, sandbox_id: str
):
    """§19.3: Write file with If-Match optimistic concurrency."""
    # Read first to get hash.
    resp = await client.get(
        f"/api/v1/connections/{connection_id}/sandboxes/{sandbox_id}/file?path=/workspace/app.py",
        headers=auth_headers,
    )
    original_hash = resp.json()["content_hash"]

    # Write with correct hash.
    resp = await client.put(
        f"/api/v1/connections/{connection_id}/sandboxes/{sandbox_id}/file?path=/workspace/app.py",
        json={"content": "print('updated')\n", "expected_hash": original_hash},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["content_hash"] != original_hash


@pytest.mark.asyncio
async def test_path_escape_blocked(
    client: AsyncClient, auth_headers: dict, connection_id: str, sandbox_id: str
):
    """§19.3: Path escape (..) is blocked."""
    resp = await client.get(
        f"/api/v1/connections/{connection_id}/sandboxes/{sandbox_id}/file?path=/workspace/../../../etc/passwd",
        headers=auth_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "path_escape"


# ---------------------------------------------------------------------------
# Commands (§19.3 item 6)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_command(
    client: AsyncClient, auth_headers: dict, connection_id: str, sandbox_id: str
):
    """§19.3: Execute a command and get result."""
    resp = await client.post(
        f"/api/v1/connections/{connection_id}/sandboxes/{sandbox_id}/commands",
        json={"command": "echo hello", "cwd": "/workspace"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "command_id" in data
    assert data["status"] == "succeeded"


@pytest.mark.asyncio
async def test_command_stream(
    client: AsyncClient, auth_headers: dict, connection_id: str, sandbox_id: str
):
    """§19.3: SSE stream returns output events."""
    # Create command.
    resp = await client.post(
        f"/api/v1/connections/{connection_id}/sandboxes/{sandbox_id}/commands",
        json={"command": "echo test", "cwd": "/workspace"},
        headers=auth_headers,
    )
    cmd_id = resp.json()["command_id"]

    # Stream events.
    resp = await client.get(
        f"/api/v1/connections/{connection_id}/sandboxes/{sandbox_id}/commands/{cmd_id}/stream",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "data:" in resp.text
    assert "output" in resp.text
    assert "finished" in resp.text


# ---------------------------------------------------------------------------
# History (§19.3 item 8, 10, 11)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_history(
    client: AsyncClient, auth_headers: dict, connection_id: str, sandbox_id: str
):
    """§19.3: History returns events with Coverage badge."""
    # Sync first so projection has data.
    await client.post(
        f"/api/v1/sandboxes/{connection_id}/{sandbox_id}/history/sync",
        headers=auth_headers,
    )
    resp = await client.get(
        f"/api/v1/sandboxes/{connection_id}/{sandbox_id}/history",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    # Coverage badge is always present (§7).
    assert "coverage" in data
    assert data["helper_status"] == "available"
    assert data["total"] >= 1  # At least sandbox.create event


@pytest.mark.asyncio
async def test_history_availability(
    client: AsyncClient, auth_headers: dict, connection_id: str, sandbox_id: str
):
    """§19.3: History availability endpoint."""
    resp = await client.get(
        f"/api/v1/sandboxes/{connection_id}/{sandbox_id}/history/availability",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["available"] is True


@pytest.mark.asyncio
async def test_history_sync(
    client: AsyncClient, auth_headers: dict, connection_id: str, sandbox_id: str
):
    """§19.3: Manual history sync."""
    resp = await client.post(
        f"/api/v1/sandboxes/{connection_id}/{sandbox_id}/history/sync",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["synced"] >= 1


# ---------------------------------------------------------------------------
# Sandboxes list (§19.3 item 3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_sandboxes(
    client: AsyncClient, auth_headers: dict, connection_id: str, sandbox_id: str
):
    """§19.3: Cross-connection sandbox list."""
    resp = await client.get("/api/v1/sandboxes", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(s["sandbox_id"] == sandbox_id for s in data["items"])
