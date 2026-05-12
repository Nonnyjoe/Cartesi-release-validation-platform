"""
services/github-watcher/webhook_handler.py

FastAPI app running on port 8001 (internal network only).
Handles GitHub webhook `release` events as a faster trigger path
than polling (immediate vs every POLL_INTERVAL_SECONDS).

Validates X-Hub-Signature-256 HMAC before processing.
"""
import hashlib
import hmac
import json
import logging
import os

import aio_pika
from fastapi import FastAPI, HTTPException, Request, Header
from typing import Optional

from poller import process_release

log = logging.getLogger("github-watcher.webhook")

WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://rvp:rvp_secret@rabbitmq:5672/rvp")

app = FastAPI(title="GitHub Watcher — Webhook Handler", version="0.1.0")

_connection: aio_pika.Connection | None = None


async def get_connection() -> aio_pika.Connection:
    global _connection
    if _connection is None or _connection.is_closed:
        _connection = await aio_pika.connect_robust(RABBITMQ_URL)
    return _connection


def _verify_signature(body: bytes, signature: str) -> bool:
    if not WEBHOOK_SECRET:
        log.warning("GITHUB_WEBHOOK_SECRET not set — skipping signature verification")
        return True
    expected = "sha256=" + hmac.new(
        WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
):
    body = await request.body()

    # Signature check
    if not x_hub_signature_256:
        raise HTTPException(401, "Missing X-Hub-Signature-256 header")
    if not _verify_signature(body, x_hub_signature_256):
        raise HTTPException(403, "Invalid signature")

    # Only handle `release` events with action `published`
    if x_github_event != "release":
        return {"ok": True, "action": "ignored", "reason": f"event={x_github_event}"}

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON payload")

    action = payload.get("action")
    if action != "published":
        return {"ok": True, "action": "ignored", "reason": f"action={action}"}

    release = payload.get("release", {})
    tag = release.get("tag_name")
    if not tag:
        raise HTTPException(422, "Missing tag_name in release payload")

    log.info("Webhook: new release published — %s", tag)

    conn = await get_connection()
    await process_release(release, conn)

    return {"ok": True, "action": "processed", "tag": tag}


@app.get("/healthz")
async def health():
    return {"status": "ok", "service": "github-watcher"}
