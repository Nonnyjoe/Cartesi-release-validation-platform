"""
services/ai-agent/publishers/session_events.py
Publishes AISessionEvent messages to rvp.ai → ai.results
and also pushes to Redis pub/sub for live dashboard streaming.
"""
import json
import logging
import os

import aio_pika
import redis.asyncio as aioredis

log = logging.getLogger("ai-agent.publisher")

RABBITMQ_URL   = os.environ.get("RABBITMQ_URL", "amqp://rvp:changeme@localhost:5672/")
REDIS_URL      = os.environ.get("REDIS_URL", "redis://localhost:6379")
PUBSUB_CHANNEL = "rvp:live"

_mq_connection = None


async def _get_connection():
    global _mq_connection
    if _mq_connection is None or _mq_connection.is_closed:
        _mq_connection = await aio_pika.connect_robust(RABBITMQ_URL)
    return _mq_connection


async def publish_session_event(event: dict):
    """
    Publish a session event to:
    1. rvp.ai → ai.results (RabbitMQ, durable)
    2. rvp:live (Redis pub/sub, for WebSocket dashboard relay)
    """
    body = json.dumps(event).encode()

    # RabbitMQ
    try:
        conn = await _get_connection()
        channel = await conn.channel()
        exchange = await channel.get_exchange("rvp.ai")
        await exchange.publish(
            aio_pika.Message(
                body=body,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key="ai.results",
        )
    except Exception as exc:
        log.warning("Failed to publish to RabbitMQ: %s", exc)

    # Redis pub/sub (best-effort — dashboard live stream)
    try:
        redis = aioredis.from_url(REDIS_URL, decode_responses=True)
        await redis.publish(PUBSUB_CHANNEL, json.dumps(event))
        await redis.aclose()
    except Exception as exc:
        log.warning("Failed to publish to Redis: %s", exc)
