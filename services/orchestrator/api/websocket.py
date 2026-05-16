"""
services/orchestrator/api/websocket.py
WebSocket endpoint — streams live events to the dashboard via Redis pub/sub.

Channel routing:
  /ws            — global subscriber (receives all events)
  /ws?channel=<run_id> — receives events for that run + all global events

The Redis subscriber task is started in main.py's lifespan (not here) to avoid
the deprecated @router.on_event("startup") which does not fire when the app
uses a lifespan context manager.
"""
import asyncio
import json
import logging
import os

import redis.asyncio as aioredis
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

log = logging.getLogger("orchestrator.ws")
router = APIRouter()

REDIS_URL      = os.environ.get("REDIS_URL", "redis://localhost:6379")
PUBSUB_CHANNEL = "rvp:live"


class ConnectionManager:
    """
    Channel-aware WebSocket manager.
    - Connections with no channel go into the None bucket (global).
    - On broadcast, events are sent to global subscribers + any channel-specific
      subscribers whose channel matches the event's run_id field.
    """

    def __init__(self):
        # channel (str|None) → list of WebSocket connections
        self._connections: dict[str | None, list[WebSocket]] = {None: []}
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, channel: str | None = None):
        await ws.accept()
        async with self._lock:
            if channel not in self._connections:
                self._connections[channel] = []
            self._connections[channel].append(ws)
        log.debug("WS connected  channel=%s  total_channels=%d", channel, len(self._connections))

    async def disconnect(self, ws: WebSocket, channel: str | None = None):
        async with self._lock:
            bucket = self._connections.get(channel, [])
            try:
                bucket.remove(ws)
            except ValueError:
                pass
            # Clean up empty non-global buckets
            if channel is not None and not bucket:
                self._connections.pop(channel, None)

    async def broadcast(self, message: str):
        """Send message to global subscribers + any channel matching the event's run_id."""
        try:
            run_id = json.loads(message).get("run_id")
        except Exception:
            run_id = None

        # Snapshot the target connections under the lock, then send outside it
        async with self._lock:
            targets: list[WebSocket] = list(self._connections.get(None, []))
            if run_id and run_id in self._connections:
                for ws in self._connections[run_id]:
                    if ws not in targets:
                        targets.append(ws)

        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    for bucket in self._connections.values():
                        try:
                            bucket.remove(ws)
                        except ValueError:
                            pass


manager = ConnectionManager()


async def redis_subscriber():
    """
    Background task: subscribe to Redis and broadcast to all WS clients.
    Started by main.py's lifespan — NOT by @router.on_event("startup").
    """
    client = aioredis.from_url(REDIS_URL, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(PUBSUB_CHANNEL)
    log.info("WebSocket relay: subscribed to Redis channel '%s'", PUBSUB_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message["type"] == "message":
                await manager.broadcast(message["data"])
    except asyncio.CancelledError:
        log.info("WebSocket Redis subscriber cancelled")
        raise
    finally:
        await pubsub.unsubscribe(PUBSUB_CHANNEL)
        await client.aclose()


@router.websocket("")
async def websocket_endpoint(ws: WebSocket):
    channel = ws.query_params.get("channel")  # e.g. a run_id
    await manager.connect(ws, channel)
    try:
        while True:
            # Keep alive — all data arrives via Redis broadcast
            await asyncio.sleep(30)
            await ws.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        await manager.disconnect(ws, channel)
    except Exception as exc:
        log.warning("WebSocket error: %s", exc)
        await manager.disconnect(ws, channel)
