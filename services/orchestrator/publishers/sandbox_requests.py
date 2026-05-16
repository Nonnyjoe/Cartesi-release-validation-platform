"""
services/orchestrator/publishers/sandbox_requests.py
Publishes SandboxRequest messages to rvp.sandbox → sandbox.queue (priority queue).
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

import aio_pika

log = logging.getLogger("orchestrator.pub.sandbox")
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://rvp:changeme@localhost:5672/")


async def publish_sandbox_request(
    run_id:       str,
    release_tag:  str,
    image_tag:    str,
    priority:     int = 5,
    requested_by: Optional[str] = None,
    sdk_version:  Optional[str] = None,
    cli_version:  Optional[str] = None,
    devnet_version:    Optional[str] = None,
    contracts_version: Optional[str] = None,
    node_major_version: int = 1,
):
    """
    Publish a SandboxRequest to the sandbox.queue priority queue.

    sdk_version, cli_version, and node_major_version are used by the
    sandbox-manager to select the correct provisioning strategy and install
    the matching @cartesi/cli version in the sandbox:
      v1.x — single rollups-node container, no CLI container
      v2.x — 6-service SDK compose stack + cli-tools container with cli_version
    devnet_version and contracts_version are passed through for informational
    purposes and future use.
    """
    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    async with connection:
        channel  = await connection.channel()
        exchange = await channel.get_exchange("rvp.sandbox")

        body = json.dumps({
            "event_id":           str(uuid.uuid4()),
            "run_id":             run_id,
            "service":            "orchestrator",
            "ts":                 datetime.now(tz=timezone.utc).isoformat(),
            "release_tag":        release_tag,
            "image_tag":          image_tag,
            "sdk_version":        sdk_version,
            "cli_version":        cli_version,
            "devnet_version":     devnet_version,
            "contracts_version":  contracts_version,
            "node_major_version": node_major_version,
            "priority":           priority,
            "requested_by":       requested_by,
        }).encode()

        await exchange.publish(
            aio_pika.Message(
                body=body,
                content_type="application/json",
                priority=priority,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key="sandbox.queue",
        )
        log.info(
            "Published sandbox request for run %s (priority=%d, node_major=%d, cli=%s)",
            run_id, priority, node_major_version, cli_version,
        )
