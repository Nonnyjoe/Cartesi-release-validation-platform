"""
services/orchestrator/api/routes/sandboxes.py
GET /sandboxes        — list active sandboxes
GET /sandboxes/{id}   — sandbox detail
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_db

router = APIRouter()


from datetime import datetime

class SandboxResponse(BaseModel):
    id:               UUID
    run_id:           Optional[UUID] = None
    status:           str
    anvil_port:       Optional[int] = None
    node_port:        Optional[int] = None
    graphql_port:     Optional[int] = None
    docker_network:   Optional[str] = None
    container_ids:    Optional[List[str]] = None
    failure_reason:   Optional[str] = None
    provisioned_at:   Optional[datetime] = None
    ready_at:         Optional[datetime] = None
    closed_at:        Optional[datetime] = None

    model_config = {"from_attributes": True}


_SELECT = (
    "SELECT id, run_id, status, anvil_port, node_port, graphql_port, "
    "docker_network, container_ids, failure_reason, "
    "provisioned_at, ready_at, closed_at "
    "FROM sandbox.sandboxes"
)


@router.get("", response_model=List[SandboxResponse])
async def list_sandboxes(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        text(f"{_SELECT} ORDER BY provisioned_at DESC LIMIT 50")
    )
    return [dict(r._mapping) for r in rows]


@router.get("/{sandbox_id}", response_model=SandboxResponse)
async def get_sandbox(sandbox_id: str, db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        text(f"{_SELECT} WHERE id = :id"),
        {"id": sandbox_id},
    )
    row = rows.fetchone()
    if not row:
        raise HTTPException(404, detail=f"Sandbox {sandbox_id} not found")
    return dict(row._mapping)
