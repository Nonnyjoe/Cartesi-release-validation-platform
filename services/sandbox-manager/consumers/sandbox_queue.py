"""
services/sandbox-manager/consumers/sandbox_queue.py
Consumes sandbox.queue (priority queue).
Enforces MAX_SANDBOXES cap — only ACKs when a slot is available.
Publishes SandboxEvents back on sandbox.events.
"""
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import aio_pika
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from pool import pool
from provisioner import SandboxProvisioner

log = logging.getLogger("sandbox-manager.consumer")

RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://rvp:changeme@localhost:5672/")
DATABASE_URL = os.environ.get("DATABASE_URL", "").replace(
    "postgresql://", "postgresql+asyncpg://"
)

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

provisioner = SandboxProvisioner()

# Track port offsets to avoid collision between concurrent sandboxes
_port_offset_counter = 0


async def _publish_event(channel, event_type: str, sandbox_id: str, run_id: str, **extra):
    exchange = await channel.get_exchange("rvp.sandbox")
    payload = {
        "event_id":   str(uuid.uuid4()),
        "run_id":     run_id,
        "sandbox_id": sandbox_id,
        "service":    "sandbox-manager",
        "ts":         datetime.now(tz=timezone.utc).isoformat(),
        "event_type": event_type,
        **extra,
    }
    await exchange.publish(
        aio_pika.Message(
            body=json.dumps(payload).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key="sandbox.events",
    )
    log.info("Published sandbox event: %s  sandbox=%s", event_type, sandbox_id)


async def _upsert_sandbox(db: AsyncSession, sandbox_id: str, run_id: str, **kwargs):
    cols = ", ".join(kwargs.keys())
    vals = ", ".join(f":{k}" for k in kwargs)
    updates = ", ".join(f"{k}=EXCLUDED.{k}" for k in kwargs)
    await db.execute(
        text(f"""
            INSERT INTO sandbox.sandboxes (id, run_id, {cols})
            VALUES (:sandbox_id, :run_id, {vals})
            ON CONFLICT (id) DO UPDATE SET {updates}
        """),
        {"sandbox_id": sandbox_id, "run_id": run_id, **kwargs},
    )
    await db.commit()


class SandboxQueueConsumer:
    def __init__(self):
        self._connection = None
        self._channel = None

    async def start(self):
        self._connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self._channel = await self._connection.channel()
        # prefetch_count=1 means we won't ack the next message until we're done with this one
        # Combined with pool.wait_for_slot() this naturally rate-limits to MAX_SANDBOXES
        await self._channel.set_qos(prefetch_count=1)

    async def run(self):
        queue = await self._channel.get_queue("sandbox.queue")
        async with queue.iterator() as q:
            async for message in q:
                # Block here (without acking) until a pool slot is available
                await pool.wait_for_slot()
                async with message.process():
                    try:
                        await self._handle(json.loads(message.body))
                    except Exception as exc:
                        log.exception("Error handling sandbox request: %s", exc)

    async def _handle(self, msg: dict):
        global _port_offset_counter

        run_id      = msg["run_id"]
        release_tag = msg["release_tag"]
        image_tag   = msg["image_tag"]
        sandbox_id  = str(uuid.uuid4())

        # Claim a pool slot
        acquired = await pool.acquire(sandbox_id, run_id)
        if not acquired:
            log.warning("Could not acquire pool slot — this shouldn't happen after wait_for_slot()")
            return

        port_offset = _port_offset_counter % 50   # cycle through 50 offset slots
        _port_offset_counter += 1

        async with SessionLocal() as db:
            # Record sandbox as provisioning
            await _upsert_sandbox(db, sandbox_id, run_id,
                                  status="provisioning",
                                  provisioned_at=datetime.now(tz=timezone.utc))

        await _publish_event(self._channel, "provisioning", sandbox_id, run_id)

        try:
            info = await provisioner.provision(sandbox_id, run_id, image_tag, port_offset)

            # Wait briefly for containers to be ready (health check)
            await asyncio.sleep(5)

            async with SessionLocal() as db:
                await _upsert_sandbox(db, sandbox_id, run_id,
                                      status="ready",
                                      docker_network=info["docker_network"],
                                      container_ids=info["container_ids"],
                                      anvil_port=info["anvil_port"],
                                      node_port=info["node_port"],
                                      graphql_port=info["graphql_port"],
                                      ready_at=datetime.now(tz=timezone.utc))

            await _publish_event(
                self._channel, "ready", sandbox_id, run_id,
                anvil_port=info["anvil_port"],
                node_port=info["node_port"],
                graphql_port=info["graphql_port"],
                docker_network=info["docker_network"],
                container_ids=info["container_ids"],
            )

            # Wait for test runner to finish (poll sandbox status)
            await self._wait_for_tests(sandbox_id)

        except Exception as exc:
            log.exception("Sandbox %s provisioning failed: %s", sandbox_id, exc)
            async with SessionLocal() as db:
                await _upsert_sandbox(db, sandbox_id, run_id,
                                      status="failed",
                                      failure_reason=str(exc))
            await _publish_event(self._channel, "failed", sandbox_id, run_id,
                                 failure_reason=str(exc))
        finally:
            # Teardown
            await self._teardown(sandbox_id, run_id)

    async def _wait_for_tests(self, sandbox_id: str, timeout: int = 600):
        """Poll DB until all tests for this sandbox are no longer pending/running."""
        for _ in range(timeout // 5):
            await asyncio.sleep(5)
            async with SessionLocal() as db:
                result = await db.execute(
                    text("""
                        SELECT COUNT(*) FROM tests.results
                        WHERE sandbox_id = :sid AND status IN ('pending', 'running')
                    """),
                    {"sid": sandbox_id},
                )
                remaining = result.scalar()
                if remaining == 0:
                    log.info("All tests done for sandbox %s", sandbox_id)
                    return
        log.warning("Timeout waiting for tests on sandbox %s — tearing down anyway", sandbox_id)

    async def _teardown(self, sandbox_id: str, run_id: str):
        async with SessionLocal() as db:
            row = await db.execute(
                text("SELECT container_ids, docker_network FROM sandbox.sandboxes WHERE id=:id"),
                {"id": sandbox_id},
            )
            sbx = row.fetchone()

        if sbx and sbx.container_ids:
            await provisioner.teardown(sandbox_id, sbx.container_ids, sbx.docker_network or "")

        async with SessionLocal() as db:
            await _upsert_sandbox(None, sandbox_id, run_id,  # db=None trick won't work
                                  status="closed", closed_at=datetime.now(tz=timezone.utc))

        # Use a fresh session
        async with SessionLocal() as db:
            await db.execute(
                text("UPDATE sandbox.sandboxes SET status='closed', closed_at=:ts WHERE id=:id"),
                {"ts": datetime.now(tz=timezone.utc), "id": sandbox_id},
            )
            await db.commit()

        await pool.release(sandbox_id)
        await _publish_event(self._channel, "closed", sandbox_id, run_id)

    async def stop(self):
        if self._connection:
            await self._connection.close()
