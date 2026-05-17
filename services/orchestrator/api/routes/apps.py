"""
services/orchestrator/api/routes/apps.py

CRUD routes for the application registry.

GET  /apps          — list active (or all) registered applications
POST /apps          — register a new application
GET  /apps/{app_id} — fetch a single application
PATCH /apps/{app_id} — update name / github_url / description / is_active
DELETE /apps/{app_id} — soft-delete (sets is_active=false)
"""
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, HttpUrl, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db

router = APIRouter()


# ─── Request / Response Schemas ───────────────────────────────────────────────

class AppCreate(BaseModel):
    name:        str
    github_url:  str
    description: Optional[str] = None
    added_by:    Optional[str] = None

    @field_validator("github_url")
    @classmethod
    def _validate_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        if not v.startswith(("https://github.com/", "http://github.com/",
                              "https://gitlab.com/", "http://gitlab.com/",
                              "https://bitbucket.org/")):
            # Accept any https:// URL — only warn on suspicious schemes
            if not v.startswith("https://"):
                raise ValueError("github_url must start with https://")
        return v

    @field_validator("name")
    @classmethod
    def _validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name cannot be empty")
        if len(v) > 120:
            raise ValueError("name must be 120 characters or fewer")
        return v


class AppUpdate(BaseModel):
    name:        Optional[str] = None
    github_url:  Optional[str] = None
    description: Optional[str] = None
    is_active:   Optional[bool] = None


class AppResponse(BaseModel):
    id:          str
    name:        str
    github_url:  str
    description: Optional[str] = None
    is_active:   bool
    added_by:    Optional[str] = None
    added_at:    str
    updated_at:  str


def _row_to_resp(row) -> AppResponse:
    return AppResponse(
        id=str(row.id),
        name=row.name,
        github_url=row.github_url,
        description=row.description,
        is_active=row.is_active,
        added_by=row.added_by,
        added_at=row.added_at.isoformat() if row.added_at else "",
        updated_at=row.updated_at.isoformat() if row.updated_at else "",
    )


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("", response_model=List[AppResponse])
async def list_apps(
    include_inactive: bool = Query(False, description="Include soft-deleted applications"),
    db: AsyncSession = Depends(get_db),
):
    """List registered applications, newest first."""
    where = "" if include_inactive else "WHERE is_active = true"
    result = await db.execute(
        text(f"SELECT * FROM tests.applications {where} ORDER BY added_at DESC")
    )
    return [_row_to_resp(r) for r in result.fetchall()]


@router.post("", response_model=AppResponse, status_code=201)
async def register_app(
    body: AppCreate,
    db: AsyncSession = Depends(get_db),
):
    """Register a new Cartesi application."""
    # Check for duplicate (active)
    dup = await db.execute(
        text("SELECT id FROM tests.applications WHERE github_url = :url AND is_active = true"),
        {"url": body.github_url},
    )
    if dup.fetchone():
        raise HTTPException(409, detail=f"An active application with url {body.github_url!r} already exists.")

    app_id = uuid.uuid4()
    now = datetime.now(tz=timezone.utc)
    await db.execute(
        text("""
            INSERT INTO tests.applications (id, name, github_url, description, is_active, added_by, added_at, updated_at)
            VALUES (:id, :name, :url, :desc, true, :added_by, :now, :now)
        """),
        {
            "id":       app_id,
            "name":     body.name,
            "url":      body.github_url,
            "desc":     body.description,
            "added_by": body.added_by,
            "now":      now,
        },
    )
    await db.commit()

    row = await db.execute(
        text("SELECT * FROM tests.applications WHERE id = :id"),
        {"id": app_id},
    )
    return _row_to_resp(row.fetchone())


@router.get("/{app_id}", response_model=AppResponse)
async def get_app(app_id: str, db: AsyncSession = Depends(get_db)):
    try:
        aid = uuid.UUID(app_id)
    except ValueError:
        raise HTTPException(400, detail="Invalid app_id")
    row = await db.execute(
        text("SELECT * FROM tests.applications WHERE id = :id"), {"id": aid}
    )
    r = row.fetchone()
    if not r:
        raise HTTPException(404, detail=f"Application {app_id} not found")
    return _row_to_resp(r)


@router.patch("/{app_id}", response_model=AppResponse)
async def update_app(
    app_id: str,
    body: AppUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update name, github_url, description, or is_active for an application."""
    try:
        aid = uuid.UUID(app_id)
    except ValueError:
        raise HTTPException(400, detail="Invalid app_id")

    row = await db.execute(
        text("SELECT * FROM tests.applications WHERE id = :id"), {"id": aid}
    )
    r = row.fetchone()
    if not r:
        raise HTTPException(404, detail=f"Application {app_id} not found")

    updates: dict = {}
    if body.name        is not None: updates["name"]        = body.name.strip()
    if body.github_url  is not None: updates["github_url"]  = body.github_url.strip().rstrip("/")
    if body.description is not None: updates["description"] = body.description
    if body.is_active   is not None: updates["is_active"]   = body.is_active
    if not updates:
        return _row_to_resp(r)

    now = datetime.now(tz=timezone.utc)
    updates["updated_at"] = now
    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    await db.execute(
        text(f"UPDATE tests.applications SET {set_clause} WHERE id = :app_id"),
        {**updates, "app_id": aid},
    )
    await db.commit()

    updated = await db.execute(
        text("SELECT * FROM tests.applications WHERE id = :id"), {"id": aid}
    )
    return _row_to_resp(updated.fetchone())


@router.delete("/{app_id}", status_code=204)
async def delete_app(app_id: str, db: AsyncSession = Depends(get_db)):
    """Soft-delete an application (sets is_active=false). Existing runs are unaffected."""
    try:
        aid = uuid.UUID(app_id)
    except ValueError:
        raise HTTPException(400, detail="Invalid app_id")

    result = await db.execute(
        text("""
            UPDATE tests.applications
               SET is_active = false, updated_at = now()
             WHERE id = :id AND is_active = true
        """),
        {"id": aid},
    )
    await db.commit()
    if result.rowcount == 0:
        raise HTTPException(404, detail=f"Application {app_id} not found or already inactive")
