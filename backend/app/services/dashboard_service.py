"""Dashboard service: aggregated metrics for the overview page.

Provides a single ``get_overview`` call that returns counts, state
breakdowns, and recent activity across sandboxes, connections, agents,
and operations.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import Connection
from app.models.history_projection import HistoryProjection
from app.models.policy import (
    ActiveWorkspace,
    PolicyGroup,
    PolicyRule,
    SdkRegistration,
)
from app.services import connection_service


async def get_overview(session: AsyncSession) -> dict[str, Any]:
    """Return a single aggregated dashboard payload."""
    # --- Connections ---
    conn_result = await session.execute(
        select(
            func.count(Connection.id),
            func.count(Connection.id).filter(Connection.enabled == True),  # noqa: E712
        )
    )
    conn_row = conn_result.one()
    total_connections = conn_row[0] or 0
    enabled_connections = conn_row[1] or 0

    # --- Sandboxes (across all enabled connections) ---
    try:
        all_sandboxes = await connection_service.list_all_sandboxes(session)
    except Exception:
        all_sandboxes = []

    total_sandboxes = len(all_sandboxes)
    state_counts: dict[str, int] = {}
    for sb in all_sandboxes:
        state = sb.get("state", "unknown")
        state_counts[state] = state_counts.get(state, 0) + 1

    # --- Active workspaces (reuse registry) ---
    ws_result = await session.execute(
        select(
            func.count(ActiveWorkspace.id),
            func.count(ActiveWorkspace.id).filter(ActiveWorkspace.active == True),  # noqa: E712
        )
    )
    ws_row = ws_result.one()
    total_workspaces = ws_row[0] or 0
    active_workspaces = ws_row[1] or 0

    # --- Policy groups ---
    group_result = await session.execute(
        select(
            func.count(PolicyGroup.id),
            func.count(PolicyGroup.id).filter(PolicyGroup.enabled == True),  # noqa: E712
        )
    )
    group_row = group_result.one()
    total_groups = group_row[0] or 0
    enabled_groups = group_row[1] or 0

    # --- Policy rules ---
    rule_result = await session.execute(
        select(
            func.count(PolicyRule.id),
            func.count(PolicyRule.id).filter(PolicyRule.effect == "allow"),
            func.count(PolicyRule.id).filter(PolicyRule.effect == "deny"),
        )
    )
    rule_row = rule_result.one()
    total_rules = rule_row[0] or 0
    allow_rules = rule_row[1] or 0
    deny_rules = rule_row[2] or 0

    # --- SDK registrations (agents) ---
    sdk_result = await session.execute(
        select(
            func.count(SdkRegistration.id),
            func.count(SdkRegistration.id).filter(SdkRegistration.online == True),  # noqa: E712
        )
    )
    sdk_row = sdk_result.one()
    total_agents = sdk_row[0] or 0
    online_agents = sdk_row[1] or 0

    # --- Operation stats from HistoryProjection ---
    op_total_result = await session.execute(
        select(func.count(HistoryProjection.id))
    )
    total_operations = op_total_result.scalar() or 0

    # Operations by type
    op_type_result = await session.execute(
        select(
            HistoryProjection.operation_type,
            func.count(HistoryProjection.id),
        ).group_by(HistoryProjection.operation_type)
    )
    operations_by_type: dict[str, int] = {}
    for row in op_type_result:
        operations_by_type[row[0]] = row[1]

    # Operations by status
    op_status_result = await session.execute(
        select(
            HistoryProjection.status,
            func.count(HistoryProjection.id),
        ).group_by(HistoryProjection.status)
    )
    operations_by_status: dict[str, int] = {}
    for row in op_status_result:
        operations_by_status[row[0]] = row[1]

    # Operations by source
    op_source_result = await session.execute(
        select(
            HistoryProjection.source,
            func.count(HistoryProjection.id),
        ).group_by(HistoryProjection.source)
    )
    operations_by_source: dict[str, int] = {}
    for row in op_source_result:
        operations_by_source[row[0]] = row[1]

    # Operations by actor (top 10)
    op_actor_result = await session.execute(
        select(
            HistoryProjection.actor_id,
            func.count(HistoryProjection.id),
        )
        .where(HistoryProjection.actor_id.isnot(None))
        .group_by(HistoryProjection.actor_id)
        .order_by(func.count(HistoryProjection.id).desc())
        .limit(10)
    )
    operations_by_actor: list[dict[str, Any]] = []
    for row in op_actor_result:
        operations_by_actor.append({"actor_id": row[0], "count": row[1]})

    # --- Recent operations (latest 20) ---
    recent_result = await session.execute(
        select(
            HistoryProjection.event_id,
            HistoryProjection.connection_id,
            HistoryProjection.sandbox_id,
            HistoryProjection.source,
            HistoryProjection.actor_type,
            HistoryProjection.actor_id,
            HistoryProjection.operation_type,
            HistoryProjection.status,
            HistoryProjection.occurred_at,
            HistoryProjection.duration_ms,
            HistoryProjection.command,
            HistoryProjection.file_path,
        )
        .order_by(HistoryProjection.occurred_at.desc())
        .limit(20)
    )
    recent_operations: list[dict[str, Any]] = []
    for row in recent_result:
        recent_operations.append(
            {
                "event_id": row.event_id,
                "connection_id": row.connection_id,
                "sandbox_id": row.sandbox_id,
                "source": row.source,
                "actor_type": row.actor_type,
                "actor_id": row.actor_id,
                "operation_type": row.operation_type,
                "status": row.status,
                "occurred_at": row.occurred_at,
                "duration_ms": row.duration_ms,
                "command": row.command,
                "file_path": row.file_path,
            }
        )

    # --- Sandbox list with state for the card ---
    sandbox_summaries: list[dict[str, Any]] = []
    for sb in all_sandboxes:
        sandbox_summaries.append(
            {
                "sandbox_id": sb.get("sandbox_id"),
                "connection_id": sb.get("connection_id"),
                "name": sb.get("name"),
                "state": sb.get("state"),
                "image": sb.get("image"),
                "created_at": sb.get("created_at"),
                "last_activity_at": sb.get("last_activity_at"),
            }
        )

    return {
        "connections": {
            "total": total_connections,
            "enabled": enabled_connections,
        },
        "sandboxes": {
            "total": total_sandboxes,
            "by_state": state_counts,
        },
        "workspaces": {
            "total": total_workspaces,
            "active": active_workspaces,
        },
        "policy_groups": {
            "total": total_groups,
            "enabled": enabled_groups,
        },
        "policy_rules": {
            "total": total_rules,
            "allow": allow_rules,
            "deny": deny_rules,
        },
        "agents": {
            "total": total_agents,
            "online": online_agents,
        },
        "operations": {
            "total": total_operations,
            "by_type": operations_by_type,
            "by_status": operations_by_status,
            "by_source": operations_by_source,
            "by_actor": operations_by_actor,
            "recent": recent_operations,
        },
        "sandbox_summaries": sandbox_summaries,
    }
