"""Command policy engine — uses DB-backed policy groups for rule matching.

Policy evaluation dimensions:
- command (regex match)
- cwd / path (glob match)
- actor
- operation_type

When a policy group is configured, rules are loaded from the DB
and evaluated in priority order.  When no group is configured,
default allow is returned.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from typing import Any, Literal


@dataclass
class PolicyDecision:
    """Result of a policy evaluation."""

    result: Literal["allow", "deny", "approval_required"]
    reason: str = ""
    rule_id: str | None = None


def evaluate_command_policy(
    command: str,
    cwd: str | None = None,
    actor_id: str = "admin",
    operation_type: str = "command.start",
    rules: list[dict[str, Any]] | None = None,
) -> PolicyDecision:
    """Evaluate whether a command is allowed.

    If *rules* is provided, match against them in priority order.
    Otherwise, default allow.
    """
    if rules:
        for rule in rules:
            if rule.get("rule_type") != "command":
                continue
            pattern = rule.get("pattern", "")
            try:
                if re.search(pattern, command) is not None:
                    return PolicyDecision(
                        result=rule.get("effect", "allow"),
                        reason=rule.get("description", f"Rule: {pattern}"),
                        rule_id=rule.get("id"),
                    )
            except re.error:
                continue
    return PolicyDecision(
        result="allow",
        reason="default allow",
        rule_id="default",
    )


def evaluate_file_policy(
    path: str,
    operation: str,
    actor_id: str = "admin",
    rules: list[dict[str, Any]] | None = None,
) -> PolicyDecision:
    """Evaluate whether a file operation is allowed."""
    if rules:
        op = operation.rsplit(".", 1)[-1] if "." in operation else operation
        # Map delete→write, list→read for rule matching (same as SDK)
        if op == "delete":
            op = "write"
        elif op == "list":
            op = "read"
        for rule in rules:
            if rule.get("rule_type") != "workspace":
                continue
            operations = rule.get("operations", "read,write,execute")
            if op and op not in [o.strip() for o in operations.split(",")]:
                continue
            pattern = rule.get("pattern", "")
            if fnmatch.fnmatch(path, pattern):
                return PolicyDecision(
                    result=rule.get("effect", "allow"),
                    reason=rule.get("description", f"Rule: {pattern}"),
                    rule_id=rule.get("id"),
                )
    return PolicyDecision(
        result="allow",
        reason="default allow",
        rule_id="default",
    )
