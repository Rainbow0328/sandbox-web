"""Sandbox adapter factory: construct an adapter by provider_type."""

from __future__ import annotations

from typing import Any

from app.adapters.base import SandboxAdapter
from app.adapters.fake import FakeAdapter


def create_adapter(
    *,
    provider_type: str,
    endpoint: str,
    credentials: dict[str, Any],
    provider_name: str,
    provider_key: str,
) -> SandboxAdapter:
    """Build a SandboxAdapter for the given provider type.

    ``fake`` uses an in-memory adapter for development.
    ``opensandbox`` wraps the SDK's OpenSandboxProvider for real sandboxes.
    """
    if provider_type == "fake":
        return FakeAdapter(provider_name=provider_name, provider_key=provider_key)

    if provider_type == "opensandbox":
        from app.adapters.opensandbox import OpenSandboxConsoleAdapter

        return OpenSandboxConsoleAdapter(
            provider_name=provider_name,
            provider_key=provider_key,
            endpoint=endpoint,
            credentials=credentials,
        )

    raise ValueError(f"Unsupported connection type: {provider_type}")
