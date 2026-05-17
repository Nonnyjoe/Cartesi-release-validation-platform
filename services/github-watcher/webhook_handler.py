"""
services/github-watcher/webhook_handler.py

FastAPI app running on port 8001 (internal network only).
Handles GitHub webhook `release` events as a faster trigger path
than polling (immediate vs every POLL_INTERVAL_SECONDS).

Supported sources
-----------------
  cartesi/rollups-node   → GITHUB_REPO
    Triggers a full run pipeline: catalog upsert + release event publish.

  cartesi/cli            → CLI_GITHUB_REPO
    Upserts the CLI toolchain chain (sdk/devnet/contracts) and backfills
    release_catalog.cli_tag for the referenced rollups-node version.
    If that node has never been run, a release event is published so the
    orchestrator can kick off a properly-toolchained run.

Webhook secrets
---------------
  GITHUB_WEBHOOK_SECRET      — shared secret for rollups-node repo webhook.
  CLI_GITHUB_WEBHOOK_SECRET  — shared secret for CLI repo webhook.
    If CLI_GITHUB_WEBHOOK_SECRET is not set, falls back to GITHUB_WEBHOOK_SECRET.
    If neither is set, signature verification is skipped with a warning.

Both repos can point to the same /webhook endpoint or use separate ones
(/webhook and /webhook/cli) — GitHub identifies the source via the
`repository.full_name` field in the payload body.
"""
import hashlib
import hmac as hmac_mod
import json
import logging
import os

import aio_pika
from fastapi import FastAPI, HTTPException, Request, Header
from typing import Optional

from poller import (
    CLI_GITHUB_REPO,
    GITHUB_REPO,
    RABBITMQ_URL,
    _is_cli_already_processed,
    process_release,
    process_cli_release,
)

log = logging.getLogger("github-watcher.webhook")

WEBHOOK_SECRET     = os.getenv("GITHUB_WEBHOOK_SECRET", "")
CLI_WEBHOOK_SECRET = os.getenv("CLI_GITHUB_WEBHOOK_SECRET", "") or WEBHOOK_SECRET

app = FastAPI(title="GitHub Watcher — Webhook Handler", version="0.2.0")

_connection: aio_pika.Connection | None = None


async def get_connection() -> aio_pika.Connection:
    global _connection
    if _connection is None or _connection.is_closed:
        _connection = await aio_pika.connect_robust(RABBITMQ_URL)
    return _connection


def _verify_signature(body: bytes, signature: str, secret: str) -> bool:
    if not secret:
        log.warning("Webhook secret not set — skipping signature verification")
        return True
    expected = "sha256=" + hmac_mod.new(
        secret.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac_mod.compare_digest(expected, signature)


async def _handle_release_payload(
    body_bytes: bytes,
    payload: dict,
    signature: str,
) -> dict:
    """
    Route a parsed release webhook payload to the correct handler based on
    which repository sent it (determined from payload["repository"]["full_name"]).

    Returns a response dict suitable for returning directly from the endpoint.
    """
    repo_full_name: str = payload.get("repository", {}).get("full_name", "")
    release = payload.get("release", {})
    tag = release.get("tag_name", "")
    if not tag:
        raise HTTPException(422, "Missing tag_name in release payload")

    conn = await get_connection()

    # ── rollups-node webhook ──────────────────────────────────────────────────
    if repo_full_name == GITHUB_REPO or repo_full_name == "":
        if not _verify_signature(body_bytes, signature, WEBHOOK_SECRET):
            raise HTTPException(403, "Invalid signature")
        log.info("Webhook (node): new release published — %s", tag)
        await process_release(release, conn)
        return {"ok": True, "action": "processed", "source": "node", "tag": tag}

    # ── CLI repo webhook ──────────────────────────────────────────────────────
    if repo_full_name == CLI_GITHUB_REPO:
        if not _verify_signature(body_bytes, signature, CLI_WEBHOOK_SECRET):
            raise HTTPException(403, "Invalid CLI webhook signature")

        # Only process CLI releases (v2.x.x); ignore SDK tags (v0.x.x)
        try:
            major = int(tag.lstrip("v").split(".")[0])
        except (ValueError, IndexError):
            major = 0

        if major < 2:
            log.debug("Webhook (cli): ignoring SDK tag %s (not a CLI release)", tag)
            return {"ok": True, "action": "ignored", "reason": f"sdk_tag={tag}"}

        if await _is_cli_already_processed(tag):
            log.info("Webhook (cli): CLI %s already in catalog — skipping", tag)
            return {"ok": True, "action": "ignored", "reason": "already_processed"}

        log.info("Webhook (cli): new CLI release — %s", tag)
        await process_cli_release(release, conn)
        return {"ok": True, "action": "processed", "source": "cli", "tag": tag}

    log.warning("Webhook: unknown repository %r — ignoring", repo_full_name)
    return {"ok": True, "action": "ignored", "reason": f"unknown_repo={repo_full_name}"}


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.post("/webhook")
async def github_webhook(
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None),
    x_github_event: Optional[str] = Header(None),
):
    """
    Single entry point for webhooks from both cartesi/rollups-node and
    cartesi/cli.  The repository is identified from the payload body, so
    both repos can point here without requiring separate endpoints.
    """
    body_bytes = await request.body()

    if not x_hub_signature_256:
        raise HTTPException(401, "Missing X-Hub-Signature-256 header")

    if x_github_event != "release":
        return {"ok": True, "action": "ignored", "reason": f"event={x_github_event}"}

    try:
        payload = json.loads(body_bytes)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON payload")

    action = payload.get("action")
    if action != "published":
        return {"ok": True, "action": "ignored", "reason": f"action={action}"}

    return await _handle_release_payload(body_bytes, payload, x_hub_signature_256)


@app.get("/healthz")
async def health():
    return {"status": "ok", "service": "github-watcher"}
