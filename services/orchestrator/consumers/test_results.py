"""
services/orchestrator/consumers/test_results.py
Consumes tests.results queue.
Aggregates results, updates run pass_rate, marks run completed/warning/failed.

Thresholds (env-configurable):
  PASS_THRESHOLD_COMPLETED  — min pass rate for 'completed'  (default 100.0)
  PASS_THRESHOLD_WARNING    — min pass rate for 'warning'    (default 80.0)
  Below WARNING threshold   → 'failed'
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

PASS_THRESHOLD_COMPLETED = float(os.environ.get("PASS_THRESHOLD_COMPLETED", "100.0"))
PASS_THRESHOLD_WARNING   = float(os.environ.get("PASS_THRESHOLD_WARNING",   "80.0"))


def _final_status(rate: float) -> str:
    if rate >= PASS_THRESHOLD_COMPLETED:
        return "completed"
    if rate >= PASS_THRESHOLD_WARNING:
        return "warning"
    return "failed"


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
        run_id = msg.get("run_id")
        slug   = msg.get("definition_slug")
        log.info("Test result: %s → %s  run=%s", slug, msg.get("status"), run_id)

        async with AsyncSessionLocal() as db:
            # Compare completed results against the dispatched count from run metadata.
            # Tests are processed sequentially by the test-runner, so later tests may
            # not yet have a results row when an early result arrives — checking only
            # for 'pending'/'running' rows would prematurely close the run.
            counts = await db.execute(
                text("""
                    SELECT
                      COALESCE((r.metadata->>'dispatched_count')::int, 0) AS dispatched,
                      COUNT(res.id) FILTER (WHERE res.status NOT IN ('running', 'pending')) AS finished,
                      COUNT(res.id) FILTER (WHERE res.status IN ('running', 'pending'))     AS in_flight
                    FROM orchestrator.runs r
                    LEFT JOIN tests.results res ON res.run_id = r.id
                    WHERE r.id = :run_id
                    GROUP BY r.metadata
                """),
                {"run_id": run_id},
            )
            row_c = counts.fetchone()
            if not row_c:
                return
            dispatched = row_c.dispatched
            finished   = row_c.finished
            in_flight  = row_c.in_flight

            if dispatched == 0 or in_flight > 0 or finished < dispatched:
                return  # dispatched_count not yet written, or tests still running/pending

            # Compute pass rate
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
            rate  = (row.passed / row.total * 100) if row.total else 0.0
            final = _final_status(rate)

            # Atomic transition: only act if the run is currently 'running'.
            # This prevents double-completion when results arrive concurrently.
            result = await db.execute(
                text("""
                    UPDATE orchestrator.runs
                    SET status=:status, pass_rate=:rate, completed_at=:ts
                    WHERE id=:id AND status = 'running'
                    RETURNING id
                """),
                {"status": final, "rate": rate,
                 "ts": datetime.now(tz=timezone.utc), "id": run_id},
            )
            updated = result.fetchone()
            await db.commit()

        if not updated:
            # Another concurrent result already closed this run — do nothing
            log.debug("Run %s already transitioned (concurrent result) — skipping notification", run_id)
            return

        log.info("Run %s → %s (pass_rate=%.1f%%)", run_id, final, rate)
        await publish_notification(
            f"run.{final}", f"Run {final}",
            run_id=run_id, pass_rate=rate,
            is_success=(final == "completed"),
            is_warning=(final == "warning"),
            is_error=(final == "failed"),
        )

    async def stop(self):
        if self._connection:
            await self._connection.close()
