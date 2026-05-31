"""
services/orchestrator/consumers/sandbox_events.py
Consumes sandbox.events queue.
Updates run/sandbox state in DB, dispatches test commands when sandbox is READY.
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import aio_pika
from sqlalchemy import text

from db import AsyncSessionLocal
from models.run import RunLog
from publishers.notifications import publish_notification, publish_live

log = logging.getLogger("orchestrator.consumer.sandbox_events")
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://rvp:changeme@localhost:5672/")


class SandboxEventConsumer:
    def __init__(self):
        self._connection = None
        self._channel    = None

    async def start(self):
        self._connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self._channel    = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)

    async def run(self):
        queue = await self._channel.get_queue("sandbox.events")
        async with queue.iterator() as q:
            async for message in q:
                async with message.process():
                    try:
                        await self._handle(json.loads(message.body))
                    except Exception as exc:
                        log.exception("Error processing sandbox event: %s", exc)

    async def _is_run_cancelled(self, run_id: str) -> bool:
        async with AsyncSessionLocal() as db:
            row = await db.execute(
                text("SELECT status FROM orchestrator.runs WHERE id = :id"),
                {"id": run_id},
            )
            r = row.fetchone()
            return r is not None and r.status == "cancelled"

    async def _store_log_batch(self, run_id: str, lines: list):
        """
        Bulk-insert a batch of log lines into orchestrator.run_logs.
        Each element of `lines` must be a dict with keys:
          source, level, message, ts (ISO-8601 string)
        """
        if not lines:
            return
        try:
            # Build rows, clamping message to 4096 chars
            rows = [
                {
                    "run_id":  run_id,
                    "source":  str(entry.get("source", "unknown"))[:64],
                    "level":   str(entry.get("level", "info")),
                    "message": str(entry.get("message", ""))[:4096],
                    "ts":      entry.get("ts") or datetime.now(tz=timezone.utc).isoformat(),
                }
                for entry in lines
                if isinstance(entry, dict)
            ]
            if not rows:
                return
            async with AsyncSessionLocal() as db:
                await db.execute(
                    text("""
                        INSERT INTO orchestrator.run_logs (run_id, source, level, message, ts)
                        SELECT
                            CAST(r->>'run_id'  AS uuid),
                            r->>'source',
                            r->>'level',
                            r->>'message',
                            CAST(r->>'ts' AS timestamptz)
                        FROM jsonb_array_elements(CAST(:rows AS jsonb)) AS r
                    """),
                    {"rows": json.dumps(rows)},
                )
                await db.commit()
        except Exception as exc:
            log.warning("Could not store log_batch (%d lines) for run %s: %s",
                        len(lines), run_id, exc)

    async def _store_run_event(self, run_id: str, event_type: str, payload: dict):
        """Insert a row into orchestrator.run_events for history/audit."""
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(
                    text("""
                        INSERT INTO orchestrator.run_events (id, run_id, event_type, payload, ts)
                        VALUES (:id, :run_id, :event_type, :payload, :ts)
                    """),
                    {
                        "id":         str(uuid.uuid4()),
                        "run_id":     run_id,
                        "event_type": event_type,
                        "payload":    json.dumps(payload),
                        "ts":         datetime.now(tz=timezone.utc),
                    },
                )
                await db.commit()
        except Exception as exc:
            log.warning("Could not store run_event %s for run %s: %s", event_type, run_id, exc)

    async def _handle(self, msg: dict):
        event_type = msg.get("event_type")
        run_id     = msg.get("run_id")
        sandbox_id = msg.get("sandbox_id")
        log.info("Sandbox event: %s  run=%s  sandbox=%s", event_type, run_id, sandbox_id)

        if run_id and await self._is_run_cancelled(run_id):
            log.info("Run %s is cancelled — ignoring sandbox event %s", run_id, event_type)
            return

        # ── log_batch: persist lines to run_logs + broadcast for live viewers ──
        if event_type == "log_batch":
            lines = msg.get("lines") or []
            # Store persistently — this is the core of the new log system.
            await self._store_log_batch(run_id, lines)
            # Broadcast to the live dashboard via Redis pub/sub ONLY.
            # publish_notification() is intentionally avoided here because:
            #   1. It opens a new RabbitMQ connection per call — unacceptable at
            #      log_batch frequency (up to dozens per second per sandbox).
            #   2. It fans out to rvp.notify (Discord etc.) — log lines should
            #      never trigger Discord notifications.
            await publish_live({
                "event_id":   str(uuid.uuid4()),
                "run_id":     run_id,
                "sandbox_id": sandbox_id,
                "service":    "orchestrator",
                "ts":         datetime.now(tz=timezone.utc).isoformat(),
                "event_type": "log_batch",
                "lines":      lines,
            })
            return

        if event_type == "step":
            step   = msg.get("step", "")
            status = msg.get("step_status", "ok")
            detail = msg.get("detail") or {}

            # service_log events are the legacy high-frequency per-line events.
            # Now that we have log_batch + run_logs we still broadcast them for
            # any WebSocket clients on old code paths, but still skip DB storage
            # since log_batch handles persistence more efficiently.
            if step != "service_log":
                await self._store_run_event(run_id, "sandbox.step", msg)

            await publish_notification(
                "sandbox.step",
                step,
                run_id=run_id,
                sandbox_id=sandbox_id,
                step=step,
                step_status=status,
                **{k: v for k, v in detail.items() if v is not None},
            )
            return

        async with AsyncSessionLocal() as db:
            if event_type == "provisioning":
                await self._store_run_event(run_id, "sandbox.provisioning", msg)
                await publish_notification("sandbox.provisioning", "Sandbox provisioning",
                                           run_id=run_id, sandbox_id=sandbox_id)

            elif event_type == "ready":
                await db.execute(
                    text("UPDATE orchestrator.runs SET status='running', started_at=:ts WHERE id=:id"),
                    {"ts": datetime.now(tz=timezone.utc), "id": run_id},
                )
                await db.commit()
                await self._store_run_event(run_id, "sandbox.ready", msg)
                await self._dispatch_tests(run_id, sandbox_id, msg)
                await publish_notification("sandbox.ready", "Sandbox ready",
                                           run_id=run_id, sandbox_id=sandbox_id)

            elif event_type == "failed":
                await db.execute(
                    text("UPDATE orchestrator.runs SET status='failed' WHERE id=:id"),
                    {"id": run_id},
                )
                await db.commit()
                await self._store_run_event(run_id, "sandbox.failed", msg)
                await publish_notification("sandbox.failed", "Sandbox failed",
                                           run_id=run_id, reason=msg.get("failure_reason"))

            elif event_type == "closed":
                log.info("Sandbox %s closed for run %s", sandbox_id, run_id)
                await self._store_run_event(run_id, "sandbox.closed", msg)
                await publish_notification("sandbox.closed", "Sandbox closed",
                                           run_id=run_id, sandbox_id=sandbox_id)

    async def _dispatch_tests(self, run_id: str, sandbox_id: str, sandbox_msg: dict):
        """Fetch active test definitions and dispatch a TestCommand for each."""
        import aio_pika as mq
        from publishers.sandbox_requests import RABBITMQ_URL as MQ_URL

        async with AsyncSessionLocal() as db:
            # Fetch run metadata + node version from release_catalog join
            run_row = await db.execute(
                text("""
                    SELECT r.suite_ids,
                           r.app_address,
                           COALESCE(rc.node_major_version, 1) AS node_major_version
                    FROM orchestrator.runs r
                    LEFT JOIN github.release_catalog rc ON rc.tag = r.release_tag
                    WHERE r.id = :id
                """),
                {"id": run_id},
            )
            run = run_row.fetchone()
            suite_ids          = run.suite_ids  if run else None
            node_major_version = run.node_major_version if run else 1
            # app_address is set by sandbox_queue consumer after deploy; also forwarded
            # from sandbox_msg so we always have the most up-to-date value.
            app_address = (sandbox_msg.get("app_address")
                           or (run.app_address if run else None))

            all_rows = await db.execute(
                text("""
                    SELECT id, slug, version FROM tests.definitions
                    WHERE is_active = true
                    AND min_node_major_version = :node_version
                """),
                {"node_version": node_major_version},
            )
            all_definitions = all_rows.fetchall()

        if suite_ids:
            suite_set   = {str(s) for s in suite_ids}
            definitions = [d for d in all_definitions if str(d.id) in suite_set]
            log.info("Suite filter: %d/%d definitions selected for run %s",
                     len(definitions), len(all_definitions), run_id)
        else:
            definitions = all_definitions

        conn = await mq.connect_robust(MQ_URL)
        async with conn:
            ch       = await conn.channel()
            exchange = await ch.get_exchange("rvp.tests")
            for defn in definitions:
                body = json.dumps({
                    "event_id":              str(uuid.uuid4()),
                    "run_id":                run_id,
                    "sandbox_id":            sandbox_id,
                    "service":               "orchestrator",
                    "ts":                    datetime.now(tz=timezone.utc).isoformat(),
                    "definition_id":         str(defn.id),
                    "definition_version":    defn.version,
                    "definition_slug":       defn.slug,
                    "anvil_port":            sandbox_msg.get("anvil_port"),
                    "node_port":             sandbox_msg.get("node_port"),
                    "graphql_port":          sandbox_msg.get("graphql_port"),
                    "docker_network":        sandbox_msg.get("docker_network"),
                    "node_major_version":    node_major_version,
                    "cli_container_name":    sandbox_msg.get("cli_container_name"),
                    "app_address":           app_address,
                    "inputbox_address":       sandbox_msg.get("inputbox_address"),
                    "ether_portal_address":   sandbox_msg.get("ether_portal_address"),
                    "erc20_portal_address":   sandbox_msg.get("erc20_portal_address"),
                    "erc721_portal_address":  sandbox_msg.get("erc721_portal_address"),
                    "erc1155_portal_address": sandbox_msg.get("erc1155_portal_address"),
                    "erc20_token_address":    sandbox_msg.get("erc20_token_address"),
                    "erc721_token_address":   sandbox_msg.get("erc721_token_address"),
                    "erc1155_token_address":  sandbox_msg.get("erc1155_token_address"),
                }).encode()
                await exchange.publish(
                    mq.Message(body=body, content_type="application/json",
                               delivery_mode=mq.DeliveryMode.PERSISTENT),
                    routing_key="tests.commands",
                )

        dispatched = len(definitions)
        log.info("Dispatched %d test commands for run %s (node_major=%d)",
                 dispatched, run_id, node_major_version)

        async with AsyncSessionLocal() as db:
            await db.execute(
                text("""
                    UPDATE orchestrator.runs
                    SET metadata = jsonb_set(
                        COALESCE(metadata, '{}'),
                        '{dispatched_count}',
                        CAST(:count AS jsonb)
                    )
                    WHERE id = :id
                """),
                {"count": str(dispatched), "id": run_id},
            )
            await db.commit()

    async def stop(self):
        if self._connection:
            await self._connection.close()
