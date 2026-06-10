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
from publishers.notifications import publish_notification, publish_live

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

        # Broadcast immediately so the dashboard streams tests in real-time
        # without waiting for the whole run to finish.
        await publish_live({
            "event_type":    "test.result",
            "run_id":        run_id,
            "definition_slug": slug,
            "status":        msg.get("status"),
        })

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

            # Compute overall pass rate
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
                    RETURNING id, release_tag, triggered_by, triggered_by_user,
                              started_at, completed_at,
                              EXTRACT(EPOCH FROM (NOW() - started_at))::int AS duration_seconds
                """),
                {"status": final, "rate": rate,
                 "ts": datetime.now(tz=timezone.utc), "id": run_id},
            )
            updated = result.fetchone()
            if not updated:
                await db.commit()
                return  # concurrent result already closed — skip expensive queries

            # Collect per-phase stats and failing test details for the notification
            phase_rows = await db.execute(
                text("""
                    SELECT
                      COALESCE(d.phase, 'Uncategorised') AS phase,
                      COUNT(*)                                                   AS total,
                      COUNT(*) FILTER (WHERE res.status = 'passed')             AS passed,
                      COUNT(*) FILTER (WHERE res.status NOT IN ('passed','running','pending')) AS failed
                    FROM tests.results res
                    JOIN tests.definitions d ON d.id = res.definition_id
                    WHERE res.run_id = :run_id
                    GROUP BY d.phase
                    ORDER BY d.phase NULLS LAST
                """),
                {"run_id": run_id},
            )
            phases_data = []
            for pr in phase_rows:
                ph_rate = (pr.passed / pr.total * 100) if pr.total else 0.0
                phases_data.append({
                    "phase":     pr.phase,
                    "total":     pr.total,
                    "passed":    pr.passed,
                    "failed":    pr.failed,
                    "pass_rate": round(ph_rate, 1),
                })

            # Top failing tests with error messages
            fail_rows = await db.execute(
                text("""
                    SELECT d.name, res.status, res.error_message
                    FROM tests.results res
                    JOIN tests.definitions d ON d.id = res.definition_id
                    WHERE res.run_id = :run_id
                      AND res.status NOT IN ('passed', 'running', 'pending')
                    ORDER BY res.completed_at
                    LIMIT 5
                """),
                {"run_id": run_id},
            )
            failed_tests = [
                {"name": fr.name, "status": fr.status,
                 "error": (fr.error_message or "")[:200]}
                for fr in fail_rows
            ]

            await db.commit()

        log.info("Run %s → %s (pass_rate=%.1f%%)", run_id, final, rate)
        await publish_notification(
            f"run.{final}", f"Run {final}",
            run_id=run_id,
            pass_rate=rate,
            release_tag=updated.release_tag,
            triggered_by=updated.triggered_by,
            triggered_by_user=updated.triggered_by_user,
            duration_seconds=updated.duration_seconds,
            total_tests=row.total,
            passed_tests=row.passed,
            failed_tests=len(failed_tests),
            phases=phases_data,
            top_failures=failed_tests,
            is_success=(final == "completed"),
            is_warning=(final == "warning"),
            is_error=(final == "failed"),
        )

    async def stop(self):
        if self._connection:
            await self._connection.close()
