"""
Thin publisher: sends messages to the AI agent queue via RabbitMQ.
Used by the /sessions route to kick off or inject messages into sessions.
"""
import json, os
import aio_pika
from constants import Exchange, RoutingKey, Queue

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://rvp:rvp_secret@rabbitmq:5672/rvp")


class AIPublisher:
    async def _connect(self):
        conn = await aio_pika.connect_robust(RABBITMQ_URL)
        channel = await conn.channel()
        return conn, channel

    async def publish_session_request(self, payload: dict):
        conn, channel = await self._connect()
        exchange = await channel.get_exchange(Exchange.AI)
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload).encode(),
                content_type="application/json",
            ),
            routing_key=RoutingKey.AI_REQUESTS,
        )
        await conn.close()

    async def publish_user_message(self, session_id: str, message: str):
        # Routed via the existing ai.requests queue (rvp.ai is a DIRECT exchange,
        # so per-session routing keys would never reach a consumer). The ai-agent
        # consumer recognises type=user_message and dispatches to the live session.
        conn, channel = await self._connect()
        exchange = await channel.get_exchange(Exchange.AI)
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps({
                    "type": "user_message",
                    "session_id": session_id,
                    "message": message,
                }).encode(),
                content_type="application/json",
            ),
            routing_key=RoutingKey.AI_REQUESTS,
        )
        await conn.close()
