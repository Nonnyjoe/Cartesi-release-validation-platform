"""
GET  /sessions                       — paginated list
GET  /sessions/{id}                  — single session
POST /sessions                       — create (publishes to ai.sessions queue)
POST /sessions/{id}/message          — inject message into interactive/collaborative session
POST /sessions/{id}/cancel           — cancel active session
GET  /sessions/suggestions           — list AI suggested actions
POST /sessions/suggestions/{id}/review — approve/reject
"""
from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional
import uuid, json
from datetime import datetime, timezone

from db import get_db
from publishers.ai import AIPublisher

router = APIRouter(tags=["sessions"])


class SessionCreateIn(BaseModel):
    mode: str  # autonomous | collaborative | interactive
    run_id: Optional[str] = None
    sandbox_id: Optional[str] = None
    goal: Optional[str] = None


class MessageIn(BaseModel):
    message: str


class ReviewIn(BaseModel):
    status: str  # approved | rejected


def _session_row(row) -> dict:
    return {
        "session_id": str(row.session_id),
        "run_id": str(row.run_id) if row.run_id else None,
        "mode": row.mode,
        "status": row.status,
        "goal": row.goal,
        "model": row.model or "claude-opus-4-6",
        "tool_calls_used": row.tool_calls_used or 0,
        "input_tokens": row.input_tokens or 0,
        "output_tokens": row.output_tokens or 0,
        "findings": json.loads(row.findings) if isinstance(row.findings, str) else (row.findings or []),
        "created_at": row.created_at.isoformat(),
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


@router.get("")
async def list_sessions(
    page: int = 1, page_size: int = 20, db: AsyncSession = Depends(get_db)
):
    offset = (page - 1) * page_size
    rows = await db.execute(
        text("SELECT * FROM ai.sessions ORDER BY created_at DESC LIMIT :lim OFFSET :off"),
        {"lim": page_size, "off": offset},
    )
    count = await db.execute(text("SELECT COUNT(*) FROM ai.sessions"))
    total = count.scalar()
    return {"items": [_session_row(r) for r in rows.fetchall()], "total": total, "page": page, "page_size": page_size}


@router.get("/suggestions")
async def list_suggestions(session_id: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    q = "SELECT * FROM ai.suggested_test_actions"
    params: dict = {}
    if session_id:
        q += " WHERE session_id = :sid"
        params["sid"] = session_id
    q += " ORDER BY created_at DESC"
    rows = await db.execute(text(q), params)
    return [
        {
            "action_id": str(r.action_id),
            "session_id": str(r.session_id),
            "action_type": r.action_type,
            "description": r.description,
            "rationale": r.rationale or "",
            "status": r.status,
            "test_definition_yaml": r.test_definition_yaml,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows.fetchall()
    ]


@router.get("/{session_id}")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        text("SELECT * FROM ai.sessions WHERE session_id = :id"), {"id": session_id}
    )).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    return _session_row(row)


@router.post("", status_code=201)
async def create_session(body: SessionCreateIn, db: AsyncSession = Depends(get_db)):
    if body.mode not in ("autonomous", "collaborative", "interactive"):
        raise HTTPException(422, "mode must be autonomous, collaborative, or interactive")

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    await db.execute(
        text("""
            INSERT INTO ai.sessions (session_id, run_id, mode, status, goal, model, created_at)
            VALUES (:id, :run_id, :mode, 'active', :goal, 'claude-opus-4-6', :now)
        """),
        {"id": session_id, "run_id": body.run_id, "mode": body.mode, "goal": body.goal, "now": now},
    )
    await db.commit()

    # Publish to ai-agent
    publisher = AIPublisher()
    await publisher.publish_session_request({
        "session_id": session_id,
        "mode": body.mode,
        "run_id": body.run_id,
        "sandbox_id": body.sandbox_id,
        "goal": body.goal,
    })

    row = (await db.execute(
        text("SELECT * FROM ai.sessions WHERE session_id = :id"), {"id": session_id}
    )).fetchone()
    return _session_row(row)


@router.post("/{session_id}/message")
async def send_message(session_id: str, body: MessageIn, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        text("SELECT mode, status FROM ai.sessions WHERE session_id = :id"), {"id": session_id}
    )).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    if row.status != "active":
        raise HTTPException(409, "Session is not active")
    if row.mode not in ("collaborative", "interactive"):
        raise HTTPException(409, "Message injection only supported for collaborative/interactive sessions")

    publisher = AIPublisher()
    await publisher.publish_user_message(session_id, body.message)
    return {"ok": True}


@router.post("/{session_id}/cancel")
async def cancel_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        text("""
            UPDATE ai.sessions SET status = 'cancelled', completed_at = now()
            WHERE session_id = :id AND status = 'active'
            RETURNING session_id
        """),
        {"id": session_id},
    )
    if not result.fetchone():
        raise HTTPException(404, "Active session not found")
    await db.commit()
    return {"ok": True}


@router.post("/suggestions/{action_id}/review")
async def review_suggestion(action_id: str, body: ReviewIn, db: AsyncSession = Depends(get_db)):
    if body.status not in ("approved", "rejected"):
        raise HTTPException(422, "status must be approved or rejected")

    result = await db.execute(
        text("""
            UPDATE ai.suggested_test_actions SET status = :status
            WHERE action_id = :id RETURNING *
        """),
        {"id": action_id, "status": body.status},
    )
    row = result.fetchone()
    if not row:
        raise HTTPException(404, "Action not found")
    await db.commit()
    return {
        "action_id": str(row.action_id),
        "status": row.status,
        "description": row.description,
    }
