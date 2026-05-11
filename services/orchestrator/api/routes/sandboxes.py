"""
services/orchestrator/api/routes/sandboxes.py
GET /sandboxes        — list active sandboxes
GET /sandboxes/{id}   — sandbox detail
"""
import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from db import get_db

router = APIRouter()


class SandboxResponse(BaseModel):
    id:             str
    run_id:         str
    status:         str
    anvil_port:     Optional[int] = None
    node_port:      Optional[int] = None
    graphql_port:   Optional[int] = None
    docker_network: Optional[str] = None
    container_ids:  Optional[List[str]] = None
    failure_reason: Optional[str] = None


@router.get("", response_model=List[SandboxResponse])
async def list_sandboxes(db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        text("SELECT id, run_id, status, anvil_port, node_port, graphql_port, "
             "docker_network, container_ids, failure_reason "
             "FROM sandbox.sandboxes ORDER BY provisioned_at DESC LIMIT 50")
    )
    return [dict(r._mapping) for r in rows]


@router.get("/{sandbox_id}", response_model=SandboxResponse)
async def get_sandbox(sandbox_id: str, db: AsyncSession = Depends(get_db)):
    rows = await db.execute(
        text("SELECT id, run_id, status, anvil_port, node_port, graphql_port, "
             "docker_network, container_ids, failure_reason "
             "FROM sandbox.sandboxes WHERE id = :id"),
        {"id": sandbox_id},
    )
    row = rows.fetchone()
    if not row:
        raise HTTPException(404, detail=f"Sandbox {sandbox_id} not found")
    return dict(row._mapping)
