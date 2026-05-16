"""
services/sandbox-manager/consumers/sandbox_queue.py
Consumes sandbox.queue (priority queue).
Enforces MAX_SANDBOXES cap — only ACKs when a slot is available.
Publishes SandboxEvents back on sandbox.events.

Improvements over previous version:
- Passes sdk_version + node_major_version to provisioner for v2.x stack selection
- Real Anvil health check (exec_run cast block-number) instead of flat sleep
- Cancellation checks before provisioning and before dispatching tests
- Port offset initialised from live DB state on startup (survives restarts)
- _wait_for_tests guards against the empty-set race (waits for dispatched_count > 0)
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
SANDBOX_HEALTH_TIMEOUT = int(os.environ.get("SANDBOX_HEALTH_TIMEOUT", "60"))
NODE_READY_DELAY       = int(os.environ.get("NODE_READY_DELAY", "15"))
V2_READY_TIMEOUT       = int(os.environ.get("V2_READY_TIMEOUT", "120"))

engine       = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

provisioner = SandboxProvisioner()

_port_offset_counter = 0


async def _publish_event(channel, event_type: str, sandbox_id: str, run_id: str, **extra):
    exchange = await channel.get_exchange("rvp.sandbox")
    payload  = {
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
    cols    = ", ".join(kwargs.keys())
    vals    = ", ".join(f":{k}" for k in kwargs)
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
        self._channel    = None

    async def start(self):
        self._connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self._channel    = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=1)
        await self._init_port_offset()

    async def _init_port_offset(self):
        """Set _port_offset_counter past any ports already in use by active sandboxes."""
        global _port_offset_counter
        from provisioner import ANVIL_PORT_BASE
        try:
            async with SessionLocal() as db:
                rows = await db.execute(
                    text("""
                        SELECT anvil_port FROM sandbox.sandboxes
                        WHERE status IN ('provisioning', 'ready') AND anvil_port IS NOT NULL
                    """)
                )
                used_ports = {r.anvil_port for r in rows.fetchall()}

            if not used_ports:
                return

            for offset in range(200):
                port = ANVIL_PORT_BASE + offset * 10
                if port not in used_ports:
                    _port_offset_counter = offset
                    log.info("Port offset initialised to %d (skipping %d active ports)",
                             offset, len(used_ports))
                    return
        except Exception as exc:
            log.warning("Could not initialise port offset from DB: %s", exc)

    async def run(self):
        queue = await self._channel.get_queue("sandbox.queue")
        async with queue.iterator() as q:
            async for message in q:
                await pool.wait_for_slot()
                async with message.process():
                    try:
                        await self._handle(json.loads(message.body))
                    except Exception as exc:
                        log.exception("Error handling sandbox request: %s", exc)

    async def _is_run_cancelled(self, run_id: str) -> bool:
        try:
            async with SessionLocal() as db:
                row = await db.execute(
                    text("SELECT status FROM orchestrator.runs WHERE id = :id"),
                    {"id": run_id},
                )
                r = row.fetchone()
                return r is not None and r.status == "cancelled"
        except Exception as exc:
            log.warning("Could not check run cancellation for %s: %s", run_id, exc)
            return False

    async def _handle(self, msg: dict):
        global _port_offset_counter

        run_id             = msg["run_id"]
        release_tag        = msg["release_tag"]
        image_tag          = msg["image_tag"]
        sdk_version        = msg.get("sdk_version")
        cli_version        = msg.get("cli_version")
        devnet_version     = msg.get("devnet_version")
        contracts_version  = msg.get("contracts_version")
        node_major_version = int(msg.get("node_major_version", 1))
        sandbox_id         = str(uuid.uuid4())

        acquired = await pool.acquire(sandbox_id, run_id)
        if not acquired:
            log.warning("Could not acquire pool slot — this shouldn't happen after wait_for_slot()")
            return

        port_offset = _port_offset_counter % 50
        _port_offset_counter += 1

        sandbox_provisioned = False

        try:
            # ── Pre-provision cancellation check ──────────────────────────────
            if await self._is_run_cancelled(run_id):
                log.info("Run %s cancelled before provisioning — skipping", run_id)
                return

            # ── Mark provisioning ─────────────────────────────────────────────
            async with SessionLocal() as db:
                await _upsert_sandbox(db, sandbox_id, run_id,
                                      status="provisioning",
                                      provisioned_at=datetime.now(tz=timezone.utc))
            await _publish_event(self._channel, "provisioning", sandbox_id, run_id)

            # ── Spin up Docker containers ──────────────────────────────────────
            try:
                info = await provisioner.provision(
                    sandbox_id, run_id, image_tag, port_offset,
                    sdk_version=sdk_version,
                    node_major_version=node_major_version,
                    cli_version=cli_version,
                    devnet_version=devnet_version,
                    contracts_version=contracts_version,
                )
                sandbox_provisioned = True
            except Exception as exc:
                log.exception("Sandbox %s provisioning failed: %s", sandbox_id, exc)
                async with SessionLocal() as db:
                    await _upsert_sandbox(db, sandbox_id, run_id,
                                          status="failed",
                                          failure_reason=str(exc))
                await _publish_event(self._channel, "failed", sandbox_id, run_id,
                                     failure_reason=str(exc))
                return

            # ── Wait for Anvil to be ready ─────────────────────────────────────
            anvil_id = info["container_ids"][0] if info["container_ids"] else None
            if anvil_id:
                healthy = await provisioner.wait_for_anvil_health(anvil_id, SANDBOX_HEALTH_TIMEOUT)
                if not healthy:
                    raise RuntimeError(
                        f"Anvil did not become healthy within {SANDBOX_HEALTH_TIMEOUT}s"
                    )

            # ── For v2.x: also wait for the jsonrpc-api container to be running ─
            if node_major_version >= 2 and len(info["container_ids"]) >= 7:
                db_container_id     = info["container_ids"][1]   # database is index 1
                jsonrpc_container_id = info["container_ids"][-1]  # jsonrpc-api is last
                ready = await provisioner.wait_for_v2_ready(
                    db_container_id, jsonrpc_container_id, V2_READY_TIMEOUT
                )
                if not ready:
                    log.warning("jsonrpc-api may not be fully ready for sandbox %s", sandbox_id)

            # Brief delay for node startup sequence
            await asyncio.sleep(NODE_READY_DELAY)

            # ── Post-provision cancellation check ──────────────────────────────
            if await self._is_run_cancelled(run_id):
                log.info("Run %s cancelled after provisioning — tearing down", run_id)
                return

            # ── Mark ready, publish event ──────────────────────────────────────
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
                cli_container_name=info.get("cli_container_name"),
            )

            # ── Wait for tests to finish ───────────────────────────────────────
            await self._wait_for_tests(sandbox_id, run_id)

        except Exception as exc:
            log.exception("Unhandled error in sandbox %s: %s", sandbox_id, exc)
            async with SessionLocal() as db:
                await _upsert_sandbox(db, sandbox_id, run_id,
                                      status="failed",
                                      failure_reason=str(exc))
            await _publish_event(self._channel, "failed", sandbox_id, run_id,
                                 failure_reason=str(exc))
        finally:
            if sandbox_provisioned:
                await self._teardown(sandbox_id, run_id)
            await pool.release(sandbox_id)

    async def _wait_for_tests(self, sandbox_id: str, run_id: str, timeout: int = 600):
        for _ in range(timeout // 5):
            await asyncio.sleep(5)
            async with SessionLocal() as db:
                meta_row = await db.execute(
                    text("""
                        SELECT COALESCE((metadata->>'dispatched_count')::int, 0)
                        FROM orchestrator.runs WHERE id = :id
                    """),
                    {"id": run_id},
                )
                dispatched = meta_row.scalar() or 0

                remaining_row = await db.execute(
                    text("""
                        SELECT COUNT(*) FROM tests.results
                        WHERE sandbox_id = :sid AND status IN ('pending', 'running')
                    """),
                    {"sid": sandbox_id},
                )
                remaining = remaining_row.scalar()

            if dispatched > 0 and remaining == 0:
                log.info("All %d tests done for sandbox %s", dispatched, sandbox_id)
                return
            elif dispatched == 0:
                log.debug("Waiting for test dispatch to complete (sandbox=%s)", sandbox_id)

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
            await db.execute(
                text("UPDATE sandbox.sandboxes SET status='closed', closed_at=:ts WHERE id=:id"),
                {"ts": datetime.now(tz=timezone.utc), "id": sandbox_id},
            )
            await db.commit()

        await _publish_event(self._channel, "closed", sandbox_id, run_id)

    async def stop(self):
        if self._connection:
            await self._connection.close()
