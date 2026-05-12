"""
tools/payload_gen.py
generate_payload — create test payloads of different types
"""
import os
import random
import string
import struct
from typing import Any


def generate_payload(
    mode: str = "random",
    size_bytes: int = 32,
    structured_type: str | None = None,
    seed: int | None = None,
) -> dict[str, Any]:
    """
    Generate a hex-encoded test payload.

    Modes:
      random      — cryptographically random bytes
      zero        — all zeros
      boundary    — mix of 0x00 and 0xff bytes
      malformed   — invalid UTF-8 / oversized / non-hex chars before encoding
      structured  — ABI-like encoding based on structured_type
      empty       — 0x (empty payload, useful for inspect)
    """
    if seed is not None:
        random.seed(seed)

    if mode == "empty":
        return {"payload": "0x", "mode": mode, "size_bytes": 0}

    if mode == "zero":
        raw = bytes(size_bytes)

    elif mode == "boundary":
        raw = bytes([0x00 if i % 2 == 0 else 0xFF for i in range(size_bytes)])

    elif mode == "malformed":
        # Random bytes that may produce invalid sequences for naive decoders
        raw = bytes([random.randint(0x80, 0xFF) for _ in range(size_bytes)])

    elif mode == "structured":
        raw = _structured_payload(structured_type or "uint256", size_bytes)

    else:  # random (default)
        raw = os.urandom(size_bytes)

    hex_payload = "0x" + raw.hex()
    return {
        "payload": hex_payload,
        "mode": mode,
        "size_bytes": len(raw),
        "hex_length": len(hex_payload),
    }


def _structured_payload(structured_type: str, size_bytes: int) -> bytes:
    """Generate ABI-like structured payloads."""
    if structured_type == "uint256":
        value = random.randint(0, 2**256 - 1)
        return value.to_bytes(32, "big")

    elif structured_type == "address":
        # 12 zero bytes + 20 random address bytes
        addr = os.urandom(20)
        return b"\x00" * 12 + addr

    elif structured_type == "string":
        # ABI-encoded string: offset (32) + length (32) + data (padded to 32)
        text = "".join(random.choices(string.ascii_letters, k=min(size_bytes, 64)))
        encoded = text.encode("utf-8")
        length_word = len(encoded).to_bytes(32, "big")
        padded = encoded + b"\x00" * (32 - len(encoded) % 32 if len(encoded) % 32 else 0)
        offset = (32).to_bytes(32, "big")
        return offset + length_word + padded

    elif structured_type == "bytes32":
        return os.urandom(32)

    else:
        return os.urandom(size_bytes)
