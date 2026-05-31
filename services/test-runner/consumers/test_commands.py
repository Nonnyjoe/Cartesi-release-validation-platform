"""
services/test-runner/consumers/test_commands.py
Consumes tests.commands queue.
For each command: checks for cancellation, runs the test, writes result to DB,
publishes to tests.results, and emits a log_batch event with executor diagnostics.
"""
import asyncio
import json
import logging
import os
import traceback
import uuid
from datetime import datetime, timezone

import aio_pika
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from executor import run_test
from executors.base import SandboxContext
from loader import DefinitionLoader

log = logging.getLogger("test-runner.consumer")

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://rvp:changeme@localhost:5672/")
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace(
    "postgresql://", "postgresql+asyncpg://"
)

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def _is_run_cancelled(run_id: str) -> bool:
    """Return True if the run is marked cancelled in orchestrator.runs."""
    try:
        async with SessionLocal() as db:
            row = await db.execute(
                text("SELECT status FROM orchestrator.runs WHERE id = :id"),
                {"id": run_id},
            )
            r = row.fetchone()
            return r is not None and r.status == "cancelled"
    except Exception as exc:
        log.warning("Could not check cancellation for run %s: %s", run_id, exc)
        return False


class TestCommandConsumer:
    def __init__(self, loader: DefinitionLoader):
        self._loader = loader
        self._connection = None
        self._channel = None

    async def start_consuming(self):
        self._connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=5)

        queue = await self._channel.get_queue("tests.commands")
        log.info("Test Runner consuming tests.commands...")
        async with queue.iterator() as q:
            async for message in q:
                async with message.process():
                    try:
                        await self._handle(json.loads(message.body))
                    except Exception as exc:
                        log.exception("Error handling test command: %s", exc)

    async def _handle(self, msg: dict):
        run_id             = msg["run_id"]
        sandbox_id         = msg["sandbox_id"]
        app_address        = msg.get("app_address")
        definition_id      = msg["definition_id"]
        definition_version = msg["definition_version"]
        definition_slug    = msg["definition_slug"]
        anvil_port          = msg["anvil_port"]
        node_port           = msg["node_port"]
        graphql_port        = msg["graphql_port"]
        docker_network      = msg["docker_network"]
        node_major_version  = int(msg.get("node_major_version", 1))
        cli_container_name  = msg.get("cli_container_name")
        inputbox_address    = msg.get("inputbox_address")
        erc20_token_address  = msg.get("erc20_token_address")
        erc721_token_address = msg.get("erc721_token_address")
        erc1155_token_address = msg.get("erc1155_token_address")

        log.info("Test command received: %s (run=%s)", definition_slug, run_id)

        # ── Cancellation check before executing ───────────────────────────────
        if await _is_run_cancelled(run_id):
            log.info("Run %s is cancelled — skipping test %s (emitting skipped)",
                     run_id, definition_slug)
            result_id = str(uuid.uuid4())
            now = datetime.now(tz=timezone.utc)
            async with SessionLocal() as db:
                await db.execute(
                    text("""
                        INSERT INTO tests.results
                          (id, run_id, sandbox_id, definition_id, definition_version,
                           status, started_at, completed_at)
                        VALUES (:id, :run_id, :sandbox_id, :def_id, :def_ver,
                                'skipped', :ts, :ts)
                    """),
                    {"id": result_id, "run_id": run_id, "sandbox_id": sandbox_id,
                     "def_id": definition_id, "def_ver": definition_version, "ts": now},
                )
                await db.commit()
            await self._publish_result(msg, {
                "status": "skipped",
                "duration_ms": 0,
                "assertion_results": [],
                "error_message": "Run cancelled",
            }, result_id, now, now)
            return

        # Fetch definition from hot-reload cache
        definition = await self._loader.get(definition_id)
        if not definition:
            log.warning("Definition %s not found in cache — skipping", definition_id)
            return

        ctx = SandboxContext(
            sandbox_id=sandbox_id,
            run_id=run_id,
            anvil_port=anvil_port,
            node_port=node_port,
            graphql_port=graphql_port,
            docker_network=docker_network,
            node_major_version=node_major_version,
            cli_container_name=cli_container_name,
            app_address=app_address,
            inputbox_address=inputbox_address,
            ether_portal_address=msg.get("ether_portal_address"),
            erc20_portal_address=msg.get("erc20_portal_address"),
            erc721_portal_address=msg.get("erc721_portal_address"),
            erc1155_portal_address=msg.get("erc1155_portal_address"),
            erc20_token_address=erc20_token_address,
            erc721_token_address=erc721_token_address,
            erc1155_token_address=erc1155_token_address,
        )

        # Insert a running result row
        result_id  = str(uuid.uuid4())
        started_at = datetime.now(tz=timezone.utc)
        async with SessionLocal() as db:
            await db.execute(
                text("""
                    INSERT INTO tests.results
                      (id, run_id, sandbox_id, definition_id, definition_version,
                       status, started_at)
                    VALUES (:id, :run_id, :sandbox_id, :def_id, :def_ver, 'running', :ts)
                """),
                {"id": result_id, "run_id": run_id, "sandbox_id": sandbox_id,
                 "def_id": definition_id, "def_ver": definition_version, "ts": started_at},
            )
            await db.commit()

        # Run the test — capture any diagnostic log lines alongside the outcome
        test_log_lines: list[dict] = []
        error_tb: str | None = None

        # Header line so logs tab shows a clear boundary per test
        test_log_lines.append({
            "source":  f"test:{definition_id[:8]}",
            "level":   "info",
            "message": f"[{definition_slug}] Starting test (run={run_id[:8]}, sandbox={sandbox_id[:8]})",
            "ts":      started_at.isoformat(),
        })

        try:
            outcome = await run_test(definition, ctx)
        except Exception as exc:
            # Unhandled executor exception — build a synthetic outcome and capture
            # the full traceback so it's visible in the logs tab.
            error_tb = traceback.format_exc()
            completed_at = datetime.now(tz=timezone.utc)
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)
            outcome = {
                "status":            "error",
                "duration_ms":       duration_ms,
                "assertion_results": [],
                "error_message":     str(exc)[:500],
            }
            for tb_line in error_tb.splitlines():
                test_log_lines.append({
                    "source":  f"test:{definition_id[:8]}",
                    "level":   "error",
                    "message": tb_line,
                    "ts":      completed_at.isoformat(),
                })

        completed_at = datetime.now(tz=timezone.utc)

        # Emit per-assertion results as log lines so they're visible even for failures
        for ar in outcome.get("assertion_results", []):
            status_str = "✓" if ar.get("passed") else "✗"
            detail     = ar.get("detail") or ""
            test_log_lines.append({
                "source":  f"test:{definition_id[:8]}",
                "level":   "info" if ar.get("passed") else "error",
                "message": f"  {status_str} [{ar.get('assertion_type', '?')}] {detail}",
                "ts":      completed_at.isoformat(),
            })

        # Error message as a log line
        if outcome.get("error_message") and not error_tb:
            test_log_lines.append({
                "source":  f"test:{definition_id[:8]}",
                "level":   "error",
                "message": f"  error: {outcome['error_message']}",
                "ts":      completed_at.isoformat(),
            })

        # Summary footer
        test_log_lines.append({
            "source":  f"test:{definition_id[:8]}",
            "level":   "info" if outcome["status"] == "passed" else "warn",
            "message": (
                f"[{definition_slug}] {outcome['status'].upper()} "
                f"({outcome['duration_ms']}ms)"
            ),
            "ts":      completed_at.isoformat(),
        })

        # Write result to DB
        async with SessionLocal() as db:
            await db.execute(
                text("""
                    UPDATE tests.results SET
                      status=:status, duration_ms=:dur,
                      assertion_results=CAST(:ar AS jsonb), logs=:logs,
                      error_message=:err, completed_at=:ts
                    WHERE id=:id
                """),
                {
                    "status": outcome["status"],
                    "dur":    outcome["duration_ms"],
                    "ar":     json.dumps(outcome["assertion_results"]),
                    "logs":   None,
                    "err":    outcome["error_message"],
                    "ts":     completed_at,
                    "id":     result_id,
                },
            )
            await db.commit()

        # Publish log batch for this test so the orchestrator can persist it
        await self._publish_log_batch(msg, test_log_lines)

        await self._publish_result(msg, outcome, result_id, started_at, completed_at)

    async def _publish_log_batch(self, cmd: dict, lines: list[dict]):
        """
        Publish a log_batch event to sandbox.events so the orchestrator consumer
        can bulk-insert the lines into orchestrator.run_logs.
        """
        if not lines:
            return
        payload = json.dumps({
            "event_id":   str(uuid.uuid4()),
            "run_id":     cmd["run_id"],
            "sandbox_id": cmd["sandbox_id"],
            "service":    "test-runner",
            "ts":         datetime.now(tz=timezone.utc).isoformat(),
            "event_type": "log_batch",
            "lines":      lines,
        }).encode()
        try:
            exchange = await self._channel.get_exchange("rvp.sandbox")
            await exchange.publish(
                aio_pika.Message(
                    body=payload,
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                ),
                routing_key="sandbox.events",
            )
        except Exception as exc:
            log.warning("Could not publish log_batch for run %s: %s", cmd["run_id"], exc)

    async def _publish_result(self, cmd: dict, outcome: dict, result_id: str,
                               started_at: datetime, completed_at: datetime):
        payload = json.dumps({
            "event_id":           str(uuid.uuid4()),
            "run_id":             cmd["run_id"],
            "sandbox_id":         cmd["sandbox_id"],
            "service":            "test-runner",
            "ts":                 completed_at.isoformat(),
            "result_id":          result_id,
            "definition_id":      cmd["definition_id"],
            "definition_version": cmd["definition_version"],
            "definition_slug":    cmd["definition_slug"],
            "status":             outcome["status"],
            "duration_ms":        outcome["duration_ms"],
            "assertion_results":  outcome["assertion_results"],
            "error_message":      outcome["error_message"],
            "started_at":         started_at.isoformat(),
            "completed_at":       completed_at.isoformat(),
        }).encode()

        exchange = await self._channel.get_exchange("rvp.tests")
        await exchange.publish(
            aio_pika.Message(
                body=payload,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key="tests.results",
        )
        log.info("Published result for %s → %s", cmd["definition_slug"], outcome["status"])
