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

from fastapi import APIRouter, Depends, HTTPException, Query, Response
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
    app_id:       Optional[str] = None  # UUID of tests.applications row; None = raw node tests only


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
    app_id:            Optional[UUID] = None
    app_address:       Optional[str] = None

    model_config = {"from_attributes": True}


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.post("", response_model=RunResponse, status_code=201)
async def trigger_run(
    body: TriggerRunRequest,
    db: AsyncSession = Depends(get_db),
):
    """Trigger a new validation run. Publishes a sandbox request to RabbitMQ."""

    # Validate and resolve app_id → name + github_url
    app_name:       Optional[str] = None
    app_github_url: Optional[str] = None
    resolved_app_id: Optional[uuid.UUID] = None

    if body.app_id:
        try:
            resolved_app_id = uuid.UUID(body.app_id)
        except ValueError:
            raise HTTPException(400, detail=f"Invalid app_id: {body.app_id!r}")

        app_row = await db.execute(
            text("SELECT name, github_url, is_active FROM tests.applications WHERE id = :id"),
            {"id": resolved_app_id},
        )
        app = app_row.fetchone()
        if not app:
            raise HTTPException(404, detail=f"Application {body.app_id} not found")
        if not app.is_active:
            raise HTTPException(409, detail=f"Application {body.app_id} is inactive")
        app_name       = app.name
        app_github_url = app.github_url

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
        app_id=resolved_app_id,
    )
    db.add(run)

    event = RunEvent(
        run_id=run.id,
        event_type="run.queued",
        payload={
            "release_tag": body.release_tag,
            "priority":    body.priority,
            "app_id":      str(resolved_app_id) if resolved_app_id else None,
            "app_name":    app_name,
        },
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
        app_id=str(resolved_app_id) if resolved_app_id else None,
        app_name=app_name,
        app_github_url=app_github_url,
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


@router.get("/{run_id}/logs")
async def get_run_logs(
    run_id:   str,
    source:   Optional[str] = Query(None, description="Filter by source (comma-separated for multiple)"),
    level:    Optional[str] = Query(None, description="Minimum level: error | warn | info | debug"),
    after_id: Optional[int] = Query(None, description="Cursor: return only rows with id > after_id"),
    limit:    int = Query(200, le=500, description="Max lines to return"),
    db: AsyncSession = Depends(get_db),
):
    """
    Return persisted log lines for a run, newest-last with cursor pagination.

    Pagination:
      - First call: omit after_id → returns the first `limit` lines (oldest first).
      - Next page:  pass after_id = last returned id → returns next `limit` lines.
      - Response includes next_cursor (None if no more lines exist).

    Filtering:
      - source: exact source label or comma-separated list (e.g. "advancer,anvil")
      - level:  only lines at this severity or higher (error > warn > info > debug)
    """
    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(400, detail="Invalid run_id")

    # Build WHERE clauses dynamically
    conditions = ["run_id = :run_id"]
    params: dict = {"run_id": rid, "limit": limit}

    if after_id is not None:
        conditions.append("id > :after_id")
        params["after_id"] = after_id

    if source:
        sources = [s.strip() for s in source.split(",") if s.strip()]
        if sources:
            conditions.append("source = ANY(:sources)")
            params["sources"] = sources

    LEVEL_ORDER = {"error": 0, "warn": 1, "info": 2, "debug": 3}
    if level and level in LEVEL_ORDER:
        threshold = LEVEL_ORDER[level]
        allowed   = [lvl for lvl, rank in LEVEL_ORDER.items() if rank <= threshold]
        conditions.append("level = ANY(:levels)")
        params["levels"] = allowed

    where = " AND ".join(conditions)
    result = await db.execute(
        text(f"""
            SELECT id, source, level, message, ts
            FROM orchestrator.run_logs
            WHERE {where}
            ORDER BY id ASC
            LIMIT :limit
        """),
        params,
    )
    rows = result.fetchall()

    lines = [
        {
            "id":      row.id,
            "source":  row.source,
            "level":   row.level,
            "message": row.message,
            "ts":      row.ts.isoformat() if row.ts else None,
        }
        for row in rows
    ]

    # Determine if there are more lines after this page
    next_cursor = None
    if len(rows) == limit:
        last_id = rows[-1].id
        more = await db.execute(
            text("SELECT 1 FROM orchestrator.run_logs WHERE run_id = :rid AND id > :last LIMIT 1"),
            {"rid": rid, "last": last_id},
        )
        if more.fetchone():
            next_cursor = last_id

    return {"lines": lines, "next_cursor": next_cursor}


@router.get("/{run_id}/logs/download")
async def download_run_logs(
    run_id: str,
    source: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """
    Stream the full run log as a plain-text file download.
    Format: <ts> [<source>] <LEVEL> <message>\\n
    """
    try:
        rid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(400, detail="Invalid run_id")

    conditions = ["run_id = :run_id"]
    params: dict = {"run_id": rid}
    if source:
        sources = [s.strip() for s in source.split(",") if s.strip()]
        if sources:
            conditions.append("source = ANY(:sources)")
            params["sources"] = sources

    where = " AND ".join(conditions)
    result = await db.execute(
        text(f"""
            SELECT source, level, message, ts
            FROM orchestrator.run_logs
            WHERE {where}
            ORDER BY id ASC
        """),
        params,
    )
    rows = result.fetchall()

    lines = []
    for row in rows:
        ts_str = row.ts.strftime("%Y-%m-%dT%H:%M:%S") if row.ts else "?"
        lines.append(f"{ts_str} [{row.source}] {row.level.upper()} {row.message}")

    content = "\n".join(lines)
    filename = f"run-{run_id[:8]}-logs.txt"
    return Response(
        content=content,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
