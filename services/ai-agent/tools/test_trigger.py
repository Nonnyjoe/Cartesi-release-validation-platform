"""Trigger a whitelisted test with AI-chosen parameter overrides.

Reads the definition from tests.definitions, requires ai_allowed=true, applies
parameter_overrides by leaf-name to the assertion array, and publishes a tests.commands
message to RabbitMQ. The test-runner consumer recognizes a session_id tag and writes
result_meta.session_id alongside the row.
"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any

import aio_pika
import asyncpg

log = logging.getLogger("ai-agent.test_trigger")


def _normalize_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+asyncpg://", "postgresql://") if dsn else dsn


def _dsn() -> str:
    return _normalize_dsn(os.environ.get("DATABASE_URL", ""))


def _apply_overrides(definition_parsed: dict, overrides: dict) -> dict:
    """Merge parameter_overrides into the assertion array.

    Two forms (review §3.4 — the old bare-key form rewrote the key in EVERY
    assertion, silently changing a shared `expect_count` or masking a failing
    assertion):
      - Path-scoped `assertions.<N>.<key>`  → rewrites exactly that assertion's leaf.
      - Bare `<key>`                         → rewrites the FIRST assertion that has
                                               that key; if >1 assertion has it the
                                               override is AMBIGUOUS and rejected
                                               (caller surfaces the error).
    Returns the merged dict; raises ValueError on an ambiguous/unknown override.
    """
    if not overrides:
        return definition_parsed
    out = copy.deepcopy(definition_parsed)
    assertions = out.get("assertions") or []

    for key, value in overrides.items():
        # ── Path-scoped: assertions.<N>.<leaf> ──────────────────────────────
        if key.startswith("assertions.") and key.count(".") >= 2:
            _, idx_s, leaf = key.split(".", 2)
            try:
                idx = int(idx_s)
            except ValueError:
                raise ValueError(f"override path {key!r}: index must be an integer")
            if not (0 <= idx < len(assertions)) or not isinstance(assertions[idx], dict):
                raise ValueError(f"override path {key!r}: no assertion at index {idx}")
            assertions[idx][leaf] = value
            continue

        # ── Bare leaf: must be unambiguous (exactly one owning assertion) ───
        owners = [a for a in assertions
                  if isinstance(a, dict) and key in a and key != "type"]
        if len(owners) == 0:
            raise ValueError(
                f"override {key!r} matches no assertion leaf; use a path form "
                f"'assertions.<N>.{key}' or check the key name")
        if len(owners) > 1:
            raise ValueError(
                f"override {key!r} is ambiguous: {len(owners)} assertions have it. "
                f"Use a path form 'assertions.<N>.{key}' to target one.")
        owners[0][key] = value
    return out


async def read_test_definition(slug: str) -> dict:
    """Fetch a whitelisted test definition by slug. Returns the parsed YAML and metadata."""
    conn = await asyncpg.connect(_dsn(), timeout=5.0)
    try:
        row = await conn.fetchrow(
            """
            SELECT id, slug, name, version, tags, component, priority, timeout_seconds,
                   ai_allowed, is_active, definition_parsed
            FROM tests.definitions
            WHERE slug = $1
            """,
            slug,
        )
    finally:
        await conn.close()

    if row is None:
        return {"success": False, "error": f"Definition {slug!r} not found"}
    if not row["ai_allowed"]:
        return {
            "success": False,
            "error": f"Definition {slug!r} is not ai_allowed (whitelist)",
            "ai_allowed": False,
        }
    parsed = row["definition_parsed"]
    if isinstance(parsed, str):
        parsed = json.loads(parsed)
    return {
        "success": True,
        "id": str(row["id"]),
        "slug": row["slug"],
        "name": row["name"],
        "version": row["version"],
        "tags": list(row["tags"] or []),
        "component": row["component"],
        "priority": row["priority"],
        "timeout_seconds": row["timeout_seconds"],
        "is_active": row["is_active"],
        "definition_parsed": parsed,
    }


async def _load_sandbox(conn: asyncpg.Connection, sandbox_id: str) -> dict | None:
    row = await conn.fetchrow(
        """
        SELECT id, run_id, docker_network, anvil_port, node_port, graphql_port,
               metadata
        FROM sandbox.sandboxes
        WHERE id = $1
        """,
        sandbox_id,
    )
    if row is None:
        return None
    meta = row["metadata"] or {}
    if isinstance(meta, str):
        meta = json.loads(meta)
    return {
        "id": str(row["id"]),
        "run_id": str(row["run_id"]) if row["run_id"] else None,
        "docker_network": row["docker_network"],
        "anvil_port": row["anvil_port"],
        "node_port": row["node_port"],
        "graphql_port": row["graphql_port"],
        "metadata": meta,
    }


async def trigger_test(
    session_id: str,
    sandbox_id: str,
    definition_slug: str,
    parameter_overrides: dict | None = None,
    wait_seconds: int = 60,
) -> dict[str, Any]:
    """Publish a tests.commands message for one test and (optionally) wait for the result.

    Returns:
        {
          success: bool,
          result_id: str,                # tests.results.id
          definition_id: str,
          status: 'passed' | 'failed' | 'error' | 'running' | 'queued',
          assertion_results: [...],
          error_message: str | None,
        }
    """
    overrides = parameter_overrides or {}

    # 1) Fetch definition
    info = await read_test_definition(definition_slug)
    if not info.get("success"):
        return info  # propagates error / ai_allowed=false

    # 2) Look up sandbox runtime details
    conn = await asyncpg.connect(_dsn(), timeout=5.0)
    try:
        sandbox = await _load_sandbox(conn, sandbox_id)
    finally:
        await conn.close()
    if sandbox is None:
        return {"success": False, "error": f"Sandbox {sandbox_id!r} not found"}

    # 3) Apply overrides (path-scoped or unambiguous bare leaves only)
    try:
        parsed = _apply_overrides(info["definition_parsed"], overrides)
    except ValueError as exc:
        return {"success": False, "error": f"invalid parameter_overrides: {exc}"}

    # 4) Build the tests.commands message — mirror what sandbox_events consumer publishes.
    result_id = str(uuid.uuid4())
    run_id    = sandbox["run_id"] or session_id  # fall back to session_id for ad-hoc runs
    meta = sandbox.get("metadata") or {}
    cmd = {
        "run_id":               run_id,
        "sandbox_id":           sandbox_id,
        "definition_id":        info["id"],
        "definition_version":   info["version"],
        "definition_slug":      info["slug"],
        "anvil_port":           sandbox["anvil_port"] or 8545,
        "node_port":            sandbox["node_port"] or 5004,
        "graphql_port":         sandbox["graphql_port"] or 4000,
        "docker_network":       sandbox["docker_network"] or "bridge",
        "node_major_version":   int(meta.get("node_major_version", 2)),
        "cli_container_name":   meta.get("cli_container_name"),
        "app_address":          meta.get("app_address"),
        "inputbox_address":     meta.get("inputbox_address"),
        "ether_portal_address": meta.get("ether_portal_address"),
        "erc20_portal_address": meta.get("erc20_portal_address"),
        "erc721_portal_address": meta.get("erc721_portal_address"),
        "erc1155_portal_address": meta.get("erc1155_portal_address"),
        "erc20_token_address":   meta.get("erc20_token_address"),
        "erc721_token_address":  meta.get("erc721_token_address"),
        "erc1155_token_address": meta.get("erc1155_token_address"),
        # AI-specific fields the consumer will pick up:
        "session_id":          session_id,
        "result_id":           result_id,
        "parameter_overrides": overrides,
        "definition_parsed_override": parsed,
    }

    # 5) Publish to RabbitMQ — on the AI priority lane, NOT the bulk queue.
    #    A post-provision full-suite sweep can back tests.commands up by ~80 min;
    #    the test-runner consumes tests.commands.ai on a dedicated channel so
    #    AI-triggered tests run promptly (see test-runner consumer + report F-1).
    rabbit_url = os.environ.get("RABBITMQ_URL", "amqp://rvp:changeme@rabbitmq:5672/")
    try:
        conn_r = await aio_pika.connect_robust(rabbit_url)
        async with conn_r:
            ch = await conn_r.channel()
            # Idempotent declare so publishing works even before the test-runner
            # has booted once (default exchange routes by queue name).
            await ch.declare_queue("tests.commands.ai", durable=True)
            await ch.default_exchange.publish(
                aio_pika.Message(body=json.dumps(cmd).encode(), content_type="application/json"),
                routing_key="tests.commands.ai",
            )
    except Exception as exc:
        log.exception("trigger_test publish failed")
        return {"success": False, "error": f"publish failed: {exc}"}

    log.info("trigger_test published: slug=%s result_id=%s session=%s",
             info["slug"], result_id, session_id)

    # 6) Optionally poll for completion
    async def _fetch_result() -> dict | None:
        conn_p = await asyncpg.connect(_dsn(), timeout=5.0)
        try:
            return await conn_p.fetchrow(
                "SELECT status, duration_ms, assertion_results, error_message "
                "FROM tests.results WHERE id = $1",
                result_id,
            )
        finally:
            await conn_p.close()

    def _build_done(row) -> dict:
        ar = row["assertion_results"]
        if isinstance(ar, str):
            ar = json.loads(ar)
        return {
            "success": row["status"] == "passed",
            "result_id": result_id,
            "definition_id": info["id"],
            "definition_slug": info["slug"],
            "status": row["status"],
            "duration_ms": row["duration_ms"],
            "assertion_results": ar,
            "error_message": row["error_message"],
            "overrides_applied": overrides,
        }

    if wait_seconds and wait_seconds > 0:
        deadline = datetime.now(tz=timezone.utc).timestamp() + wait_seconds
        while datetime.now(tz=timezone.utc).timestamp() < deadline:
            await asyncio.sleep(1)
            row = await _fetch_result()
            if row and row["status"] not in (None, "pending", "running"):
                return _build_done(row)
        # One final check after the deadline — catches tests that finished in the last second
        row = await _fetch_result()
        if row and row["status"] not in (None, "pending", "running"):
            return _build_done(row)
        return {
            "success": False,
            "result_id": result_id,
            "definition_id": info["id"],
            "definition_slug": info["slug"],
            "status": "timeout",
            "error_message": (
                f"No result within {wait_seconds}s. The test may still be running — "
                f"query tests.results WHERE id='{result_id}' to check."
            ),
        }

    # Fire-and-forget
    return {
        "success": True,
        "result_id": result_id,
        "definition_id": info["id"],
        "definition_slug": info["slug"],
        "status": "queued",
    }
