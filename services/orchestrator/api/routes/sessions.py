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
from pydantic import BaseModel, Field
from typing import Literal, Optional
import uuid, json
from datetime import datetime, timezone

from api.crypto import encrypt_key
from db import get_db
from publishers.ai import AIPublisher
from publishers.notifications import _get_redis, PUBSUB_CHANNEL

router = APIRouter(tags=["sessions"])

ALLOWED_MODELS = {"claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"}


class SessionCreateIn(BaseModel):
    mode: Literal["autonomous", "collaborative", "interactive"]
    run_id: Optional[str] = None
    sandbox_id: Optional[str] = None
    goal: Optional[str] = None
    # New: per-session credentials
    anthropic_api_key: Optional[str] = Field(default=None, min_length=20)
    model_id: str = "claude-opus-4-6"


class MessageIn(BaseModel):
    message: str


class ReviewIn(BaseModel):
    status: str  # approved | rejected


def _session_row(row) -> dict:
    findings = row.findings
    if isinstance(findings, str):
        findings = json.loads(findings)
    return {
        "session_id":      str(row.id),
        "run_id":          str(row.run_id) if row.run_id else None,
        "sandbox_id":      str(row.sandbox_id) if row.sandbox_id else None,
        "mode":            row.mode,
        "status":          row.status,
        "goal":            row.goal,
        "model":           getattr(row, "model_id", None) or "claude-opus-4-6",
        "tool_calls_used": row.tool_call_count or 0,
        # Schema only tracks a single total — surface it under both input/output for the existing UI.
        "input_tokens":    row.total_tokens or 0,
        "output_tokens":   0,
        "findings":        findings or [],
        "created_at":      row.created_at.isoformat(),
        "completed_at":    row.closed_at.isoformat() if row.closed_at else None,
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
        text("SELECT * FROM ai.sessions WHERE id = :id"), {"id": session_id}
    )).fetchone()
    if not row:
        raise HTTPException(404, "Session not found")
    return _session_row(row)


@router.post("", status_code=201)
async def create_session(body: SessionCreateIn, db: AsyncSession = Depends(get_db)):
    if body.model_id not in ALLOWED_MODELS:
        raise HTTPException(422, f"model_id must be one of {sorted(ALLOWED_MODELS)}")

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    ciphertext = nonce = None
    if body.anthropic_api_key:
        try:
            ciphertext, nonce = encrypt_key(body.anthropic_api_key)
        except RuntimeError as exc:
            raise HTTPException(500, str(exc))

    await db.execute(
        text("""
            INSERT INTO ai.sessions
              (id, run_id, sandbox_id, mode, status, goal, model_id,
               anthropic_key_ciphertext, anthropic_key_nonce, created_at)
            VALUES
              (:id, :run_id, :sandbox_id, CAST(:mode AS ai_mode), 'active', :goal, :model,
               :ct, :nonce, :now)
        """),
        {
            "id": session_id,
            "run_id": body.run_id,
            "sandbox_id": body.sandbox_id,
            "mode": body.mode,
            "goal": body.goal,
            "model": body.model_id,
            "ct": ciphertext,
            "nonce": nonce,
            "now": now,
        },
    )
    await db.commit()

    # Publish to ai-agent (key NOT included — agent reads from DB)
    publisher = AIPublisher()
    await publisher.publish_session_request({
        "session_id": session_id,
        "mode": body.mode,
        "run_id": body.run_id,
        "sandbox_id": body.sandbox_id,
        "goal": body.goal,
    })

    # Live event so the dashboard's Sessions list updates without reload.
    try:
        await _get_redis().publish(PUBSUB_CHANNEL, json.dumps({
            "event_id":   str(uuid.uuid4()),
            "session_id": session_id,
            "run_id":     body.run_id,
            "service":    "orchestrator",
            "ts":         now.isoformat(),
            "event_type": "ai.session_created",
            "payload":    {
                "mode":   body.mode,
                "goal":   body.goal,
                "model":  body.model_id,
            },
        }))
    except Exception:
        pass  # best-effort

    return {
        "session_id": session_id,
        "mode": body.mode,
        "status": "active",
        "goal": body.goal,
        "model_id": body.model_id,
        "run_id": body.run_id,
        "sandbox_id": body.sandbox_id,
        "created_at": now.isoformat(),
    }


@router.get("/{session_id}/tools")
async def list_session_tools(
    session_id: str,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
):
    """Return the audited tool invocations for a session, newest first."""
    rows = await db.execute(
        text(
            """
            SELECT id, tool_name, input, output, status, duration_ms, created_at
            FROM ai.tool_invocations
            WHERE session_id = :sid
            ORDER BY created_at DESC
            LIMIT :lim
            """,
        ),
        {"sid": session_id, "lim": limit},
    )
    out = []
    for r in rows.fetchall():
        out.append({
            "id": str(r.id),
            "tool_name": r.tool_name,
            "input": r.input,
            "output": r.output,
            "status": r.status,
            "duration_ms": r.duration_ms,
            "created_at": r.created_at.isoformat(),
        })
    return out


@router.post("/{session_id}/message")
async def send_message(session_id: str, body: MessageIn, db: AsyncSession = Depends(get_db)):
    row = (await db.execute(
        text("SELECT mode, status FROM ai.sessions WHERE id = :id"), {"id": session_id}
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
            UPDATE ai.sessions SET status = 'aborted', closed_at = now()
            WHERE id = :id AND status = 'active'
            RETURNING id
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
