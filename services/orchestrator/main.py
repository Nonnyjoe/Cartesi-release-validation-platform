"""
services/orchestrator/main.py
Central FastAPI application — runs, sandboxes, reports, and WebSocket live feed.
"""
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.runs import router as runs_router
from api.routes.releases import router as releases_router
from api.routes.sandboxes import router as sandboxes_router
from api.routes.reports import router as reports_router
from api.routes.tests import router as tests_router
from api.routes.sessions import router as sessions_router
from api.routes.queues import router as queues_router
from api.routes.health import router as health_router
from api.routes.apps import router as apps_router
from api.websocket import router as ws_router, redis_subscriber
from consumers.sandbox_events import SandboxEventConsumer
from consumers.test_results import TestResultConsumer
from consumers.releases import ReleasesConsumer
from db import engine, Base

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("orchestrator")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background consumers on boot, shut them down cleanly on exit."""
    log.info("Orchestrator starting up...")

    # Ensure DB tables exist (idempotent — init.sql already ran, this is for dev)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    sandbox_consumer  = SandboxEventConsumer()
    result_consumer   = TestResultConsumer()
    releases_consumer = ReleasesConsumer()

    await asyncio.gather(
        sandbox_consumer.start(),
        result_consumer.start(),
        releases_consumer.start(),
        return_exceptions=True,
    )

    async def _run_consumer(consumer, name: str):
        """Run a consumer indefinitely, restarting on crash. Never swallows CancelledError."""
        while True:
            try:
                await consumer.run()
                log.warning("Consumer %s exited normally — restarting", name)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("Consumer %s crashed (%s) — restarting in 5 s", name, exc)
            await asyncio.sleep(5)
            try:
                await consumer.start()
            except Exception as exc:
                log.error("Consumer %s reconnect failed (%s) — will retry", name, exc)

    sandbox_task  = asyncio.create_task(_run_consumer(sandbox_consumer,  "sandbox_events"))
    result_task   = asyncio.create_task(_run_consumer(result_consumer,   "test_results"))
    releases_task = asyncio.create_task(_run_consumer(releases_consumer, "releases"))
    # Start WebSocket Redis relay here (not via deprecated @on_event("startup"))
    ws_redis_task = asyncio.create_task(redis_subscriber())

    log.info("Orchestrator ready.")
    yield

    log.info("Orchestrator shutting down...")
    sandbox_task.cancel()
    result_task.cancel()
    releases_task.cancel()
    ws_redis_task.cancel()
    await asyncio.gather(sandbox_task, result_task, releases_task, ws_redis_task,
                         return_exceptions=True)
    await sandbox_consumer.stop()
    await result_consumer.stop()
    await releases_consumer.stop()


app = FastAPI(
    title="Cartesi RVP — Orchestrator",
    version="0.1.0",
    description="Central brain for the Cartesi Release Validation Platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs_router,       prefix="/runs",       tags=["runs"])
app.include_router(releases_router,   prefix="/releases",   tags=["releases"])
app.include_router(sandboxes_router,  prefix="/sandboxes",  tags=["sandboxes"])
app.include_router(reports_router,    prefix="/reports",    tags=["reports"])
app.include_router(ws_router,         prefix="/ws",         tags=["websocket"])
app.include_router(tests_router,      prefix="/tests",      tags=["tests"])
app.include_router(sessions_router,   prefix="/sessions",   tags=["sessions"])
app.include_router(queues_router,     prefix="/queues",     tags=["queues"])
app.include_router(apps_router,       prefix="/apps",       tags=["apps"])
app.include_router(health_router)


