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

import os

from api.crypto import encrypt_key
from db import get_db
from publishers.ai import AIPublisher
from publishers.notifications import _get_redis, PUBSUB_CHANNEL

router = APIRouter(tags=["sessions"])

ALLOWED_MODELS = {"claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5-20251001"}

# Defaults for bootstrap-provisioned sandboxes (overridable per deploy).
AI_BOOTSTRAP_RELEASE_TAG = os.environ.get("AI_BOOTSTRAP_RELEASE_TAG", "v2.0.0-alpha.11")
AI_BOOTSTRAP_IMAGE_TAG   = os.environ.get(
    "AI_BOOTSTRAP_IMAGE_TAG", "cartesi/rollups-runtime:0.12.0-alpha.39")
# Max test phases selectable per manual session — start small (a phase can hold
# 45 tests); raise as agent budgets grow.
AI_MANUAL_MAX_PHASES = int(os.environ.get("AI_MANUAL_MAX_PHASES", "2"))


class SessionCreateIn(BaseModel):
    mode: Literal["autonomous", "collaborative", "interactive"]
    run_id: Optional[str] = None
    sandbox_id: Optional[str] = None
    goal: Optional[str] = None
    # 'runner' = agent delegates execution to the test-runner (trigger_test);
    # 'ai_manual' = agent reads each selected definition, decides the inputs itself,
    # executes the steps with primitive tools and records verdicts in ai.test_verdicts.
    execution_mode: Literal["runner", "ai_manual"] = "runner"
    selected_tests: Optional[list[str]] = None  # ordered definition slugs (ai_manual)
    # Phase-based selection (ai_manual): names as in tests.definitions.phase.
    # When given without selected_tests, every active+ai_allowed test in those
    # phases is selected; with selected_tests, phases only bound the count
    # (the dashboard sends the trimmed slug list as selected_tests).
    selected_phases: Optional[list[str]] = None
    # Bootstrap a dedicated sandbox for this session: the orchestrator queues a
    # provisioning run (contracts/tokens/app deployed; Anvil state cache makes
    # repeats fast) and the agent starts only after the environment is ready.
    bootstrap: bool = False
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
        "execution_mode":  getattr(row, "execution_mode", None) or "runner",
        "selected_tests":  list(getattr(row, "selected_tests", None) or []),
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

    # Autonomous mode without a target has the agent burning tokens flailing.
    # (Seen in session bb3d5ae0: 76k tokens consumed before failure.)
    # bootstrap=true substitutes for sandbox_id: the environment is provisioned
    # first and the agent only starts once it is ready.
    if body.mode == "autonomous":
        if not body.sandbox_id and not body.bootstrap:
            raise HTTPException(
                422, "autonomous mode requires sandbox_id (or bootstrap: true)")
        if body.execution_mode == "runner" and (not body.goal or not body.goal.strip()):
            raise HTTPException(422, "autonomous mode requires a non-empty goal")

    selected = [s.strip() for s in (body.selected_tests or []) if s and s.strip()]
    phases   = [p.strip() for p in (body.selected_phases or []) if p and p.strip()]
    if body.execution_mode == "ai_manual":
        if not body.sandbox_id and not body.bootstrap:
            raise HTTPException(
                422, "ai_manual execution requires sandbox_id (or bootstrap: true)")
        if len(phases) > AI_MANUAL_MAX_PHASES:
            raise HTTPException(
                422, f"At most {AI_MANUAL_MAX_PHASES} phases per manual session "
                     f"(got {len(phases)}) — split across sessions")
        if phases:
            rows = await db.execute(
                text("""
                    SELECT slug, phase FROM tests.definitions
                    WHERE phase = ANY(:phases) AND is_active AND ai_allowed
                    ORDER BY phase, slug
                """),
                {"phases": phases},
            )
            phase_rows = rows.fetchall()
            found_phases = {r.phase for r in phase_rows}
            missing = [p for p in phases if p not in found_phases]
            if missing:
                raise HTTPException(
                    422, f"No ai-runnable tests in phases: {missing}")
            if not selected:
                # Whole-phase selection: take every runnable test in order.
                selected = [r.slug for r in phase_rows]
        if not selected:
            raise HTTPException(
                422, "ai_manual execution requires selected_tests or selected_phases")
        # Validate slugs against the whitelist so the agent never gets a dead plan.
        rows = await db.execute(
            text("SELECT slug, ai_allowed FROM tests.definitions WHERE slug = ANY(:slugs)"),
            {"slugs": selected},
        )
        found = {r.slug: r.ai_allowed for r in rows.fetchall()}
        unknown     = [s for s in selected if s not in found]
        not_allowed = [s for s in selected if found.get(s) is False]
        if unknown:
            raise HTTPException(422, f"Unknown test slugs: {unknown}")
        if not_allowed:
            raise HTTPException(422, f"Tests not ai_allowed: {not_allowed}")

    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    ciphertext = nonce = None
    if body.anthropic_api_key:
        try:
            ciphertext, nonce = encrypt_key(body.anthropic_api_key)
        except RuntimeError as exc:
            raise HTTPException(500, str(exc))

    # ── Bootstrap: queue a dedicated provisioning run for this session ────────
    # The run is tagged ai_session so the sweep dispatcher skips it and the
    # sandbox-manager keeps the sandbox alive for the session's lifetime.
    run_id = body.run_id
    release_tag = None
    if body.bootstrap and not body.sandbox_id:
        from api.routes.runs import TriggerRunRequest, trigger_run
        release_tag = AI_BOOTSTRAP_RELEASE_TAG
        run = await trigger_run(
            TriggerRunRequest(
                release_tag=release_tag,
                image_tag=AI_BOOTSTRAP_IMAGE_TAG,
                priority=8,
                triggered_by="user",
                triggered_by_user="ai-session-bootstrap",
            ),
            db,
        )
        run_id = str(run.id)
        # NB: metadata can be JSON null (not SQL NULL) when the run was created
        # with metadata_=None — `'null'::jsonb || object` array-concats instead
        # of merging, so sanitize to an object first.
        await db.execute(
            text("""
                UPDATE orchestrator.runs
                SET metadata = (CASE WHEN metadata IS NULL
                                       OR jsonb_typeof(metadata) <> 'object'
                                     THEN '{}'::jsonb ELSE metadata END)
                               || jsonb_build_object('ai_session', true,
                                                     'session_id', CAST(:sid AS text))
                WHERE id = :id
            """),
            {"id": run_id, "sid": session_id},
        )
        await db.commit()

    initial_status = "starting" if (body.bootstrap and not body.sandbox_id) else "active"
    await db.execute(
        text("""
            INSERT INTO ai.sessions
              (id, run_id, sandbox_id, mode, status, goal, model_id,
               anthropic_key_ciphertext, anthropic_key_nonce, created_at,
               execution_mode, selected_tests)
            VALUES
              (:id, :run_id, :sandbox_id, CAST(:mode AS ai_mode),
               CAST(:status AS ai_session_status), :goal, :model,
               :ct, :nonce, :now, :exec_mode, :selected)
        """),
        {
            "id": session_id,
            "run_id": run_id,
            "sandbox_id": body.sandbox_id,
            "mode": body.mode,
            "status": initial_status,
            "goal": body.goal,
            "model": body.model_id,
            "ct": ciphertext,
            "nonce": nonce,
            "now": now,
            "exec_mode": body.execution_mode,
            "selected": selected or None,
        },
    )
    await db.commit()

    # Publish to ai-agent (key NOT included — agent reads from DB)
    publisher = AIPublisher()
    await publisher.publish_session_request({
        "session_id": session_id,
        "mode": body.mode,
        "run_id": run_id,
        "sandbox_id": body.sandbox_id,
        "goal": body.goal,
        "execution_mode": body.execution_mode,
        "selected_tests": selected,
        "bootstrap": bool(body.bootstrap and not body.sandbox_id),
        "release_tag": release_tag,
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
                "mode":           body.mode,
                "goal":           body.goal,
                "model":          body.model_id,
                "execution_mode": body.execution_mode,
            },
        }))
    except Exception:
        pass  # best-effort

    return {
        "session_id": session_id,
        "mode": body.mode,
        "status": initial_status,
        "goal": body.goal,
        "execution_mode": body.execution_mode,
        "selected_tests": selected,
        "model_id": body.model_id,
        "run_id": run_id,
        "sandbox_id": body.sandbox_id,
        "bootstrap": bool(body.bootstrap and not body.sandbox_id),
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
            SELECT id, tool_name, input, output, status, duration_ms,
                   definition_slug, created_at
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
            "definition_slug": r.definition_slug,
            "created_at": r.created_at.isoformat(),
        })
    return out


def _maybe_json(v):
    return json.loads(v) if isinstance(v, str) else v


@router.get("/{session_id}/verdicts")
async def list_session_verdicts(session_id: str, db: AsyncSession = Depends(get_db)):
    """The agent's own verdicts for manually executed tests (execution_mode=ai_manual)."""
    rows = await db.execute(
        text(
            """
            SELECT id, definition_slug, verdict, reasoning, inputs_used, evidence,
                   duration_ms, created_at, confidence, evidence_validated,
                   validation_notes, auto_downgraded_from, trail_step_count,
                   trail_mutating_count, trail_truncated, observations,
                   definition_snapshot, model_id, model_params,
                   release_tag, image_tag, contracts_version
            FROM ai.test_verdicts
            WHERE session_id = :sid
            ORDER BY created_at ASC
            """,
        ),
        {"sid": session_id},
    )
    out = []
    for r in rows.fetchall():
        out.append({
            "verdict_id":           str(r.id),
            "definition_slug":      r.definition_slug,
            "verdict":              r.verdict,
            "reasoning":            r.reasoning,
            "inputs_used":          _maybe_json(r.inputs_used),
            "evidence":             _maybe_json(r.evidence),
            "duration_ms":          r.duration_ms,
            "created_at":           r.created_at.isoformat(),
            # Trust / validation fields (migration 0015)
            "confidence":           float(r.confidence) if r.confidence is not None else None,
            "evidence_validated":   r.evidence_validated,
            "validation_notes":     r.validation_notes,
            "auto_downgraded_from": r.auto_downgraded_from,
            "trail_step_count":     r.trail_step_count,
            "trail_mutating_count": r.trail_mutating_count,
            "trail_truncated":      r.trail_truncated,
            "observations":         _maybe_json(r.observations),
            # Provenance
            "model_id":             r.model_id,
            "model_params":         _maybe_json(r.model_params),
            "release_tag":          r.release_tag,
            "image_tag":            r.image_tag,
            "contracts_version":    r.contracts_version,
            "definition_snapshot":  _maybe_json(r.definition_snapshot),
        })
    return out


@router.get("/{session_id}/plans")
async def list_session_plans(session_id: str, db: AsyncSession = Depends(get_db)):
    """The agent's persisted understanding + plan per test (execution_mode=ai_manual)."""
    rows = await db.execute(
        text(
            """
            SELECT id, definition_slug, objective, success_criteria, failure_criteria,
                   planned_steps, created_at
            FROM ai.test_plans WHERE session_id = :sid ORDER BY created_at ASC
            """,
        ),
        {"sid": session_id},
    )
    return [{
        "plan_id":          str(r.id),
        "definition_slug":  r.definition_slug,
        "objective":        r.objective,
        "success_criteria": r.success_criteria,
        "failure_criteria": r.failure_criteria,
        "planned_steps":    _maybe_json(r.planned_steps),
        "created_at":       r.created_at.isoformat(),
    } for r in rows.fetchall()]


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
            WHERE id = :id AND status IN ('starting', 'active')
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
