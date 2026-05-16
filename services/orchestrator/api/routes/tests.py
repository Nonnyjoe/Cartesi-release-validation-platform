"""
GET  /tests          — list all test definitions
GET  /tests/{id}     — get single definition
POST /tests          — create a new definition from YAML+MD content
PATCH /tests/{id}    — toggle is_active
"""
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from db import get_db

router = APIRouter(tags=["tests"])

VALID_PRIORITIES = {"low", "medium", "high", "critical"}


class TestDefinitionOut(BaseModel):
    id: str
    slug: str
    name: str
    version: int
    priority: str
    component: Optional[str] = None
    is_active: bool
    tags: list[str]
    created_at: str
    updated_at: str


class TestCreateIn(BaseModel):
    content: str  # raw YAML+MD body


class TestPatchIn(BaseModel):
    is_active: Optional[bool] = None


def _row_to_out(row) -> dict:
    return {
        "id": str(row.id),
        "slug": row.slug,
        "name": row.name,
        "version": row.version,
        "priority": row.priority,
        "component": row.component,
        "is_active": row.is_active,
        "tags": list(row.tags) if row.tags else [],
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("", response_model=list[TestDefinitionOut])
async def list_definitions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM tests.definitions ORDER BY name")
    )
    return [_row_to_out(r) for r in result.fetchall()]


@router.get("/{definition_id}", response_model=TestDefinitionOut)
async def get_definition(definition_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM tests.definitions WHERE id = :id"),
        {"id": definition_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Definition not found")
    return _row_to_out(row)


@router.post("", response_model=TestDefinitionOut, status_code=201)
async def create_definition(body: TestCreateIn, db: AsyncSession = Depends(get_db)):
    # Parse YAML frontmatter
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", body.content, re.DOTALL)
    if not match:
        raise HTTPException(422, "Content must start with YAML frontmatter (---)")

    try:
        meta = yaml.safe_load(match.group(1))
    except Exception as e:
        raise HTTPException(422, f"Invalid YAML frontmatter: {e}")

    slug = meta.get("id") or meta.get("slug")
    if not slug:
        raise HTTPException(422, "YAML frontmatter must include 'id' field (used as slug)")

    priority = meta.get("priority", "medium")
    if priority not in VALID_PRIORITIES:
        priority = "medium"

    definition_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    tags = meta.get("tags", [])
    if isinstance(tags, str):
        tags = [tags]

    await db.execute(
        text("""
            INSERT INTO tests.definitions
                (id, slug, name, version, tags, component, priority,
                 timeout_seconds, release_introduced, definition_raw, definition_parsed,
                 is_active, created_at, updated_at)
            VALUES
                (:id, :slug, :name, :version, :tags, :component, CAST(:priority AS test_priority),
                 :timeout_seconds, :release_introduced, :definition_raw, CAST(:definition_parsed AS jsonb),
                 true, :now, :now)
        """),
        {
            "id": definition_id,
            "slug": slug,
            "name": meta.get("name", slug),
            "version": int(meta.get("version", 1)),
            "tags": tags,
            "component": meta.get("component"),
            "priority": priority,
            "timeout_seconds": int(meta.get("timeout_seconds", 120)),
            "release_introduced": meta.get("release_introduced"),
            "definition_raw": body.content,
            "definition_parsed": json.dumps(meta),
            "now": now,
        },
    )
    await db.commit()

    result = await db.execute(
        text("SELECT * FROM tests.definitions WHERE id = :id"),
        {"id": definition_id},
    )
    return _row_to_out(result.fetchone())


@router.patch("/{definition_id}", response_model=TestDefinitionOut)
async def patch_definition(
    definition_id: str, body: TestPatchIn, db: AsyncSession = Depends(get_db)
):
    if body.is_active is None:
        raise HTTPException(422, "Nothing to update")

    result = await db.execute(
        text("""
            UPDATE tests.definitions
            SET is_active = :is_active, updated_at = :now
            WHERE id = :id
            RETURNING *
        """),
        {"is_active": body.is_active, "now": datetime.now(timezone.utc), "id": definition_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Definition not found")
    await db.commit()
    return _row_to_out(row)
