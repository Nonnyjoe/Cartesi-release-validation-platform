"""
services/orchestrator/publishers/notifications.py
Publishes NotificationMessage to rvp.notify (fanout) and pushes to Redis pub/sub.

Uses a module-level singleton Redis client to avoid creating a new connection
pool on every notification call (which would leak connections under load).
"""
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import aio_pika
import redis.asyncio as aioredis

log = logging.getLogger("orchestrator.pub.notify")
RABBITMQ_URL   = os.environ.get("RABBITMQ_URL", "amqp://rvp:changeme@localhost:5672/")
REDIS_URL      = os.environ.get("REDIS_URL", "redis://localhost:6379")
PUBSUB_CHANNEL = "rvp:live"

# Singleton Redis client — created once, reused for all publish calls
_redis_client: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


async def publish_notification(event_type: str, title: str, run_id: str | None = None, **fields):
    payload = {
        "event_id":   str(uuid.uuid4()),
        "run_id":     run_id,
        "service":    "orchestrator",
        "ts":         datetime.now(tz=timezone.utc).isoformat(),
        "event_type": event_type,
        "title":      title,
        "fields":     fields,
    }
    body = json.dumps(payload).encode()

    # RabbitMQ fanout → notify.discord (and any other notification subscribers)
    try:
        conn = await aio_pika.connect_robust(RABBITMQ_URL)
        async with conn:
            ch = await conn.channel()
            exchange = await ch.get_exchange("rvp.notify")
            await exchange.publish(
                aio_pika.Message(body=body, content_type="application/json",
                                 delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                routing_key="",
            )
    except Exception as exc:
        log.error("RabbitMQ notification publish failed: %s", exc)

    # Redis pub/sub → live dashboard via WebSocket relay
    try:
        await _get_redis().publish(PUBSUB_CHANNEL, json.dumps(payload))
    except Exception as exc:
        log.error("Redis notification publish failed: %s", exc)
        # Reset client so the next call re-creates it (handles Redis restarts)
        global _redis_client
        _redis_client = None
