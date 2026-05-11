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
from publishers.notifications import publish_notification

log = logging.getLogger("orchestrator.consumer.sandbox_events")
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://rvp:changeme@localhost:5672/")


class SandboxEventConsumer:
    def __init__(self):
        self._connection = None
        self._channel = None

    async def start(self):
        self._connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self._channel = await self._connection.channel()
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

    async def _handle(self, msg: dict):
        event_type = msg.get("event_type")
        run_id     = msg.get("run_id")
        sandbox_id = msg.get("sandbox_id")
        log.info("Sandbox event: %s  run=%s  sandbox=%s", event_type, run_id, sandbox_id)

        async with AsyncSessionLocal() as db:
            # Update run status based on sandbox lifecycle
            if event_type == "ready":
                await db.execute(
                    text("UPDATE orchestrator.runs SET status='running', started_at=:ts WHERE id=:id"),
                    {"ts": datetime.now(tz=timezone.utc), "id": run_id},
                )
                await db.commit()
                # Dispatch test commands
                await self._dispatch_tests(run_id, sandbox_id, msg)
                await publish_notification("sandbox.ready", "Sandbox ready", run_id=run_id,
                                           sandbox_id=sandbox_id)

            elif event_type == "failed":
                await db.execute(
                    text("UPDATE orchestrator.runs SET status='failed' WHERE id=:id"),
                    {"id": run_id},
                )
                await db.commit()
                await publish_notification("sandbox.failed", "Sandbox failed", run_id=run_id,
                                           reason=msg.get("failure_reason"))

            elif event_type == "closed":
                log.info("Sandbox %s closed for run %s", sandbox_id, run_id)

    async def _dispatch_tests(self, run_id: str, sandbox_id: str, sandbox_msg: dict):
        """Fetch all active test definitions and publish a TestCommand for each."""
        import aio_pika as mq
        from publishers.sandbox_requests import RABBITMQ_URL as MQ_URL

        async with AsyncSessionLocal() as db:
            rows = await db.execute(
                text("SELECT id, slug, version FROM tests.definitions WHERE is_active = true")
            )
            definitions = rows.fetchall()

        conn = await mq.connect_robust(MQ_URL)
        async with conn:
            ch = await conn.channel()
            exchange = await ch.get_exchange("rvp.tests")
            for defn in definitions:
                body = json.dumps({
                    "event_id":           str(uuid.uuid4()),
                    "run_id":             run_id,
                    "sandbox_id":         sandbox_id,
                    "service":            "orchestrator",
                    "ts":                 datetime.now(tz=timezone.utc).isoformat(),
                    "definition_id":      str(defn.id),
                    "definition_version": defn.version,
                    "definition_slug":    defn.slug,
                    "anvil_port":         sandbox_msg.get("anvil_port"),
                    "node_port":          sandbox_msg.get("node_port"),
                    "graphql_port":       sandbox_msg.get("graphql_port"),
                    "docker_network":     sandbox_msg.get("docker_network"),
                }).encode()
                await exchange.publish(
                    mq.Message(body=body, content_type="application/json",
                               delivery_mode=mq.DeliveryMode.PERSISTENT),
                    routing_key="tests.commands",
                )
        log.info("Dispatched %d test commands for run %s", len(definitions), run_id)

    async def stop(self):
        if self._connection:
            await self._connection.close()
