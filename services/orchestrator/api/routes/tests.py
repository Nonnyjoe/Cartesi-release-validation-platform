"""
GET  /tests          — list all test definitions
GET  /tests/{id}     — get single definition
POST /tests          — create a new definition from YAML content
PATCH /tests/{id}    — toggle enabled / update content
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime, timezone

from ...database import get_db

router = APIRouter(prefix="/tests", tags=["tests"])


class TestDefinitionOut(BaseModel):
    definition_id: str
    name: str
    description: str
    category: str
    priority: int
    enabled: bool
    tags: list[str]
    created_at: str
    updated_at: str


class TestCreateIn(BaseModel):
    name: str
    content: str  # raw YAML+MD body


class TestPatchIn(BaseModel):
    enabled: Optional[bool] = None
    content: Optional[str] = None


def _row_to_out(row) -> dict:
    return {
        "definition_id": str(row.definition_id),
        "name": row.name,
        "description": row.description or "",
        "category": row.category or "general",
        "priority": row.priority,
        "enabled": row.enabled,
        "tags": row.tags or [],
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


@router.get("", response_model=list[TestDefinitionOut])
async def list_definitions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM tests.definitions ORDER BY priority DESC, name")
    )
    return [_row_to_out(r) for r in result.fetchall()]


@router.get("/{definition_id}", response_model=TestDefinitionOut)
async def get_definition(definition_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("SELECT * FROM tests.definitions WHERE definition_id = :id"),
        {"id": definition_id},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Definition not found")
    return _row_to_out(row)


@router.post("", response_model=TestDefinitionOut, status_code=201)
async def create_definition(body: TestCreateIn, db: AsyncSession = Depends(get_db)):
    import yaml, re

    # Parse YAML frontmatter
    match = re.match(r"^---\n(.*?)\n---\n(.*)$", body.content, re.DOTALL)
    if not match:
        raise HTTPException(422, "Content must start with YAML frontmatter (---)")

    try:
        meta = yaml.safe_load(match.group(1))
    except Exception as e:
        raise HTTPException(422, f"Invalid YAML frontmatter: {e}")

    definition_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    await db.execute(
        text("""
            INSERT INTO tests.definitions
                (definition_id, name, description, category, priority, enabled, tags,
                 assertions, created_at, updated_at)
            VALUES
                (:id, :name, :desc, :cat, :pri, true, :tags::jsonb,
                 :assertions::jsonb, :now, :now)
        """),
        {
            "id": definition_id,
            "name": meta.get("name", body.name),
            "desc": meta.get("description", ""),
            "cat": meta.get("category", "general"),
            "pri": meta.get("priority", 5),
            "tags": str(meta.get("tags", [])),
            "assertions": str(meta.get("assertions", [])),
            "now": now,
        },
    )
    await db.commit()

    result = await db.execute(
        text("SELECT * FROM tests.definitions WHERE definition_id = :id"),
        {"id": definition_id},
    )
    return _row_to_out(result.fetchone())


@router.patch("/{definition_id}", response_model=TestDefinitionOut)
async def patch_definition(
    definition_id: str, body: TestPatchIn, db: AsyncSession = Depends(get_db)
):
    updates = {}
    if body.enabled is not None:
        updates["enabled"] = body.enabled
    if not updates:
        raise HTTPException(422, "Nothing to update")

    set_clause = ", ".join(f"{k} = :{k}" for k in updates)
    updates["id"] = definition_id
    updates["now"] = datetime.now(timezone.utc)

    result = await db.execute(
        text(f"UPDATE tests.definitions SET {set_clause}, updated_at = :now WHERE definition_id = :id RETURNING *"),
        updates,
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Definition not found")
    await db.commit()
    return _row_to_out(row)
