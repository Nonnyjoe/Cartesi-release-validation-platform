"""
services/ai-agent/consumers/session_requests.py
Consumes ai.requests queue — starts AI sessions based on AISessionRequest messages.
"""
import asyncio
import json
import logging
import os

import aio_pika

from session_manager import SessionManager
from publishers.session_events import publish_session_event

log = logging.getLogger("ai-agent.consumer.session_requests")
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://rvp:changeme@localhost:5672/")


class SessionRequestConsumer:
    def __init__(self):
        self._connection = None
        self._channel = None
        # Active interactive/collaborative sessions: session_id → Queue
        self._message_queues: dict[str, asyncio.Queue] = {}

    async def start(self):
        self._connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=5)

    async def run(self):
        queue = await self._channel.get_queue("ai.requests")
        log.info("AI Agent consuming ai.requests...")
        async with queue.iterator() as q:
            async for message in q:
                async with message.process():
                    try:
                        await self._handle(json.loads(message.body))
                    except Exception as exc:
                        log.exception("Error handling session request: %s", exc)

    async def _handle(self, msg: dict):
        # Mid-session user message (collaborative/interactive) — not a new session.
        if msg.get("type") == "user_message":
            await self.send_user_message(msg.get("session_id", ""), msg.get("message", ""))
            return

        mode = msg.get("mode", "autonomous")
        log.info("AI session request: mode=%s  release=%s", mode, msg.get("release_tag"))

        def publish(event: dict):
            asyncio.create_task(publish_session_event(event))

        manager = SessionManager(msg, publish)

        if mode == "autonomous":
            asyncio.create_task(manager.run_autonomous())

        elif mode in ("collaborative", "interactive"):
            q: asyncio.Queue = asyncio.Queue()
            self._message_queues[manager.session_id] = q

            async def _run_and_cleanup(coro):
                try:
                    await coro
                finally:
                    self._message_queues.pop(manager.session_id, None)

            if mode == "collaborative":
                asyncio.create_task(_run_and_cleanup(manager.run_collaborative(q)))
            else:
                asyncio.create_task(_run_and_cleanup(manager.run_interactive(q)))

    async def send_user_message(self, session_id: str, message: str):
        """Called by the orchestrator WebSocket to inject user messages into a live session."""
        q = self._message_queues.get(session_id)
        if q:
            await q.put(message)
        else:
            log.warning("No active session found for session_id=%s", session_id)

    async def stop(self):
        for q in self._message_queues.values():
            await q.put("__done__")
        if self._connection:
            await self._connection.close()
