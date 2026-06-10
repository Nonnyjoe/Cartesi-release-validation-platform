"""Audit recorder for tool invocations.

Writes one row to ai.tool_invocations per tool call. Best-effort: if the DB is unreachable,
we log and continue — the tool itself runs regardless.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

import asyncpg

log = logging.getLogger("ai-agent.audit")


def _dsn() -> str:
    return os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")


async def record_invocation(
    session_id: str | None,
    tool_name: str,
    tool_input: dict,
    output: Any,
    status: str,
    duration_ms: int,
) -> None:
    if not session_id:
        return
    dsn = _dsn()
    if not dsn:
        return
    try:
        conn = await asyncpg.connect(dsn, timeout=5.0)
    except Exception as exc:
        log.warning("audit: connect failed: %s", exc)
        return
    try:
        await conn.execute(
            """
            INSERT INTO ai.tool_invocations
              (session_id, tool_name, input, output, status, duration_ms)
            VALUES ($1::uuid, $2, $3::jsonb, $4::jsonb, $5, $6)
            """,
            session_id,
            tool_name,
            json.dumps(tool_input)[:50_000],
            json.dumps(output, default=str)[:200_000] if output is not None else None,
            status,
            duration_ms,
        )
        # Keep the live tool count on the session row in sync so the Sessions
        # list shows real-time counts (previously only flushed at close).
        await conn.execute(
            """
            UPDATE ai.sessions
            SET tool_call_count = COALESCE(tool_call_count, 0) + 1
            WHERE id = $1::uuid
            """,
            session_id,
        )
    except Exception as exc:
        log.warning("audit: insert failed: %s", exc)
    finally:
        await conn.close()


class AuditedCall:
    """Context manager that records timing + outcome."""

    def __init__(self, session_id: str | None, tool_name: str, tool_input: dict):
        self.session_id = session_id
        self.tool_name = tool_name
        self.tool_input = tool_input
        self.status: str = "ok"
        self.output: Any = None
        self._t0: float = 0.0

    def __enter__(self):
        self._t0 = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb):
        return False  # don't swallow

    def mark_denied(self, output: Any):
        self.status = "denied"
        self.output = output

    def mark_error(self, output: Any):
        self.status = "error"
        self.output = output

    def mark_ok(self, output: Any):
        self.status = "ok"
        self.output = output

    @property
    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self._t0) * 1000)
