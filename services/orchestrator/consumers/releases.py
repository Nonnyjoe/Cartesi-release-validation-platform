"""
services/orchestrator/consumers/releases.py
Consumes release events from the releases.orchestrator queue.

When github-watcher publishes a new release event, this consumer:
  1. Looks up the release catalog to get the resolved image_tag, sdk_version,
     and node_major_version (populated by the watcher's _upsert_catalog).
  2. Generates a run_id and inserts a Run record into orchestrator.runs.
  3. THEN publishes the SandboxRequest to sandbox.queue.

Ordering guarantee: the run record always exists before the sandbox-manager
picks up the request, eliminating the race where sandbox events would find
no matching run row and silently drop all status updates.
"""
import json
import logging
import os
import sys
import uuid
from datetime import datetime, timezone

import aio_pika
from sqlalchemy import text

from db import AsyncSessionLocal
from publishers.sandbox_requests import publish_sandbox_request

sys.path.insert(0, "/app/shared")
from sdk_resolver import derive_image_tag, node_major_version as _major

log = logging.getLogger("orchestrator.consumer.releases")
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://rvp:changeme@localhost:5672/")


class ReleasesConsumer:
    def __init__(self):
        self._connection = None
        self._channel    = None

    async def start(self):
        self._connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self._channel    = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=5)

    async def run(self):
        queue = await self._channel.get_queue("releases.orchestrator")
        async with queue.iterator() as q:
            async for message in q:
                async with message.process():
                    try:
                        await self._handle(json.loads(message.body))
                    except Exception as exc:
                        log.exception("Error processing release event: %s", exc)

    async def _handle(self, msg: dict):
        tag_name = msg.get("tag_name", "unknown")
        html_url = msg.get("html_url", "")
        log.info("Release event received: tag=%s", tag_name)

        async with AsyncSessionLocal() as db:
            # ── Idempotency: skip if a github_release run already exists ──────
            existing = await db.execute(
                text("""
                    SELECT id FROM orchestrator.runs
                    WHERE release_tag = :tag AND triggered_by = 'github_release'
                    LIMIT 1
                """),
                {"tag": tag_name},
            )
            if existing.fetchone():
                log.info("Run for release %s already exists — skipping", tag_name)
                return

            # ── Look up the release catalog for the resolved image / SDK / CLI info ─
            catalog_row = await db.execute(
                text("""
                    SELECT image_tag, sdk_version, cli_version, devnet_version,
                           contracts_version, node_major_version
                    FROM github.release_catalog
                    WHERE tag = :tag
                """),
                {"tag": tag_name},
            )
            catalog = catalog_row.fetchone()

            if catalog:
                image_tag          = catalog.image_tag
                sdk_version        = catalog.sdk_version
                cli_version        = catalog.cli_version
                devnet_version     = catalog.devnet_version
                contracts_version  = catalog.contracts_version
                node_major         = catalog.node_major_version or _major(tag_name)
            else:
                # Catalog not yet populated (race between poller and consumer)
                # Fall back to local derivation without an API call
                node_major        = _major(tag_name)
                sdk_version       = None
                cli_version       = None
                devnet_version    = None
                contracts_version = None
                image_tag         = derive_image_tag(tag_name, sdk_version)
                log.warning(
                    "Release %s not found in catalog — using fallback image_tag %s",
                    tag_name, image_tag,
                )

            run_id = str(uuid.uuid4())
            now    = datetime.now(tz=timezone.utc)

            await db.execute(
                text("""
                    INSERT INTO orchestrator.runs
                        (id, release_tag, image_tag, status, priority,
                         triggered_by, queued_at)
                    VALUES
                        (:id, :release_tag, :image_tag, 'queued', 9,
                         'github_release', :now)
                """),
                {"id": run_id, "release_tag": tag_name,
                 "image_tag": image_tag, "now": now},
            )
            await db.execute(
                text("""
                    INSERT INTO orchestrator.run_events
                        (id, run_id, event_type, payload, ts)
                    VALUES
                        (:eid, :run_id, 'run.queued', CAST(:payload AS jsonb), :ts)
                """),
                {
                    "eid":     str(uuid.uuid4()),
                    "run_id":  run_id,
                    "payload": json.dumps({
                        "release_tag":        tag_name,
                        "source":             "github-watcher",
                        "html_url":           html_url,
                        "sdk_version":        sdk_version,
                        "cli_version":        cli_version,
                        "devnet_version":     devnet_version,
                        "contracts_version":  contracts_version,
                        "node_major_version": node_major,
                    }),
                    "ts": now,
                },
            )
            await db.commit()
            log.info(
                "Created run record %s for release %s (node_major=%d sdk=%s cli=%s devnet=%s contracts=%s)",
                run_id, tag_name, node_major, sdk_version, cli_version,
                devnet_version, contracts_version,
            )

        # Publish sandbox request AFTER the run record is committed
        await publish_sandbox_request(
            run_id=run_id,
            release_tag=tag_name,
            image_tag=image_tag,
            priority=9,
            requested_by="github-watcher",
            sdk_version=sdk_version,
            cli_version=cli_version,
            devnet_version=devnet_version,
            contracts_version=contracts_version,
            node_major_version=node_major,
        )
        log.info("Published sandbox request for run %s (release %s)", run_id, tag_name)

    async def stop(self):
        if self._connection:
            await self._connection.close()
