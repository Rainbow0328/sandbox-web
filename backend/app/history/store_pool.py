"""History store pool: caches SandboxHistoryStore instances per sandbox.

The SDK's ``SandboxHistoryStore.initialize()`` uploads a helper .pyz file
to the sandbox and installs it — a heavy operation involving multiple HTTP
round-trips (upload, install command, init, health check, cleanup).

Without caching, every Console operation (file write, command execute, etc.)
and every history sync creates a **new** store and re-installs the helper,
causing a storm of HTTP requests to the sandbox.

This module provides a process-level cache that keeps one initialized
``SandboxHistoryStore`` per ``(connection_id, sandbox_id)`` pair.  The store
is reused for both writes (``write_operation_to_sandbox_history``) and
reads (``sync_history``), eliminating redundant helper installations.

To avoid excessive health-check HTTP requests, the store is only
re-verified if it hasn't been used in the last ``HEALTH_CHECK_TTL`` seconds.
"""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

# Process-level cache: "connection_id:sandbox_id" -> (store, last_verified_ts)
_store_cache: dict[str, tuple[Any, float]] = {}

# Skip health check if store was verified within this many seconds.
_HEALTH_CHECK_TTL = 120.0


def _cache_key(connection_id: str, sandbox_id: str) -> str:
    return f"{connection_id}:{sandbox_id}"


async def get_history_store(
    adapter: Any,
    ref: Any,
    connection_id: str,
    sandbox_id: str,
) -> Any | None:
    """Get or create a cached SandboxHistoryStore.

    Returns an initialized store, or ``None`` if creation fails.
    The store is cached per (connection_id, sandbox_id) and reused
    across calls.

    To avoid excessive HTTP requests, the store's health is only checked
    if it hasn't been verified in the last ``HEALTH_CHECK_TTL`` seconds.
    """
    key = _cache_key(connection_id, sandbox_id)

    # Check cache first.
    cached = _store_cache.get(key)
    if cached is not None:
        store, last_verified = cached
        now = time.monotonic()
        # Skip health check if recently verified.
        if now - last_verified < _HEALTH_CHECK_TTL:
            return store
        # Verify store is still healthy.
        try:
            await store.health()
            _store_cache[key] = (store, now)
            return store
        except Exception:
            # Store is stale/unhealthy — remove and recreate.
            logger.info("History store for %s is unhealthy, recreating", key)
            try:
                await store.close()
            except Exception:
                pass
            _store_cache.pop(key, None)

    # Create a new store.
    try:
        from agent_sandbox_backends.history.config import (
            HistoryConfig,
            HistoryConsistency,
            HistoryMode,
        )
        from agent_sandbox_backends.history.provider_transport import (
            ProviderHistoryHelperTransport,
        )
        from agent_sandbox_backends.history.sandbox import SandboxHistoryStore
        from agent_sandbox_backends.version import SDK_VERSION

        sdk_provider = adapter.sdk_provider
        sdk_ref = adapter.to_sdk_ref(ref)
        transport = ProviderHistoryHelperTransport(sdk_provider, sdk_ref)
        store = SandboxHistoryStore(
            transport,
            sdk_version=SDK_VERSION,
            config=HistoryConfig(
                mode=HistoryMode.SANDBOX,
                consistency=HistoryConsistency.BEST_EFFORT,
            ),
        )
        await store.initialize()
        _store_cache[key] = (store, time.monotonic())
        logger.info("History store created and cached for %s", key)
        return store
    except Exception as exc:
        logger.warning("Failed to create history store for %s: %s", key, exc)
        return None


async def close_history_store(connection_id: str, sandbox_id: str) -> None:
    """Close and remove a cached history store (e.g., when sandbox is deleted)."""
    key = _cache_key(connection_id, sandbox_id)
    cached = _store_cache.pop(key, None)
    if cached is not None:
        store, _ = cached
        try:
            await store.close()
        except Exception:
            pass


async def close_all_stores() -> None:
    """Close all cached history stores (e.g., on shutdown)."""
    for key, (store, _) in list(_store_cache.items()):
        try:
            await store.close()
        except Exception:
            pass
    _store_cache.clear()
