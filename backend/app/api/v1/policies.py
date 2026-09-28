"""Policy management API routes.

Endpoints:
  POST   /policies/register      — SDK registration + preset push
  POST   /policies/push            — Push updates to SDKs
  GET    /policies/listen         — Long-poll for updates
  GET    /policies/full           — One-shot full fetch
  GET    /policies/groups         — List groups
  POST   /policies/groups         — Create group
  GET    /policies/groups/{id}    — Get group detail
  PUT    /policies/groups/{id}    — Update group
  DELETE /policies/groups/{id}    — Delete group
  GET    /policies/groups/{id}/rules         — List rules
  POST   /policies/groups/{id}/rules         — Create rule
  PUT    /policies/rules/{id}                — Update rule
  DELETE /policies/rules/{id}                — Delete rule
  GET    /sandboxes/by-name/{name}           — Lookup sandbox by name (reuse)
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.core.deps import SessionDep
from app.services import policy_service

router = APIRouter(tags=["policies"])


# ── Request/Response schemas ─────────────────────────────────────────

class RegisterRequest(BaseModel):
    sdk_version: str = ""
    policy_group: str
    sandbox_id: str
    sandbox_name: str | None = None
    agent_name: str | None = None
    callback_url: str | None = None
    callback_mode: str = "long_poll"
    preset_rules: list[dict[str, Any]] | None = None
    baseline_rules: list[dict[str, Any]] | None = None


class CreateGroupRequest(BaseModel):
    name: str
    description: str = ""


class UpdateGroupRequest(BaseModel):
    name: str | None = None
    description: str | None = None
    enabled: bool | None = None


class CreateRuleRequest(BaseModel):
    rule_type: str = Field(..., description="command | workspace")
    pattern: str
    effect: str = "allow"
    operations: str = "read,write,execute"
    priority: int = 0
    description: str = ""
    is_baseline: bool = False
    sandbox_id: str | None = Field(
        default=None,
        description="When set, this rule only applies to this sandbox (sandbox-level override)",
    )


class UpdateRuleRequest(BaseModel):
    pattern: str | None = None
    effect: str | None = None
    operations: str | None = None
    priority: int | None = None
    description: str | None = None


class PushRequest(BaseModel):
    group_id: str


# ── SDK Registration ─────────────────────────────────────────────────

@router.post("/policies/register")
async def register_sdk(
    request: RegisterRequest,
    session: SessionDep,
) -> dict[str, Any]:
    """SDK registration endpoint.

    SDK pushes its preset rules + baseline on startup.  Console
    returns the merged current rules + version.
    """
    return await policy_service.register_sdk(
        session,
        policy_group=request.policy_group,
        sandbox_id=request.sandbox_id,
        sandbox_name=request.sandbox_name,
        agent_name=request.agent_name,
        sdk_version=request.sdk_version,
        callback_url=request.callback_url,
        callback_mode=request.callback_mode,
        preset_rules=request.preset_rules,
        baseline_rules=request.baseline_rules,
    )


# ── Push ─────────────────────────────────────────────────────────────

@router.post("/policies/push")
async def push_policy(
    request: PushRequest,
    session: SessionDep,
) -> dict[str, Any]:
    """Manually trigger a policy push to all registered SDKs."""
    return await policy_service.push_policy_to_sdk(session, request.group_id)


# ── Long-poll ─────────────────────────────────────────────────────────

@router.get("/policies/listen")
async def listen_for_updates(
    session: SessionDep,
    group: str,
    sandbox_id: str = "",
    version: int = 0,
    agent: str | None = None,
) -> dict[str, Any]:
    """Long-poll: blocks until policy version > current, then returns rules.

    When *sandbox_id* is provided, returns only group-level + that sandbox's rules.
    """
    result = await policy_service.listen_for_updates(
        session, group, version, timeout=300.0,
        sandbox_id=sandbox_id or None,
    )
    if result is None:
        raise HTTPException(status_code=304, detail="No updates")
    return result


# ── Full fetch ────────────────────────────────────────────────────────

@router.get("/policies/full")
async def get_full_policy(
    session: SessionDep,
    group: str,
    sandbox_id: str = "",
) -> dict[str, Any]:
    """One-shot full fetch of all rules for a group."""
    result = await policy_service.get_full_policy(session, group, sandbox_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return result


# ── Group CRUD ───────────────────────────────────────────────────────

@router.get("/policies/groups")
async def list_groups(session: SessionDep) -> list[dict[str, Any]]:
    return await policy_service.list_groups(session)


@router.post("/policies/groups", status_code=201)
async def create_group(
    request: CreateGroupRequest,
    session: SessionDep,
) -> dict[str, Any]:
    return await policy_service.create_group(
        session, name=request.name, description=request.description,
    )


@router.get("/policies/groups/{group_id}")
async def get_group(
    group_id: str,
    session: SessionDep,
) -> dict[str, Any]:
    result = await policy_service.get_group(session, group_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return result


@router.put("/policies/groups/{group_id}")
async def update_group(
    group_id: str,
    request: UpdateGroupRequest,
    session: SessionDep,
) -> dict[str, Any]:
    result = await policy_service.update_group(
        session, group_id,
        name=request.name,
        description=request.description,
        enabled=request.enabled,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return result


@router.delete("/policies/groups/{group_id}")
async def delete_group(
    group_id: str,
    session: SessionDep,
) -> dict[str, Any]:
    ok = await policy_service.delete_group(session, group_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Group not found")
    return {"deleted": True}


# ── Rule CRUD ────────────────────────────────────────────────────────

@router.get("/policies/groups/{group_id}/rules")
async def list_rules(
    group_id: str,
    session: SessionDep,
    sandbox_id: str | None = None,
) -> list[dict[str, Any]]:
    """List rules for a group.

    If *sandbox_id* query param is provided, returns group-level + sandbox-level rules.
    Otherwise returns all rules.
    """
    return await policy_service.list_rules(session, group_id, sandbox_id=sandbox_id)


@router.post("/policies/groups/{group_id}/rules", status_code=201)
async def create_rule(
    group_id: str,
    request: CreateRuleRequest,
    session: SessionDep,
) -> dict[str, Any]:
    return await policy_service.create_rule(
        session, group_id,
        rule_type=request.rule_type,
        pattern=request.pattern,
        effect=request.effect,
        operations=request.operations,
        priority=request.priority,
        description=request.description,
        is_baseline=request.is_baseline,
        sandbox_id=request.sandbox_id,
    )


@router.put("/policies/rules/{rule_id}")
async def update_rule(
    rule_id: str,
    request: UpdateRuleRequest,
    session: SessionDep,
) -> dict[str, Any]:
    result = await policy_service.update_rule(
        session, rule_id,
        pattern=request.pattern,
        effect=request.effect,
        operations=request.operations,
        priority=request.priority,
        description=request.description,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return result


@router.delete("/policies/rules/{rule_id}")
async def delete_rule(
    rule_id: str,
    session: SessionDep,
) -> dict[str, Any]:
    ok = await policy_service.delete_rule(session, rule_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"deleted": True}


# ── Sandbox reuse lookup ─────────────────────────────────────────────

@router.get("/sandboxes/by-name/{name}")
async def lookup_sandbox_by_name(
    name: str,
    session: SessionDep,
) -> dict[str, Any]:
    """Lookup a sandbox by name for reuse-by-name."""
    result = await policy_service.lookup_sandbox_by_name(session, name)
    if result is None:
        raise HTTPException(status_code=404, detail="Sandbox not found")
    return result


@router.get("/policies/sandbox/{sandbox_id}")
async def get_rules_for_sandbox(
    sandbox_id: str,
    session: SessionDep,
) -> dict[str, Any]:
    """Get the policy group and rules for a specific sandbox.

    Returns group-level + sandbox-level rules for the sandbox's group.
    """
    result = await policy_service.get_rules_for_sandbox(session, sandbox_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Sandbox not registered to any group")
    return result
