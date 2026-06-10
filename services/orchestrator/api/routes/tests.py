"""
GET  /tests             — list all test definitions (optional ?category= ?phase= filters)
GET  /tests/categories  — grouped phase/category counts for accordion UI
GET  /tests/{id}        — get single definition
POST /tests             — create a new definition from YAML+MD content
PATCH /tests/{id}       — toggle is_active
"""
import json
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import yaml
from fastapi import APIRouter, HTTPException, Depends, Query
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
    ai_allowed: bool = False
    tags: list[str]
    timeout_seconds: int
    definition_raw: str
    category: Optional[str] = None
    phase: Optional[str] = None
    created_at: str
    updated_at: str


class TestCreateIn(BaseModel):
    content: str  # raw YAML+MD body


class TestPatchIn(BaseModel):
    is_active: Optional[bool] = None
    ai_allowed: Optional[bool] = None


class CategoryEntry(BaseModel):
    category: str
    count: int
    active_count: int


class PhaseGroup(BaseModel):
    phase: str
    phase_number: int
    categories: List[CategoryEntry]


def _row_to_out(row) -> dict:
    return {
        "id": str(row.id),
        "slug": row.slug,
        "name": row.name,
        "version": row.version,
        "priority": row.priority,
        "component": row.component,
        "is_active": row.is_active,
        "ai_allowed": bool(getattr(row, "ai_allowed", False)),
        "tags": list(row.tags) if row.tags else [],
        "timeout_seconds": row.timeout_seconds,
        "definition_raw": row.definition_raw,
        "category": row.category,
        "phase": row.phase,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _phase_number(phase: str) -> int:
    """Extract leading integer from 'Phase N: ...' strings for sorting."""
    m = re.match(r"Phase\s+(\d+)", phase or "")
    return int(m.group(1)) if m else 9999


@router.get("/categories", response_model=List[PhaseGroup])
async def list_categories(db: AsyncSession = Depends(get_db)):
    """Return tests grouped by phase then category with counts, for accordion UIs."""
    result = await db.execute(
        text("""
            SELECT phase, category,
                   COUNT(*)                            AS count,
                   COUNT(*) FILTER (WHERE is_active)  AS active_count
            FROM tests.definitions
            WHERE phase IS NOT NULL AND category IS NOT NULL
            GROUP BY phase, category
            ORDER BY phase, category
        """)
    )
    rows = result.fetchall()

    phases: dict[str, dict] = {}
    for row in rows:
        if row.phase not in phases:
            phases[row.phase] = {
                "phase": row.phase,
                "phase_number": _phase_number(row.phase),
                "categories": [],
            }
        phases[row.phase]["categories"].append({
            "category": row.category,
            "count": row.count,
            "active_count": row.active_count,
        })

    return sorted(phases.values(), key=lambda p: p["phase_number"])


@router.get("", response_model=list[TestDefinitionOut])
async def list_definitions(
    category: Optional[str] = Query(None),
    phase: Optional[str] = Query(None),
    ai_allowed: Optional[bool] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    clauses: list[str] = []
    params: dict = {}
    if category:
        clauses.append("category = :cat")
        params["cat"] = category
    if phase:
        clauses.append("phase = :phase")
        params["phase"] = phase
    if ai_allowed is not None:
        clauses.append("ai_allowed = :aa")
        params["aa"] = ai_allowed

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    result = await db.execute(
        text(f"SELECT * FROM tests.definitions {where} ORDER BY name"),
        params,
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
                 category, phase, is_active, created_at, updated_at)
            VALUES
                (:id, :slug, :name, :version, :tags, :component, CAST(:priority AS test_priority),
                 :timeout_seconds, :release_introduced, :definition_raw, CAST(:definition_parsed AS jsonb),
                 :category, :phase, true, :now, :now)
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
            "category": meta.get("category"),
            "phase": meta.get("phase"),
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
    sets: list[str] = []
    params: dict = {"id": definition_id, "now": datetime.now(timezone.utc)}
    if body.is_active is not None:
        sets.append("is_active = :is_active")
        params["is_active"] = body.is_active
    if body.ai_allowed is not None:
        sets.append("ai_allowed = :ai_allowed")
        params["ai_allowed"] = body.ai_allowed
    if not sets:
        raise HTTPException(422, "Nothing to update")

    sets.append("updated_at = :now")
    result = await db.execute(
        text(f"UPDATE tests.definitions SET {', '.join(sets)} WHERE id = :id RETURNING *"),
        params,
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Definition not found")
    await db.commit()
    return _row_to_out(row)
