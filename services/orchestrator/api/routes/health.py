"""
GET /healthz — deep health check: DB ping + RabbitMQ ping
GET /metrics  — Prometheus-compatible text metrics
"""
import os
import time
from datetime import datetime, timezone

import aio_pika
import httpx
from fastapi import APIRouter
from sqlalchemy import text

from db import engine

router = APIRouter(tags=["health"])

RABBITMQ_URL  = os.getenv("RABBITMQ_URL", "amqp://rvp:rvp_secret@rabbitmq:5672/rvp")
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
RABBITMQ_MGMT = os.getenv("RABBITMQ_MGMT_PORT", "15672")
RABBITMQ_USER = os.getenv("RABBITMQ_USER", "rvp")
RABBITMQ_PASS = os.getenv("RABBITMQ_PASS", "rvp_secret")

_start_time = time.time()


@router.get("/healthz")
async def healthz():
    checks: dict = {}
    healthy = True

    # ── DB check ──────────────────────────────────────────────────────────────
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        healthy = False

    # ── RabbitMQ check ────────────────────────────────────────────────────────
    try:
        conn = await aio_pika.connect(RABBITMQ_URL, timeout=3)
        await conn.close()
        checks["rabbitmq"] = "ok"
    except Exception as e:
        checks["rabbitmq"] = f"error: {e}"
        healthy = False

    return {
        "status": "ok" if healthy else "degraded",
        "service": "orchestrator",
        "uptime_seconds": round(time.time() - _start_time),
        "checks": checks,
        "ts": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/metrics")
async def metrics():
    """Prometheus text-format metrics."""
    lines: list[str] = []

    def gauge(name: str, value: float, help_text: str = ""):
        if help_text:
            lines.append(f"# HELP {name} {help_text}")
            lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {value}")

    uptime = round(time.time() - _start_time)
    gauge("rvp_uptime_seconds", uptime, "Orchestrator uptime in seconds")

    # Run counts by status
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT status, COUNT(*) FROM orchestrator.runs GROUP BY status")
            )
            for row in result.fetchall():
                gauge(
                    f'rvp_runs_total{{status="{row[0]}"}}',
                    float(row[1]),
                    "Total runs by status" if row[0] == "pending" else "",
                )

            # Active sandboxes
            sb_result = await conn.execute(
                text("SELECT COUNT(*) FROM sandbox.sandboxes WHERE status IN ('ready','in_use','provisioning')")
            )
            gauge("rvp_active_sandboxes", float(sb_result.scalar() or 0), "Active sandbox count")

            # AI sessions
            sess_result = await conn.execute(
                text("SELECT COUNT(*) FROM ai.sessions WHERE status = 'active'")
            )
            gauge("rvp_active_ai_sessions", float(sess_result.scalar() or 0), "Active AI sessions")
    except Exception:
        pass

    # RabbitMQ queue depths via management API
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get(
                f"http://{RABBITMQ_HOST}:{RABBITMQ_MGMT}/api/queues/rvp",
                auth=(RABBITMQ_USER, RABBITMQ_PASS),
            )
            if resp.status_code == 200:
                lines.append("# HELP rvp_queue_depth RabbitMQ queue message depth")
                lines.append("# TYPE rvp_queue_depth gauge")
                for q in resp.json():
                    name = q.get("name", "").replace(".", "_")
                    lines.append(f'rvp_queue_depth{{queue="{q["name"]}"}} {q.get("messages", 0)}')
    except Exception:
        pass

    return "\n".join(lines) + "\n"
