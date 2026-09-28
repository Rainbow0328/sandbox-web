"""Policy management service: CRUD, registration, push, long-poll, lookup."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy import (
    ActiveWorkspace,
    PolicyGroup,
    PolicyRule,
    SdkRegistration,
)


def _utc_now() -> str:
    """Return a UTC timestamp string in ISO-8601 format."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# In-memory versioning for long-poll: group_id -> (version, asyncio.Event)
_poll_events: dict[str, tuple[int, asyncio.Event]] = {}


def _new_id() -> str:
    """Generate a 26-char ID (compact UUID)."""
    return uuid.uuid4().hex[:26]


# ── Group CRUD ───────────────────────────────────────────────────────

async def list_groups(session: AsyncSession) -> list[dict[str, Any]]:
    result = await session.execute(
        select(PolicyGroup).where(PolicyGroup.enabled == True)  # noqa: E712
    )
    groups = result.scalars().all()
    return [_group_to_dict(g) for g in groups]


async def get_group(session: AsyncSession, group_id: str) -> dict[str, Any] | None:
    result = await session.execute(
        select(PolicyGroup).where(PolicyGroup.id == group_id)
    )
    g = result.scalar_one_or_none()
    if g is None:
        return None
    return _group_to_dict(g)


async def create_group(
    session: AsyncSession,
    *,
    name: str,
    description: str = "",
) -> dict[str, Any]:
    g = PolicyGroup(
        id=_new_id(),
        name=name,
        description=description,
        version=1,
        enabled=True,
    )
    session.add(g)
    await session.commit()
    await session.refresh(g)
    return _group_to_dict(g)


async def update_group(
    session: AsyncSession,
    group_id: str,
    *,
    name: str | None = None,
    description: str | None = None,
    enabled: bool | None = None,
) -> dict[str, Any] | None:
    values: dict[str, Any] = {"updated_at": _utc_now()}
    if name is not None:
        values["name"] = name
    if description is not None:
        values["description"] = description
    if enabled is not None:
        values["enabled"] = enabled
    await session.execute(
        update(PolicyGroup).where(PolicyGroup.id == group_id).values(**values)
    )
    await session.commit()
    return await get_group(session, group_id)


async def delete_group(session: AsyncSession, group_id: str) -> bool:
    result = await session.execute(
        select(PolicyGroup).where(PolicyGroup.id == group_id)
    )
    g = result.scalar_one_or_none()
    if g is None:
        return False
    await session.delete(g)
    await session.commit()
    return True


# ── Rule CRUD ───────────────────────────────────────────────────────

async def list_rules(
    session: AsyncSession,
    group_id: str,
    *,
    sandbox_id: str | None = None,
) -> list[dict[str, Any]]:
    """List rules for a group.

    If *sandbox_id* is provided, returns both group-level rules (sandbox_id IS NULL)
    and sandbox-level rules (sandbox_id == sandbox_id).
    Otherwise returns all rules in the group.
    """
    if sandbox_id:
        result = await session.execute(
            select(PolicyRule)
            .where(
                PolicyRule.group_id == group_id,
                (PolicyRule.sandbox_id.is_(None)) | (PolicyRule.sandbox_id == sandbox_id),
            )
            .order_by(PolicyRule.priority.desc())
        )
    else:
        result = await session.execute(
            select(PolicyRule)
            .where(PolicyRule.group_id == group_id)
            .order_by(PolicyRule.priority.desc())
        )
    rules = result.scalars().all()
    return [_rule_to_dict(r) for r in rules]


async def create_rule(
    session: AsyncSession,
    group_id: str,
    *,
    rule_type: str,
    pattern: str,
    effect: str = "allow",
    operations: str = "read,write,execute",
    priority: int = 0,
    description: str = "",
    is_baseline: bool = False,
    sandbox_id: str | None = None,
) -> dict[str, Any]:
    r = PolicyRule(
        id=_new_id(),
        group_id=group_id,
        sandbox_id=sandbox_id,
        rule_type=rule_type,
        pattern=pattern,
        effect=effect,
        operations=operations,
        priority=priority,
        description=description,
        is_baseline=is_baseline,
    )
    session.add(r)
    # Bump group version
    await session.execute(
        update(PolicyGroup)
        .where(PolicyGroup.id == group_id)
        .values(
            version=PolicyGroup.version + 1,
            updated_at=_utc_now(),
        )
    )
    await session.commit()
    await session.refresh(r)
    _notify_poll(group_id)
    return _rule_to_dict(r)


async def update_rule(
    session: AsyncSession,
    rule_id: str,
    *,
    pattern: str | None = None,
    effect: str | None = None,
    operations: str | None = None,
    priority: int | None = None,
    description: str | None = None,
) -> dict[str, Any] | None:
    result = await session.execute(
        select(PolicyRule).where(PolicyRule.id == rule_id)
    )
    r = result.scalar_one_or_none()
    if r is None:
        return None
    if pattern is not None:
        r.pattern = pattern
    if effect is not None:
        r.effect = effect
    if operations is not None:
        r.operations = operations
    if priority is not None:
        r.priority = priority
    if description is not None:
        r.description = description
    r.updated_at = _utc_now()
    # Bump group version
    await session.execute(
        update(PolicyGroup)
        .where(PolicyGroup.id == r.group_id)
        .values(
            version=PolicyGroup.version + 1,
            updated_at=_utc_now(),
        )
    )
    await session.commit()
    _notify_poll(r.group_id)
    return _rule_to_dict(r)


async def delete_rule(session: AsyncSession, rule_id: str) -> bool:
    result = await session.execute(
        select(PolicyRule).where(PolicyRule.id == rule_id)
    )
    r = result.scalar_one_or_none()
    if r is None:
        return False
    group_id = r.group_id
    await session.delete(r)
    await session.execute(
        update(PolicyGroup)
        .where(PolicyGroup.id == group_id)
        .values(
            version=PolicyGroup.version + 1,
            updated_at=_utc_now(),
        )
    )
    await session.commit()
    _notify_poll(group_id)
    return True


# ── SDK Registration ─────────────────────────────────────────────────

async def register_sdk(
    session: AsyncSession,
    *,
    policy_group: str,
    sandbox_id: str,
    sandbox_name: str | None = None,
    agent_name: str | None = None,
    sdk_version: str = "",
    callback_url: str | None = None,
    callback_mode: str = "long_poll",
    preset_rules: list[dict[str, Any]] | None = None,
    baseline_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Register an SDK instance.  Returns current rules + version."""

    # Find or create the group by name
    result = await session.execute(
        select(PolicyGroup).where(PolicyGroup.name == policy_group)
    )
    group = result.scalar_one_or_none()
    if group is None:
        group = PolicyGroup(
            id=_new_id(),
            name=policy_group,
            description=f"Auto-created from SDK registration",
            version=1,
            enabled=True,
        )
        session.add(group)
        await session.flush()

    # If preset rules are provided and the group is new (no rules yet),
    # import them
    existing_rules_result = await session.execute(
        select(PolicyRule).where(PolicyRule.group_id == group.id)
    )
    existing_rules = existing_rules_result.scalars().all()
    if not existing_rules and preset_rules:
        for pr in preset_rules:
            session.add(PolicyRule(
                id=_new_id(),
                group_id=group.id,
                rule_type=pr.get("rule_type", "command"),
                pattern=pr.get("pattern", ""),
                effect=pr.get("effect", "allow"),
                operations=pr.get("operations", "read,write,execute"),
                priority=pr.get("priority", 0),
                description=pr.get("description", ""),
                is_baseline=False,
            ))
    # Baseline rules are always imported (they are immutable deny rules)
    if baseline_rules:
        # Delete old baselines first
        old_baselines = [r for r in existing_rules if r.is_baseline]
        for old in old_baselines:
            await session.delete(old)
        for br in baseline_rules:
            session.add(PolicyRule(
                id=_new_id(),
                group_id=group.id,
                rule_type=br.get("rule_type", "command"),
                pattern=br.get("pattern", ""),
                effect=br.get("effect", "deny"),
                operations=br.get("operations", "read,write,execute"),
                priority=999,
                description=br.get("description", ""),
                is_baseline=True,
            ))
        group.version += 1

    # Upsert SDK registration
    reg_result = await session.execute(
        select(SdkRegistration).where(
            SdkRegistration.sandbox_id == sandbox_id,
            SdkRegistration.group_id == group.id,
        )
    )
    reg = reg_result.scalar_one_or_none()
    if reg is None:
        reg = SdkRegistration(
            id=_new_id(),
            group_id=group.id,
            sandbox_id=sandbox_id,
            sandbox_name=sandbox_name,
            agent_name=agent_name,
            sdk_version=sdk_version,
            callback_url=callback_url,
            callback_mode=callback_mode,
            last_seen=_utc_now(),
            online=True,
        )
        session.add(reg)
    else:
        reg.sandbox_name = sandbox_name or reg.sandbox_name
        reg.agent_name = agent_name or reg.agent_name
        reg.sdk_version = sdk_version or reg.sdk_version
        reg.callback_url = callback_url
        reg.callback_mode = callback_mode
        reg.last_seen = _utc_now()
        reg.online = True

    # Upsert active workspace
    ws_result = await session.execute(
        select(ActiveWorkspace).where(
            ActiveWorkspace.sandbox_name == sandbox_name
        )
    )
    ws = ws_result.scalar_one_or_none()
    if ws is None and sandbox_name:
        ws = ActiveWorkspace(
            id=_new_id(),
            sandbox_id=sandbox_id,
            sandbox_name=sandbox_name,
            agent_name=agent_name,
            group_id=group.id,
            active=True,
        )
        session.add(ws)
    elif ws is not None:
        ws.sandbox_id = sandbox_id
        ws.agent_name = agent_name or ws.agent_name
        ws.group_id = group.id
        ws.active = True

    await session.commit()
    _notify_poll(group.id)

    # Return current rules + version (filtered to this sandbox)
    rules = await list_rules(session, group.id, sandbox_id=sandbox_id)
    return {
        "group_id": group.id,
        "group_name": group.name,
        "version": group.version,
        "rules": rules,
    }


# ── Push to SDK ──────────────────────────────────────────────────────

async def push_policy_to_sdk(
    session: AsyncSession,
    group_id: str,
) -> dict[str, Any]:
    """Push the latest policy to all registered SDK callbacks.

    For push-mode SDKs: send HTTP POST to callback_url with the rules
    filtered to that SDK's sandbox (group-level + that sandbox's rules).
    For long-poll SDKs: the _notify_poll will wake them up.
    """
    result = await session.execute(
        select(SdkRegistration).where(
            SdkRegistration.group_id == group_id,
            SdkRegistration.online == True,  # noqa: E712
        )
    )
    regs = result.scalars().all()

    group_result = await session.execute(
        select(PolicyGroup).where(PolicyGroup.id == group_id)
    )
    group = group_result.scalar_one_or_none()
    version = group.version if group else 0

    pushed = 0
    failed = 0
    for reg in regs:
        if reg.callback_url and reg.callback_mode == "push":
            # Push only rules relevant to this sandbox:
            # group-level (sandbox_id IS NULL) + sandbox-level (sandbox_id == reg.sandbox_id)
            sandbox_rules = await list_rules(
                session, group_id, sandbox_id=reg.sandbox_id,
            )
            try:
                async with httpx.AsyncClient(timeout=5) as client:
                    resp = await client.post(
                        f"{reg.callback_url}/policy-update",
                        json={"rules": sandbox_rules, "version": version},
                    )
                    if resp.status_code == 200:
                        pushed += 1
                    else:
                        failed += 1
            except Exception:
                failed += 1
        else:
            # Long-poll: the _notify_poll already triggered their wake-up
            pushed += 1

    # Also wake up long-poll listeners
    _notify_poll(group_id)

    return {
        "pushed": pushed,
        "failed": failed,
        "version": version,
        "total_registrations": len(regs),
    }


# ── Long-poll ────────────────────────────────────────────────────────

async def listen_for_updates(
    session: AsyncSession,
    group_id: str,
    current_version: int,
    timeout: float = 300.0,
    sandbox_id: str | None = None,
) -> dict[str, Any] | None:
    """Long-poll: wait until policy version > current_version.

    Returns the updated rules + version, or None on timeout.
    When *sandbox_id* is provided, returns only group-level + that sandbox's rules.
    """
    # Check if group exists
    group_result = await session.execute(
        select(PolicyGroup).where(PolicyGroup.id == group_id)
    )
    group = group_result.scalar_one_or_none()
    if group is None:
        # Try by name
        group_result = await session.execute(
            select(PolicyGroup).where(PolicyGroup.name == group_id)
        )
        group = group_result.scalar_one_or_none()
        if group is None:
            return None
        group_id = group.id

    if group.version > current_version:
        rules = await list_rules(session, group_id, sandbox_id=sandbox_id)
        return {"rules": rules, "version": group.version}

    # Wait for a notification
    event = _get_or_create_poll_event(group_id)
    try:
        await asyncio.wait_for(event[1].wait(), timeout=timeout)
    except asyncio.TimeoutError:
        return None

    # Re-fetch
    rules = await list_rules(session, group_id, sandbox_id=sandbox_id)
    group_result = await session.execute(
        select(PolicyGroup).where(PolicyGroup.id == group_id)
    )
    group = group_result.scalar_one_or_none()
    version = group.version if group else current_version
    return {"rules": rules, "version": version}


async def get_full_policy(
    session: AsyncSession,
    group_id_or_name: str,
    sandbox_id: str | None = None,
) -> dict[str, Any] | None:
    """One-shot full fetch of all rules for a group.

    When *sandbox_id* is provided, returns group-level + that sandbox's rules.
    """
    group = await _resolve_group(session, group_id_or_name)
    if group is None:
        return None
    rules = await list_rules(session, group.id, sandbox_id=sandbox_id)
    return {"rules": rules, "version": group.version}


# ── Sandbox reuse lookup ─────────────────────────────────────────────

async def lookup_sandbox_by_name(
    session: AsyncSession,
    name: str,
) -> dict[str, Any] | None:
    """Find an active sandbox by name for reuse."""
    result = await session.execute(
        select(ActiveWorkspace).where(
            ActiveWorkspace.sandbox_name == name,
            ActiveWorkspace.active == True,  # noqa: E712
        )
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        return None
    return {
        "sandbox_id": ws.sandbox_id,
        "sandbox_instance_id": ws.sandbox_instance_id,
        "provider_name": ws.provider_name,
        "provider_key": ws.provider_key,
        "agent_name": ws.agent_name,
    }


async def deactivate_workspace(
    session: AsyncSession,
    sandbox_id: str,
) -> bool:
    """Mark a workspace as inactive (e.g., sandbox deleted)."""
    result = await session.execute(
        select(ActiveWorkspace).where(
            ActiveWorkspace.sandbox_id == sandbox_id,
        )
    )
    ws = result.scalar_one_or_none()
    if ws is None:
        return False
    ws.active = False
    ws.updated_at = _utc_now()
    await session.commit()
    return True


async def get_rules_for_sandbox(
    session: AsyncSession,
    sandbox_id: str,
) -> dict[str, Any] | None:
    """Find the group and rules for a sandbox by sandbox_id.

    Looks up the ActiveWorkspace to find the group_id, then returns
    group-level + sandbox-level rules for that sandbox.
    """
    ws_result = await session.execute(
        select(ActiveWorkspace).where(
            ActiveWorkspace.sandbox_id == sandbox_id,
            ActiveWorkspace.active == True,  # noqa: E712
        )
    )
    ws = ws_result.scalar_one_or_none()
    if ws is None or ws.group_id is None:
        return None

    group_result = await session.execute(
        select(PolicyGroup).where(PolicyGroup.id == ws.group_id)
    )
    group = group_result.scalar_one_or_none()
    if group is None:
        return None

    rules = await list_rules(session, group.id, sandbox_id=sandbox_id)
    return {
        "group_id": group.id,
        "group_name": group.name,
        "version": group.version,
        "rules": rules,
    }


# ── Helpers ──────────────────────────────────────────────────────────

async def _resolve_group(
    session: AsyncSession,
    id_or_name: str,
) -> PolicyGroup | None:
    """Find a group by ID or name."""
    result = await session.execute(
        select(PolicyGroup).where(PolicyGroup.id == id_or_name)
    )
    g = result.scalar_one_or_none()
    if g is None:
        result = await session.execute(
            select(PolicyGroup).where(PolicyGroup.name == id_or_name)
        )
        g = result.scalar_one_or_none()
    return g


def _group_to_dict(g: PolicyGroup) -> dict[str, Any]:
    return {
        "id": g.id,
        "name": g.name,
        "description": g.description,
        "version": g.version,
        "enabled": g.enabled,
        "rule_count": len(g.rules) if g.rules else 0,
        "registration_count": len(g.registrations) if g.registrations else 0,
        "created_at": g.created_at,
        "updated_at": g.updated_at,
    }


def _rule_to_dict(r: PolicyRule) -> dict[str, Any]:
    return {
        "id": r.id,
        "group_id": r.group_id,
        "sandbox_id": r.sandbox_id,
        "rule_type": r.rule_type,
        "pattern": r.pattern,
        "effect": r.effect,
        "operations": r.operations,
        "priority": r.priority,
        "description": r.description,
        "is_baseline": r.is_baseline,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
    }


def _get_or_create_poll_event(group_id: str) -> tuple[int, asyncio.Event]:
    if group_id not in _poll_events:
        _poll_events[group_id] = (0, asyncio.Event())
    return _poll_events[group_id]


def _notify_poll(group_id: str) -> None:
    if group_id in _poll_events:
        version, event = _poll_events[group_id]
        new_event = asyncio.Event()
        new_event.set()
        _poll_events[group_id] = (version + 1, new_event)
    else:
        event = asyncio.Event()
        event.set()
        _poll_events[group_id] = (1, event)
