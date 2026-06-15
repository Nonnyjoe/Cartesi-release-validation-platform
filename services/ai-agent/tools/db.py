"""Shared asyncpg connection pool for the ai-agent tools.

The trustworthiness review flagged "one asyncpg.connect() per tool call and per
verdict" as a scaling risk. This module provides a single lazily-created pool
reused across audit writes, verdict recording, plan recording, and read tools —
one TCP/auth handshake amortised over the whole process instead of per call.
"""
from __future__ import annotations

import asyncio
import logging
import os

import asyncpg

log = logging.getLogger("ai-agent.db")

_pool: asyncpg.Pool | None = None
_lock = asyncio.Lock()


def _dsn() -> str:
    dsn = os.environ.get("DATABASE_URL", "")
    return dsn.replace("postgresql+asyncpg://", "postgresql://") if dsn else dsn


async def get_pool() -> asyncpg.Pool | None:
    """Return the process-wide pool, creating it on first use. None if no DSN."""
    global _pool
    if _pool is not None:
        return _pool
    dsn = _dsn()
    if not dsn:
        return None
    async with _lock:
        if _pool is None:
            try:
                _pool = await asyncpg.create_pool(
                    dsn,
                    min_size=1,
                    max_size=int(os.environ.get("AI_DB_POOL_MAX", "8")),
                    timeout=5.0,
                    command_timeout=15.0,
                )
                log.info("ai-agent DB pool created (max=%s)", _pool.get_max_size())
            except Exception as exc:
                log.warning("DB pool creation failed: %s", exc)
                return None
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        try:
            await _pool.close()
        finally:
            _pool = None
