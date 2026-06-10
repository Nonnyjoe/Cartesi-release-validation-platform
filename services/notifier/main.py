"""
services/notifier/main.py

Consumes RabbitMQ notification queues and dispatches Discord embeds.

Queues consumed:
  notify.discord   — all events destined for Discord
  notify.dashboard — dashboard-only events (logged but not forwarded to Discord)

Message envelope (from shared.message_schemas.notification):
  {
    "event_type": "run.completed" | "run.failed" | "release.detected"
                | "ai.finding" | "run.queued",
    "run_id": "...",
    "payload": { ... }   ← event-specific data
  }
"""
import asyncio
import json
import logging
import os
from functools import partial

import aio_pika

from discord import send_embed
from formatters import (
    format_release_detected,
    format_run_queued,
    format_run_completed,
    format_run_failed,
    format_ai_finding,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
)
log = logging.getLogger("notifier")

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://rvp:rvp_secret@rabbitmq:5672/rvp")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")

def _fmt_run_completed(p: dict) -> list[dict]:
    # payload is the `fields` dict from publish_notification — it contains
    # pass_rate, phases, top_failures, etc. directly at the top level.
    return format_run_completed(p.get("run", p), p.get("report"))


FORMATTERS: dict = {
    "release.detected": format_release_detected,
    "run.queued":       format_run_queued,
    "run.completed":    _fmt_run_completed,
    "run.warning":      _fmt_run_completed,   # warning uses the same formatter
    "run.failed":       format_run_failed,
    "ai.finding":       format_ai_finding,
}


async def handle_discord_message(message: aio_pika.IncomingMessage):
    async with message.process(requeue=True):
        try:
            body = json.loads(message.body)
        except json.JSONDecodeError as e:
            log.error("Invalid JSON in notify.discord message: %s", e)
            return

        event_type = body.get("event_type", "unknown")
        run_id = body.get("run_id")
        payload = body.get("payload", body)

        log.info("Received %s (run=%s)", event_type, run_id)

        formatter = FORMATTERS.get(event_type)
        if not formatter:
            log.warning("No formatter for event_type=%s", event_type)
            return

        try:
            embeds = formatter(payload)
        except Exception as e:
            log.error("Formatter error (%s): %s", event_type, e, exc_info=True)
            return

        await send_embed(
            embeds=embeds,
            event_type=event_type,
            run_id=run_id,
            webhook_url=DISCORD_WEBHOOK_URL,
        )


async def main():
    log.info("Notifier starting up")

    connection = await aio_pika.connect_robust(RABBITMQ_URL)
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=5)

    discord_queue = await channel.get_queue("notify.discord")
    await discord_queue.consume(handle_discord_message)

    log.info("Notifier ready — consuming notify.discord")

    try:
        await asyncio.Future()  # run forever
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await connection.close()
        log.info("Notifier stopped")


if __name__ == "__main__":
    asyncio.run(main())
