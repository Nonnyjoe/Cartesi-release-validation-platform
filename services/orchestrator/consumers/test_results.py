"""
services/orchestrator/consumers/test_results.py
Consumes tests.results queue.
Aggregates results, updates run pass_rate, marks run completed/failed.
"""
import json
import logging
import os
from datetime import datetime, timezone

import aio_pika
from sqlalchemy import text

from db import AsyncSessionLocal
from publishers.notifications import publish_notification

log = logging.getLogger("orchestrator.consumer.test_results")
RABBITMQ_URL = os.environ.get("RABBITMQ_URL", "amqp://rvp:changeme@localhost:5672/")


class TestResultConsumer:
    def __init__(self):
        self._connection = None
        self._channel = None

    async def start(self):
        self._connection = await aio_pika.connect_robust(RABBITMQ_URL)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=20)

    async def run(self):
        queue = await self._channel.get_queue("tests.results")
        async with queue.iterator() as q:
            async for message in q:
                async with message.process():
                    try:
                        await self._handle(json.loads(message.body))
                    except Exception as exc:
                        log.exception("Error processing test result: %s", exc)

    async def _handle(self, msg: dict):
        run_id     = msg.get("run_id")
        status     = msg.get("status")
        slug       = msg.get("definition_slug")
        log.info("Test result: %s → %s  run=%s", slug, status, run_id)

        async with AsyncSessionLocal() as db:
            # Check if all tests for this run are done
            pending = await db.execute(
                text("""
                    SELECT COUNT(*) FROM tests.results
                    WHERE run_id = :run_id AND status IN ('pending', 'running')
                """),
                {"run_id": run_id},
            )
            remaining = pending.scalar()

            if remaining == 0:
                # Compute pass rate and mark run complete
                stats = await db.execute(
                    text("""
                        SELECT
                          COUNT(*) FILTER (WHERE status = 'passed') AS passed,
                          COUNT(*) AS total
                        FROM tests.results WHERE run_id = :run_id
                    """),
                    {"run_id": run_id},
                )
                row   = stats.fetchone()
                rate  = (row.passed / row.total * 100) if row.total else 0
                final = "completed" if rate == 100 else "failed"

                await db.execute(
                    text("""
                        UPDATE orchestrator.runs
                        SET status=:status, pass_rate=:rate, completed_at=:ts
                        WHERE id=:id
                    """),
                    {"status": final, "rate": rate,
                     "ts": datetime.now(tz=timezone.utc), "id": run_id},
                )
                await db.commit()
                await publish_notification(
                    f"run.{final}", f"Run {final}",
                    run_id=run_id, pass_rate=rate,
                    is_success=(final == "completed"), is_error=(final == "failed"),
                )

    async def stop(self):
        if self._connection:
            await self._connection.close()
