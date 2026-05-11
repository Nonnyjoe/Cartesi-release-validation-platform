"""
services/orchestrator/publishers/notifications.py
Publishes NotificationMessage to rvp.notify (fanout) and also pushes to Redis pub/sub.
"""
import json
import logging
import os
from datetime import datetime, timezone

import aio_pika
import redis.asyncio as aioredis

log = logging.getLogger("orchestrator.pub.notify")
RABBITMQ_URL   = os.environ.get("RABBITMQ_URL", "amqp://rvp:changeme@localhost:5672/")
REDIS_URL      = os.environ.get("REDIS_URL", "redis://localhost:6379")
PUBSUB_CHANNEL = "rvp:live"


async def publish_notification(event_type: str, title: str, run_id: str | None = None, **fields):
    payload = {
        "event_id":   __import__("uuid").uuid4().__str__(),
        "run_id":     run_id,
        "service":    "orchestrator",
        "ts":         datetime.now(tz=timezone.utc).isoformat(),
        "event_type": event_type,
        "title":      title,
        "fields":     fields,
    }
    body = json.dumps(payload).encode()

    # RabbitMQ fanout
    conn = await aio_pika.connect_robust(RABBITMQ_URL)
    async with conn:
        ch = await conn.channel()
        exchange = await ch.get_exchange("rvp.notify")
        await exchange.publish(
            aio_pika.Message(body=body, content_type="application/json",
                             delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key="",
        )

    # Redis pub/sub for live dashboard
    redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    await redis.publish(PUBSUB_CHANNEL, json.dumps(payload))
    await redis.aclose()
