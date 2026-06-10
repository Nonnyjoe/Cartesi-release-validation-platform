"""AES-GCM helper for per-session Anthropic key encryption.

Used by the orchestrator API to encrypt user-provided API keys before storing them in
ai.sessions. The ai-agent service has the matching decrypt helper.

Falls back to base64-only "encoding" (NOT encryption) when the `cryptography` package
isn't available. A warning is logged on fallback so operators know to install it.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Optional

log = logging.getLogger("orchestrator.crypto")

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM  # type: ignore
    _HAS_CRYPTO = True
except ImportError:
    AESGCM = None  # type: ignore
    _HAS_CRYPTO = False
    log.warning("cryptography package not installed; AI session keys stored base64 only (INSECURE)")


# Preflight: fail loudly at import time, not on the first encrypt of a user's key.
if not os.environ.get("AI_SESSION_KEY"):
    log.error(
        "AI_SESSION_KEY is not set or empty — POST /sessions with an API key WILL 500. "
        "Set it in the root .env (base64 of 32 random bytes; see .env.example)."
    )


def _key() -> bytes:
    raw = os.environ.get("AI_SESSION_KEY")
    if not raw:
        raise RuntimeError(
            "AI_SESSION_KEY env var is not set or empty "
            "(must be in root .env — compose interpolates it into this container)"
        )
    return base64.b64decode(raw)


def encrypt_key(plaintext: str) -> tuple[bytes, bytes]:
    """Encrypt the plaintext API key. Returns (ciphertext, nonce)."""
    nonce = os.urandom(12)
    if not _HAS_CRYPTO:
        return base64.b64encode(plaintext.encode("utf-8")), nonce
    aes = AESGCM(_key())
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), None)
    return ct, nonce


def decrypt_key(ciphertext: Optional[bytes], nonce: Optional[bytes]) -> Optional[str]:
    if ciphertext is None or nonce is None:
        return None
    if not _HAS_CRYPTO:
        return base64.b64decode(bytes(ciphertext)).decode("utf-8")
    aes = AESGCM(_key())
    pt = aes.decrypt(bytes(nonce), bytes(ciphertext), None)
    return pt.decode("utf-8")
