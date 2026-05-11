"""
services/orchestrator/api/websocket.py
WebSocket endpoint that streams live run/sandbox/test events to the dashboard.
Subscribes to Redis pub/sub channel "rvp:live" and fans out to all connected clients.
"""
import asyncio
import json
import logging
import os

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger("orchestrator.ws")
router = APIRouter()

REDIS_URL     = os.environ.get("REDIS_URL", "redis://localhost:6379")
PUBSUB_CHANNEL = "rvp:live"


class ConnectionManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)

    def disconnect(self, ws: WebSocket):
        self._connections.remove(ws)

    async def broadcast(self, message: str):
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)


manager = ConnectionManager()
_redis_subscriber_task: asyncio.Task | None = None


async def _redis_subscriber():
    """Background task: subscribe to Redis and broadcast to all WS clients."""
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(PUBSUB_CHANNEL)
    log.info("WebSocket relay: subscribed to Redis channel '%s'", PUBSUB_CHANNEL)
    async for message in pubsub.listen():
        if message["type"] == "message":
            await manager.broadcast(message["data"])


@router.websocket("")
async def websocket_endpoint(ws: WebSocket):
    await manager.connect(ws)
    try:
        while True:
            # Keep connection alive; all data comes via Redis broadcast
            await asyncio.sleep(30)
            await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception as exc:
        log.warning("WebSocket error: %s", exc)
        manager.disconnect(ws)


@router.on_event("startup")
async def start_redis_subscriber():
    global _redis_subscriber_task
    _redis_subscriber_task = asyncio.create_task(_redis_subscriber())
