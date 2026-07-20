"""Realtime terminal WebSocket — command execution via adapter.execute()."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC

from fastapi import WebSocket, WebSocketDisconnect

from app.adapters.base import ExecRequest
from app.db.engine import get_session_factory
from app.services.file_service import get_sandbox_ref


async def _verify_ws_token(token: str) -> str | None:
    from app.core.config import get_settings
    settings = get_settings()
    if not settings.admin_token:
        return "admin"
    from app.core.security import verify_admin_token
    if verify_admin_token(token):
        return "admin"
    from sqlalchemy import select

    from app.models.session import Session
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(select(Session).where(Session.id == token))
        sess = result.scalar_one_or_none()
        if sess is None:
            return None
        from datetime import datetime
        now = datetime.now(UTC)
        expires = datetime.fromisoformat(sess.expires_at.replace("Z", "+00:00"))
        if expires < now:
            return None
        return sess.actor_id


async def handle_terminal_websocket(
    websocket: WebSocket,
    connection_id: str,
    sandbox_id: str,
) -> None:
    token = websocket.query_params.get("token", "")
    actor = await _verify_ws_token(token)
    if actor is None:
        await websocket.close(code=4401)
        return

    await websocket.accept()

    factory = get_session_factory()
    async with factory() as session:
        try:
            ref, adapter, connection = await get_sandbox_ref(session, connection_id, sandbox_id)
        except Exception as exc:
            await websocket.send_json({"type": "error", "message": str(exc)})
            await websocket.close(code=4404)
            return

    cwd = connection.default_workdir or "/workspace"
    await websocket.send_json({
        "type": "output",
        "data": f"Connected to sandbox {sandbox_id}\r\nuser@{sandbox_id}:{cwd}$ ",
    })

    input_buffer = ""
    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=1800)
            except TimeoutError:
                await websocket.send_json({"type": "closed", "reason": "timeout"})
                break

            data = json.loads(msg)
            if data.get("type") == "input":
                raw = data.get("data", "")
                # Normalize \r to \n so Enter triggers execution.
                input_buffer += raw.replace("\r", "\n")

                while "\n" in input_buffer:
                    line, input_buffer = input_buffer.split("\n", 1)
                    cmd = line.strip()

                    if not cmd:
                        await websocket.send_json({"type": "output", "data": f"user@{sandbox_id}:{cwd}$ "})
                        continue

                    if cmd == "exit":
                        await websocket.send_json({"type": "closed", "reason": "user exit"})
                        return

                    if cmd == "clear":
                        await websocket.send_json({"type": "output", "data": "\x1b[2J\x1b[H"})
                        await websocket.send_json({"type": "output", "data": f"user@{sandbox_id}:{cwd}$ "})
                        continue

                    # Handle cd command locally.
                    if cmd.startswith("cd "):
                        new_dir = cmd[3:].strip()
                        if new_dir == "..":
                            cwd = "/".join(cwd.rstrip("/").split("/")[:-1]) or "/"
                        elif new_dir.startswith("/"):
                            cwd = new_dir
                        else:
                            cwd = f"{cwd.rstrip('/')}/{new_dir}"
                        await websocket.send_json({"type": "output", "data": f"user@{sandbox_id}:{cwd}$ "})
                        continue

                    try:
                        exec_request = ExecRequest(command=cmd, cwd=cwd)
                        result = await adapter.execute(ref, exec_request)
                        if result.stdout:
                            await websocket.send_json({"type": "output", "data": result.stdout_text})
                        if result.stderr:
                            await websocket.send_json({"type": "output", "data": result.stderr_text})
                    except Exception as exc:
                        await websocket.send_json({"type": "output", "data": f"Error: {exc}\r\n"})

                    await websocket.send_json({"type": "output", "data": f"user@{sandbox_id}:{cwd}$ "})

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await websocket.send_json({"type": "error", "message": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
