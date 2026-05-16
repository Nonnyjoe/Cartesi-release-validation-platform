"""
services/orchestrator/api/routes/runs.py
POST /runs          — trigger a new test run
GET  /runs          — list runs (paginated)
GET  /runs/{run_id} — get single run detail
POST /runs/{run_id}/cancel — cancel a queued/running run
"""
import sys
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db
from models.run import Run, RunEvent
from publishers.sandbox_requests import publish_sandbox_request

sys.path.insert(0, "/app/shared")
from sdk_resolver import node_major_version as _major

router = APIRouter()


# ─── Request / Response Schemas ───────────────────────────────────────────────

class TriggerRunRequest(BaseModel):
    release_tag:  str
    image_tag:    str
    suite_ids:    Optional[List[str]] = None
    priority:     int = 5              # 5=user, 9=auto, 1=scheduled
    triggered_by: str = "user"        # must be: github_release | user | scheduled
    triggered_by_user: Optional[str] = None


class RunResponse(BaseModel):
    id:                UUID
    release_tag:       str
    image_tag:         str
    status:            str
    priority:          int
    triggered_by:      str
    triggered_by_user: Optional[str] = None
    suite_ids:         Optional[List[UUID]] = None
    queued_at:         datetime
    started_at:        Optional[datetime] = None
    completed_at:      Optional[datetime] = None
    pass_rate:         Optional[float] = None

    model_config = {"from_attributes": True}


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("", response_model=RunResponse, status_code=201)
async def trigger_run(
    body: TriggerRunRequest,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a new validation run. Publishes a sandbox request to RabbitMQ."""
    run = Run(
        id=uuid.uuid4(),
        release_tag=body.release_tag,
        image_tag=body.image_tag,
        suite_ids=[uuid.UUID(s) for s in (body.suite_ids or [])],
        status="queued",
        priority=body.priority,
        triggered_by=body.triggered_by,
        triggered_by_user=body.triggered_by_user,
        queued_at=datetime.now(tz=timezone.utc),
    )
    db.add(run)

    event = RunEvent(
        run_id=run.id,
        event_type="run.queued",
        payload={"release_tag": body.release_tag, "priority": body.priority},
    )
    db.add(event)
    await db.commit()
    await db.refresh(run)

    # Look up version chain via JOIN — no denormalized columns on release_catalog
    catalog_row = await db.execute(
        text("""
            SELECT
                rc.node_major_version,
                CASE
                    WHEN rc.node_major_version >= 2 AND c.sdk_tag IS NOT NULL
                        THEN 'cartesi/rollups-runtime:' || LTRIM(c.sdk_tag, 'v')
                    ELSE 'cartesi/rollups-node:' || LTRIM(rc.tag, 'v')
                END                    AS image_tag,
                LTRIM(c.sdk_tag, 'v') AS sdk_version,
                LTRIM(c.tag, 'v')     AS cli_version,
                c.devnet_tag          AS devnet_version,
                d.contracts_tag       AS contracts_version
            FROM github.release_catalog rc
            LEFT JOIN github.cli_catalog    c ON c.tag = rc.cli_tag
            LEFT JOIN github.devnet_catalog d ON d.tag = c.devnet_tag
            WHERE rc.tag = :tag
        """),
        {"tag": body.release_tag},
    )
    catalog           = catalog_row.fetchone()
    sdk_version       = catalog.sdk_version       if catalog else None
    cli_version       = catalog.cli_version       if catalog else None
    devnet_version    = catalog.devnet_version    if catalog else None
    contracts_version = catalog.contracts_version if catalog else None
    node_major        = catalog.node_major_version if catalog else _major(body.release_tag)

    # Publish sandbox request onto the priority queue
    await publish_sandbox_request(
        run_id=str(run.id),
        release_tag=body.release_tag,
        image_tag=body.image_tag,
        priority=body.priority,
        requested_by=body.triggered_by_user,
        sdk_version=sdk_version,
        cli_version=cli_version,
        devnet_version=devnet_version,
        contracts_version=contracts_version,
        node_major_version=node_major,
    )

    return run


@router.get("", response_model=List[RunResponse])
async def list_runs(
    status: Optional[str] = Query(None),
    limit:  int = Query(20, le=100),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    """List runs, newest first. Optionally filter by status."""
    q = select(Run).order_by(desc(Run.queued_at)).offset(offset).limit(limit)
    if status:
        q = q.where(Run.status == status)
    result = await db.execute(q)
    return result.scalars().all()


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(Run, uuid.UUID(run_id))
    if not run:
        raise HTTPException(404, detail=f"Run {run_id} not found")
    return run


@router.get("/{run_id}/events")
async def get_run_events(run_id: str, db: AsyncSession = Depends(get_db)):
    """
    Return all stored events for a run in chronological order.
    Used by the dashboard to hydrate the setup/activity log on page load.
    """
    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(400, detail="Invalid run_id")
    result = await db.execute(
        text("""
            SELECT id, run_id, event_type, payload, ts
            FROM orchestrator.run_events
            WHERE run_id = :rid
            ORDER BY ts ASC
        """),
        {"rid": rid},
    )
    rows = result.fetchall()
    return [
        {
            "id":         str(row.id),
            "run_id":     str(row.run_id),
            "event_type": row.event_type,
            "payload":    row.payload or {},
            "ts":         row.ts.isoformat() if row.ts else None,
        }
        for row in rows
    ]


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: str, db: AsyncSession = Depends(get_db)):
    run = await db.get(Run, uuid.UUID(run_id))
    if not run:
        raise HTTPException(404, detail=f"Run {run_id} not found")
    if run.status in ("completed", "failed", "cancelled"):
        raise HTTPException(400, detail=f"Run is already {run.status}")
    run.status = "cancelled"
    event = RunEvent(run_id=run.id, event_type="run.cancelled", payload={})
    db.add(event)
    await db.commit()
    return {"status": "cancelled", "run_id": run_id}
