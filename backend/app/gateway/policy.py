"""Command policy engine — v0.1 default allow, v0.3 will add full rule matching.

(对齐 §9.3、§15.4)

Policy evaluation dimensions:
- command (exact match or regex)
- cwd
- path (for file operations)
- actor
- operation_type

v0.1 behavior: all commands are allowed by default. The interface is provided
so that v0.3 can wire in a full rule engine without changing call sites.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass
class PolicyDecision:
    """Result of a policy evaluation."""

    result: Literal["allow", "deny", "approval_required"]
    reason: str = ""
    rule_id: str | None = None


# v0.1: Optional denylist of dangerous commands (empty by default).
# In v0.3, this will be loaded from a policy database.
_DENYLIST: set[str] = set()

# Commands that require approval (v0.3 feature).
_APPROVAL_REQUIRED: set[str] = set()


def evaluate_command_policy(
    command: str,
    cwd: str | None = None,
    actor_id: str = "admin",
    operation_type: str = "command.start",
) -> PolicyDecision:
    """Evaluate whether a command is allowed.

    v0.1: default allow, with an optional static denylist.
    v0.3: will load rules from a policy database and match on
    command/cwd/path/actor/operation_type dimensions.
    """
    # Extract the base command (first token).
    base_cmd = command.strip().split()[0] if command.strip() else ""

    # Check denylist.
    if base_cmd in _DENYLIST:
        return PolicyDecision(
            result="deny",
            reason=f"Command '{base_cmd}' is in the denylist",
            rule_id="denylist",
        )

    # Check approval required.
    if base_cmd in _APPROVAL_REQUIRED:
        return PolicyDecision(
            result="approval_required",
            reason=f"Command '{base_cmd}' requires approval",
            rule_id="approval_required",
        )

    # Default: allow.
    return PolicyDecision(
        result="allow",
        reason="default allow",
        rule_id="default",
    )


def evaluate_file_policy(
    path: str,
    operation: str,
    actor_id: str = "admin",
) -> PolicyDecision:
    """Evaluate whether a file operation is allowed.

    v0.1: all file operations are allowed (path normalization is handled
    separately in file_service.normalize_path).
    """
    return PolicyDecision(
        result="allow",
        reason="default allow",
        rule_id="default",
    )
