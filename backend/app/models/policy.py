"""Policy management ORM models.

Tables:
  - policy_groups:     A named group that maps to a set of rules.
  - policy_rules:      Individual command/workspace rules (allow/deny).
  - sdk_registrations: SDK instances that have registered with Console.
  - active_workspaces: Sandboxes tracked by Console (for reuse lookup).
"""

from __future__ import annotations

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin


class PolicyGroup(Base, TimestampMixin):
    """A named group of permission rules.

    Multiple SDK instances can share the same group.
    """

    __tablename__ = "policy_groups"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    rules: Mapped[list["PolicyRule"]] = relationship(
        "PolicyRule",
        back_populates="group",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    registrations: Mapped[list["SdkRegistration"]] = relationship(
        "SdkRegistration",
        back_populates="group",
        lazy="selectin",
    )


class PolicyRule(Base, TimestampMixin):
    """A single permission rule within a group.

    When ``sandbox_id`` is NULL, the rule applies to all sandboxes in the group.
    When ``sandbox_id`` is set, the rule overrides group-level rules for that
    specific sandbox only (sandbox-level override).
    """

    __tablename__ = "policy_rules"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    group_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("policy_groups.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sandbox_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True,
        doc="When set, this rule only applies to this specific sandbox.
             When NULL, applies to all sandboxes in the group.",
    )
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)  # command | workspace
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    effect: Mapped[str] = mapped_column(String(16), nullable=False)  # allow | deny
    operations: Mapped[str] = mapped_column(
        String(128), nullable=False, default="read,write,execute",
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    is_baseline: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
        doc="True if pushed by SDK as immutable baseline",
    )

    group: Mapped["PolicyGroup"] = relationship(back_populates="rules")


class SdkRegistration(Base, TimestampMixin):
    """An SDK instance that registered with Console.

    Tracks the callback URL (push mode) or long-poll mode,
    the sandbox_id, agent_name, etc.
    """

    __tablename__ = "sdk_registrations"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    group_id: Mapped[str] = mapped_column(
        String(26), ForeignKey("policy_groups.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    sandbox_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    sandbox_name: Mapped[str] = mapped_column(String(255), nullable=True)
    agent_name: Mapped[str] = mapped_column(String(255), nullable=True)
    sdk_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    callback_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    callback_mode: Mapped[str] = mapped_column(
        String(32), nullable=False, default="long_poll",
    )  # push | long_poll
    last_seen: Mapped[str] = mapped_column(
        String(40), nullable=False, default="",
    )
    online: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    group: Mapped["PolicyGroup"] = relationship(back_populates="registrations")


class ActiveWorkspace(Base, TimestampMixin):
    """A sandbox tracked by Console for reuse-by-name lookup.

    When an SDK creates a sandbox with a name, it's recorded here.
    When another SDK requests reuse_by_name, we look it up here first.
    """

    __tablename__ = "active_workspaces"

    id: Mapped[str] = mapped_column(String(26), primary_key=True)
    sandbox_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    sandbox_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    sandbox_instance_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    provider_name: Mapped[str] = mapped_column(String(64), nullable=False, default="opensandbox")
    provider_key: Mapped[str] = mapped_column(String(64), nullable=False, default="opensandbox-default")
    agent_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    group_id: Mapped[str | None] = mapped_column(
        String(26), ForeignKey("policy_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
