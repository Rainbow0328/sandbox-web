"""Security utilities: Fernet encryption for connection credentials and Admin Token auth."""

from __future__ import annotations

import hmac
import secrets
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import get_settings


def _get_fernet() -> Fernet:
    """Build a Fernet instance from the configured master key.

    The master key may be provided as a URL-safe base64 string (Fernet-compatible)
    or as a hex string. If hex, it is converted to a 32-byte URL-safe base64 key.
    """
    key = get_settings().master_key
    # If it looks like hex (64 chars), convert to Fernet-compatible base64.
    try:
        if len(key) == 64:
            import base64

            raw = bytes.fromhex(key)
            fernet_key = base64.urlsafe_b64encode(raw)
            return Fernet(fernet_key)
    except (ValueError, TypeError):
        pass
    # Otherwise assume it's already a Fernet key.
    return Fernet(key.encode() if isinstance(key, str) else key)


def encrypt_credentials(credentials: dict[str, Any]) -> bytes:
    """Encrypt a credentials dict and return the ciphertext bytes."""
    import json

    fernet = _get_fernet()
    plaintext = json.dumps(credentials, separators=(",", ":")).encode("utf-8")
    return fernet.encrypt(plaintext)


def decrypt_credentials(ciphertext: bytes) -> dict[str, Any]:
    """Decrypt ciphertext bytes back to a credentials dict."""
    import json

    fernet = _get_fernet()
    try:
        plaintext = fernet.decrypt(ciphertext)
    except InvalidToken as exc:
        raise ValueError("Failed to decrypt credentials: master key mismatch or data corruption") from exc
    return json.loads(plaintext)


def verify_admin_token(provided: str) -> bool:
    """Constant-time comparison of the provided token against the configured admin token."""
    expected = get_settings().admin_token
    if not expected:
        return False
    return hmac.compare_digest(provided, expected)


def generate_session_token() -> str:
    """Generate a random session token (URL-safe, 32 bytes)."""
    return secrets.token_urlsafe(32)
