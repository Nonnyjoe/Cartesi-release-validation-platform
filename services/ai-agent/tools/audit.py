"""Audit recorder for tool invocations.

Writes one row to ai.tool_invocations per tool call. Best-effort: if the DB is unreachable,
we log and continue — the tool itself runs regardless.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from tools.db import get_pool

log = logging.getLogger("ai-agent.audit")


async def record_invocation(
    session_id: str | None,
    tool_name: str,
    tool_input: dict,
    output: Any,
    status: str,
    duration_ms: int,
    definition_slug: str | None = None,
) -> None:
    if not session_id:
        return
    pool = await get_pool()
    if pool is None:
        return
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ai.tool_invocations
                  (session_id, tool_name, input, output, status, duration_ms, definition_slug)
                VALUES ($1::uuid, $2, $3::jsonb, $4::jsonb, $5, $6, $7)
                """,
                session_id,
                tool_name,
                json.dumps(tool_input)[:50_000],
                json.dumps(output, default=str)[:200_000] if output is not None else None,
                status,
                duration_ms,
                definition_slug,
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
