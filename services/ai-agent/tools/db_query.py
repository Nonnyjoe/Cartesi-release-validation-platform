"""Read-only DB query tool.

Uses the `ai_reader` Postgres role created in migration 0012, which has SELECT on:
- tests.definitions
- tests.results
- orchestrator.runs
- ai.sessions
- ai.tool_invocations
- ai.suggested_test_actions

Any INSERT/UPDATE/DELETE/DDL will fail with a permission error from Postgres.
A 5-second statement timeout is enforced.
"""
from __future__ import annotations

import logging
import os
import re

import asyncpg

log = logging.getLogger("ai-agent.db_query")

DEFAULT_LIMIT = 200
TIMEOUT_MS = 5000

_FORBIDDEN_PATTERNS = [
    re.compile(r"\b(insert|update|delete|drop|alter|truncate|grant|revoke|create|copy)\b", re.I),
]


async def query_db(sql: str) -> dict:
    if not sql or not sql.strip():
        return {"success": False, "error": "empty query"}

    stripped = sql.strip().rstrip(";")
    # Quick syntactic guard before sending to the server.
    for pat in _FORBIDDEN_PATTERNS:
        if pat.search(stripped):
            return {
                "success": False,
                "error": "Only SELECT statements are allowed.",
            }
    if not re.match(r"^\s*(select|with)\b", stripped, re.I):
        return {"success": False, "error": "Only SELECT or WITH ... SELECT queries allowed."}

    dsn = os.environ.get("AI_READER_DATABASE_URL")
    if not dsn:
        dsn = os.environ.get("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    if not dsn:
        return {"success": False, "error": "No DB connection configured"}

    # Convert SQLAlchemy DSN form if needed.
    if dsn.startswith("postgresql+asyncpg://"):
        dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")

    conn = None
    try:
        conn = await asyncpg.connect(dsn, timeout=5.0)
        await conn.execute(f"SET statement_timeout = {TIMEOUT_MS}")
        rows = await conn.fetch(stripped)
    except asyncpg.exceptions.InsufficientPrivilegeError as exc:
        return {"success": False, "error": f"permission denied: {exc}"}
    except Exception as exc:
        log.exception("query_db error")
        return {"success": False, "error": str(exc)}
    finally:
        if conn is not None:
            await conn.close()

    if len(rows) > DEFAULT_LIMIT:
        rows = rows[:DEFAULT_LIMIT]
        truncated = True
    else:
        truncated = False

    return {
        "success": True,
        "row_count": len(rows),
        "truncated": truncated,
        "rows": [dict(r) for r in rows],
    }
