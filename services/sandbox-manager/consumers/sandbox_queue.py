"""
services/sandbox-manager/consumers/sandbox_queue.py
Consumes sandbox.queue (priority queue).
Enforces MAX_SANDBOXES cap — only ACKs when a slot is available.
Publishes SandboxEvents back on sandbox.events.

Hardening additions
-------------------
Fix 1 – Startup orphan sweep: on start(), any sandbox left in provisioning/ready
         state from a previous process is torn down before consuming new messages.
Fix 2 – snapshot_volume persisted in DB: teardown can recover the per-sandbox
         snapshot volume name after a restart without relying on in-memory state.
Fix 3 – Periodic GC loop: every GC_INTERVAL_SECONDS, scan Docker for labelled
         resources whose sandbox_id is no longer active and remove them.
Fix 5 – Task tracking: in-flight _handle tasks are tracked in _running_tasks so
         drain() can wait for them on graceful shutdown.
"""
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import aio_pika
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from pool import pool, MAX_SANDBOXES
from provisioner import SandboxProvisioner
from log_buffer import LogBatchBuffer

log = logging.getLogger("sandbox-manager.consumer")

RABBITMQ_URL     = os.environ.get("RABBITMQ_URL", "amqp://rvp:changeme@localhost:5672/")
DATABASE_URL     = os.environ.get("DATABASE_URL", "").replace(
    "postgresql://", "postgresql+asyncpg://"
)
NODE_READY_DELAY = int(os.environ.get("NODE_READY_DELAY", "15"))
V2_READY_TIMEOUT = int(os.environ.get("V2_READY_TIMEOUT", "120"))
GC_INTERVAL      = int(os.environ.get("GC_INTERVAL_SECONDS", "600"))

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
        self._connection    = None
        self._channel       = None
        # Fix 5: track in-flight tasks for graceful drain
        self._running_tasks: set[asyncio.Task] = set()
        # Fix 3: GC background task handle
        self._gc_task: Optional[asyncio.Task]  = None

    async def start(self):
        self._connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self._channel    = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=MAX_SANDBOXES)
        await self._init_port_offset()
        # Fix 1: clean up any containers left from a previous process
        await self._sweep_orphaned_sandboxes()
        # Fix 3: start periodic GC loop
        self._gc_task = asyncio.create_task(self._gc_loop())

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

    # ── Fix 1: Startup orphan sweep ────────────────────────────────────────────

    async def _sweep_orphaned_sandboxes(self):
        """
        On startup, tear down any sandboxes left in provisioning/ready state from
        a previous process.  The DB holds container_ids, docker_network, and
        snapshot_volume (Fix 2), giving teardown everything it needs.
        """
        try:
            async with SessionLocal() as db:
                rows = await db.execute(
                    text("""
                        SELECT id, run_id, container_ids, docker_network, snapshot_volume
                        FROM sandbox.sandboxes
                        WHERE status IN ('provisioning', 'ready')
                    """)
                )
                orphans = rows.fetchall()
        except Exception as exc:
            log.warning("Startup sweep: could not query DB: %s", exc)
            return

        if not orphans:
            log.info("Startup sweep: no orphaned sandboxes found")
            return

        log.warning(
            "Startup sweep: found %d orphaned sandbox(es) — tearing down", len(orphans)
        )
        for sbx in orphans:
            sid = str(sbx.id)
            log.info("Startup sweep: tearing down orphaned sandbox %s (run=%s)",
                     sid[:8], str(sbx.run_id)[:8])
            try:
                await provisioner.teardown(
                    sid,
                    sbx.container_ids or [],
                    sbx.docker_network or f"rvp-sbx-{sid[:8]}",
                    per_sandbox_volume=sbx.snapshot_volume,
                )
            except Exception as exc:
                log.warning("Startup sweep: teardown failed for sandbox %s: %s", sid[:8], exc)
            finally:
                try:
                    async with SessionLocal() as db:
                        await db.execute(
                            text("""
                                UPDATE sandbox.sandboxes
                                SET status = 'closed', closed_at = :ts
                                WHERE id = :id
                            """),
                            {"ts": datetime.now(tz=timezone.utc), "id": sid},
                        )
                        await db.commit()
                except Exception as exc:
                    log.warning("Startup sweep: could not mark sandbox %s closed: %s",
                                sid[:8], exc)

    # ── Fix 3: Periodic GC loop ────────────────────────────────────────────────

    async def _gc_loop(self):
        """
        Run the Docker resource GC every GC_INTERVAL seconds.
        Catches anything the normal teardown path missed (transient Docker errors,
        SIGKILL during in-flight tasks, ephemeral build containers, etc.).
        """
        log.info("GC loop started (interval=%ds)", GC_INTERVAL)
        while True:
            await asyncio.sleep(GC_INTERVAL)
            try:
                await self._run_gc()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("GC loop error: %s", exc)

    async def _run_gc(self):
        """Query active sandbox IDs from DB then delegate Docker cleanup to provisioner."""
        try:
            async with SessionLocal() as db:
                rows = await db.execute(
                    text("""
                        SELECT id::text FROM sandbox.sandboxes
                        WHERE status IN ('provisioning', 'ready')
                    """)
                )
                active_ids = {r[0] for r in rows.fetchall()}
        except Exception as exc:
            log.warning("GC: could not fetch active sandboxes from DB: %s", exc)
            return

        loop = asyncio.get_event_loop()
        cleaned = await loop.run_in_executor(
            None, provisioner.gc_orphaned_resources, active_ids
        )
        if cleaned:
            log.info("GC run complete: cleaned up %d orphaned sandbox(es)", cleaned)
        else:
            log.debug("GC run complete: nothing to clean")

    # ── Consumer loop ──────────────────────────────────────────────────────────

    async def run(self):
        queue = await self._channel.get_queue("sandbox.queue")
        async with queue.iterator() as q:
            async for message in q:
                await pool.wait_for_slot()
                body = json.loads(message.body)
                await message.ack()
                # Fix 5: track task so drain() can wait for it
                task = asyncio.create_task(self._handle(body))
                self._running_tasks.add(task)
                task.add_done_callback(self._running_tasks.discard)

    # ── Fix 5: Graceful drain ──────────────────────────────────────────────────

    async def drain(self, timeout: int = 120):
        """
        Wait for all in-flight _handle tasks to complete.
        Called on SIGTERM before the process exits so containers are torn down
        cleanly rather than left dangling.
        """
        if not self._running_tasks:
            return
        log.info("Draining %d in-flight sandbox task(s)…", len(self._running_tasks))
        try:
            await asyncio.wait_for(
                asyncio.gather(*list(self._running_tasks), return_exceptions=True),
                timeout=timeout,
            )
            log.info("All sandbox tasks drained cleanly")
        except asyncio.TimeoutError:
            log.warning(
                "Drain timed out after %ds — %d task(s) still running; cancelling",
                timeout, len(self._running_tasks),
            )
            for task in list(self._running_tasks):
                task.cancel()
            await asyncio.gather(*list(self._running_tasks), return_exceptions=True)

    # ── Cancellation check ────────────────────────────────────────────────────

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

    # ── Sandbox lifecycle ──────────────────────────────────────────────────────

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
        # Application registry fields (present when run was triggered with an app_id)
        app_id             = msg.get("app_id")
        app_name           = msg.get("app_name")
        app_github_url     = msg.get("app_github_url")
        sandbox_id         = str(uuid.uuid4())

        # If contracts_version not in message, resolve it from release_catalog via release_tag
        if not contracts_version and release_tag:
            contracts_version = await self._resolve_contracts_version(release_tag)
            if contracts_version:
                log.info(
                    "Resolved contracts_version=%s for release_tag=%s",
                    contracts_version, release_tag,
                )

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
            loop = asyncio.get_event_loop()
            channel = self._channel

            def step_reporter(step: str, status: str = "ok", **detail):
                """
                Called synchronously from the provisioner thread executor.
                Schedules a step event publish on the async event loop so the
                orchestrator and dashboard can receive real-time progress.
                """
                coro = _publish_event(
                    channel, "step", sandbox_id, run_id,
                    step=step, step_status=status,
                    detail=detail if detail else None,
                )
                asyncio.run_coroutine_threadsafe(coro, loop)

            def log_batch_reporter(batch: list):
                """
                Called from LogBatchBuffer when a batch of log lines is ready.
                Publishes a log_batch event to RabbitMQ for the orchestrator to
                persist into run_logs and broadcast over WebSocket.
                """
                coro = _publish_event(
                    channel, "log_batch", sandbox_id, run_id,
                    lines=batch,
                )
                asyncio.run_coroutine_threadsafe(coro, loop)

            log_buffer = LogBatchBuffer(flush_cb=log_batch_reporter, max_lines=50, max_age_s=2.0)

            try:
                info = await provisioner.provision(
                    sandbox_id, run_id, image_tag, port_offset,
                    sdk_version=sdk_version,
                    node_major_version=node_major_version,
                    cli_version=cli_version,
                    devnet_version=devnet_version,
                    contracts_version=contracts_version,
                    step_cb=step_reporter,
                    log_buffer=log_buffer,
                    app_name=app_name,
                    app_github_url=app_github_url,
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

            # ── For v2.x: also wait for the jsonrpc-api container to be running ─
            # (Anvil health check + contract deployment are handled inside provisioner)
            if node_major_version >= 2 and len(info["container_ids"]) >= 7:
                db_container_id      = info["container_ids"][1]   # database is index 1
                jsonrpc_container_id = info["container_ids"][6]   # jsonrpc-api is always index 6
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

            # ── Mark ready — Fix 2: persist snapshot_volume to DB ─────────────
            app_address = info.get("app_address")
            async with SessionLocal() as db:
                await _upsert_sandbox(db, sandbox_id, run_id,
                                      status="ready",
                                      docker_network=info["docker_network"],
                                      container_ids=info["container_ids"],
                                      anvil_port=info["anvil_port"],
                                      node_port=info["node_port"],
                                      graphql_port=info["graphql_port"],
                                      snapshot_volume=info.get("per_sandbox_volume"),
                                      ready_at=datetime.now(tz=timezone.utc))

                # Persist app_address back to orchestrator.runs so the dashboard can show it
                if app_address:
                    await db.execute(
                        text("UPDATE orchestrator.runs SET app_address = :addr WHERE id = :id"),
                        {"addr": app_address, "id": run_id},
                    )
                    await db.commit()

            await _publish_event(
                self._channel, "ready", sandbox_id, run_id,
                anvil_port=info["anvil_port"],
                node_port=info["node_port"],
                graphql_port=info["graphql_port"],
                docker_network=info["docker_network"],
                container_ids=info["container_ids"],
                cli_container_name=info.get("cli_container_name"),
                app_address=app_address,
                inputbox_address=info.get("inputbox_address"),
                ether_portal_address=info.get("ether_portal_address"),
                erc20_portal_address=info.get("erc20_portal_address"),
                erc721_portal_address=info.get("erc721_portal_address"),
                erc1155_portal_address=info.get("erc1155_portal_address"),
                erc20_token_address=info.get("erc20_token_address"),
                erc721_token_address=info.get("erc721_token_address"),
                erc1155_token_address=info.get("erc1155_token_address"),
            )

            # ── Wait for all dispatched tests to complete ──────────────────────
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

    async def _wait_for_tests(self, sandbox_id: str, run_id: str, timeout: int = 7200):
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

                counts_row = await db.execute(
                    text("""
                        SELECT
                            COUNT(*) FILTER (WHERE status IN ('pending', 'running')) AS in_flight,
                            COUNT(*) AS total_started
                        FROM tests.results
                        WHERE sandbox_id = :sid
                    """),
                    {"sid": sandbox_id},
                )
                counts = counts_row.fetchone()
                in_flight     = counts.in_flight     if counts else 0
                total_started = counts.total_started if counts else 0

            if dispatched > 0 and total_started >= dispatched and in_flight == 0:
                log.info("All %d tests done for sandbox %s", dispatched, sandbox_id)
                return
            elif dispatched == 0:
                log.debug("Waiting for test dispatch to complete (sandbox=%s)", sandbox_id)
            else:
                log.debug(
                    "Sandbox %s waiting: dispatched=%d started=%d in_flight=%d",
                    sandbox_id, dispatched, total_started, in_flight,
                )

        log.warning("Timeout waiting for tests on sandbox %s — tearing down anyway", sandbox_id)

    async def _teardown(self, sandbox_id: str, run_id: str):
        async with SessionLocal() as db:
            row = await db.execute(
                text("""
                    SELECT container_ids, docker_network, snapshot_volume
                    FROM sandbox.sandboxes WHERE id = :id
                """),
                {"id": sandbox_id},
            )
            sbx = row.fetchone()

        if sbx and sbx.container_ids:
            # Fix 2: read snapshot_volume from DB (no longer relies on in-memory dict)
            await provisioner.teardown(
                sandbox_id,
                sbx.container_ids,
                sbx.docker_network or "",
                per_sandbox_volume=sbx.snapshot_volume,
            )

        async with SessionLocal() as db:
            await db.execute(
                text("UPDATE sandbox.sandboxes SET status='closed', closed_at=:ts WHERE id=:id"),
                {"ts": datetime.now(tz=timezone.utc), "id": sandbox_id},
            )
            await db.commit()

        await _publish_event(self._channel, "closed", sandbox_id, run_id)

    async def _resolve_contracts_version(self, release_tag: str) -> Optional[str]:
        """
        Resolve contracts_version for a given node release tag by walking the
        BCNF FK chain:
          release_catalog.cli_tag → cli_catalog.tag
          cli_catalog.devnet_tag  → devnet_catalog.tag
          devnet_catalog.contracts_tag → contracts_catalog.tag
        """
        try:
            async with SessionLocal() as db:
                row = await db.execute(
                    text("""
                        SELECT d.contracts_tag
                        FROM github.release_catalog rc
                        LEFT JOIN github.cli_catalog    c ON c.tag = rc.cli_tag
                        LEFT JOIN github.devnet_catalog d ON d.tag = c.devnet_tag
                        WHERE rc.tag = :tag
                        LIMIT 1
                    """),
                    {"tag": release_tag},
                )
                r = row.fetchone()
                if not r:
                    return None
                return r.contracts_tag or None
        except Exception as exc:
            log.warning(
                "Could not resolve contracts_version for release_tag=%s: %s",
                release_tag, exc,
            )
            return None

    async def stop(self):
        if self._gc_task:
            self._gc_task.cancel()
            try:
                await self._gc_task
            except asyncio.CancelledError:
                pass
        if self._connection:
            await self._connection.close()
