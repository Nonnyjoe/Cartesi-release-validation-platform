"""
services/notifier/discord.py

Sends Discord embeds to a webhook URL with:
  - 3× retry with exponential backoff on transient failures
  - Automatic handling of Discord rate limit (HTTP 429, Retry-After)
  - Delivery logging to `notifications.deliveries` table
"""
import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy import text

log = logging.getLogger("notifier.discord")

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://rvp_notifier:rvp_secret@postgres:5432/rvp")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
MAX_RETRIES = 3

engine = create_async_engine(DATABASE_URL, echo=False)


async def _log_delivery(
    event_type: str,
    run_id: str | None,
    status: str,
    error: str | None = None,
):
    """Persist a delivery attempt record to notifications.deliveries."""
    async with AsyncSession(engine) as session:
        try:
            await session.execute(
                text("""
                    INSERT INTO notifications.deliveries
                        (delivery_id, event_type, run_id, channel, status, error, delivered_at)
                    VALUES
                        (:id, :event_type, :run_id, 'discord', :status, :error, :now)
                """),
                {
                    "id": str(uuid.uuid4()),
                    "event_type": event_type,
                    "run_id": run_id,
                    "status": status,
                    "error": error,
                    "now": datetime.now(timezone.utc),
                },
            )
            await session.commit()
        except Exception as e:
            log.warning("Failed to log delivery: %s", e)


async def send_embed(
    embeds: list[dict],
    event_type: str = "unknown",
    run_id: str | None = None,
    webhook_url: str | None = None,
) -> bool:
    """
    POST embeds to a Discord webhook.

    Returns True on success, False after all retries are exhausted.
    """
    url = webhook_url or DISCORD_WEBHOOK_URL
    if not url:
        log.warning("DISCORD_WEBHOOK_URL not set — skipping notification")
        return False

    payload = {"embeds": embeds[:10]}  # Discord max 10 embeds per message

    async with httpx.AsyncClient(timeout=15) as client:
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                resp = await client.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )

                # Discord rate limit
                if resp.status_code == 429:
                    retry_after = float(resp.json().get("retry_after", 1.0))
                    log.warning(
                        "Discord rate limited — waiting %.1fs (attempt %d/%d)",
                        retry_after, attempt, MAX_RETRIES,
                    )
                    await asyncio.sleep(retry_after)
                    continue

                # Success
                if resp.status_code in (200, 204):
                    log.info("Discord embed sent (%s)", event_type)
                    await _log_delivery(event_type, run_id, "delivered")
                    return True

                # Non-retryable client error
                if 400 <= resp.status_code < 500:
                    log.error(
                        "Discord rejected embed (%s): %s %s",
                        event_type, resp.status_code, resp.text[:200],
                    )
                    await _log_delivery(event_type, run_id, "failed", resp.text[:500])
                    return False

                # 5xx — retry
                log.warning(
                    "Discord server error %s (attempt %d/%d)",
                    resp.status_code, attempt, MAX_RETRIES,
                )

            except httpx.TransportError as e:
                log.warning("Discord transport error (attempt %d/%d): %s", attempt, MAX_RETRIES, e)

            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 ** attempt)

    log.error("Discord delivery failed after %d attempts (%s)", MAX_RETRIES, event_type)
    await _log_delivery(event_type, run_id, "failed", "max retries exceeded")
    return False
