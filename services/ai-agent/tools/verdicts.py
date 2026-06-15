"""Record the agent's own pass/fail judgment for a manually executed test.

Used in execution_mode='ai_manual' sessions: after the agent reads a test
definition, executes the steps itself via primitive tools, and compares the
observed behaviour against the definition's Expected Behaviour, it records a
verdict here. Writes go to ai.test_verdicts — deliberately separate from the
runner-produced tests.results table.

Trustworthiness hardening (2026-06-13 review):
  - VALIDATION GATE: a 'passed'/'failed' verdict with an empty execution trail
    is auto-downgraded to 'inconclusive' — you cannot pass/fail a test you did
    not execute. Evidence is cross-checked against the trail (evidence_validated).
  - PROVENANCE: model id+params, release/image/contracts version, and a frozen
    definition snapshot are stamped on every verdict for reproducibility.
  - IMMUTABLE TRAIL: each tool invocation is claimed by exactly one verdict via
    an immutable verdict_id FK (replacing the mutable slug/time-window heuristic).
  - record_test_plan persists the agent's understanding + plan before execution.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from tools.db import get_pool

log = logging.getLogger("ai-agent.verdicts")

VALID_VERDICTS = ("passed", "failed", "blocked", "skipped", "inconclusive")

# Trail rows beyond this are summarised-as-truncated rather than dropped silently.
TRAIL_CAP = 400

# Tools whose effect mutates chain / node / app state. Read-only tests legitimately
# have zero mutating steps, so this count is informational (surfaced for the human
# gate + evidence heuristic) — it is NOT a hard pass requirement.
_MUTATING_TOOLS = {"send_advance_input", "advance_time", "restart_component", "pause_network"}
_CLI_MUTATING_HINTS = ("send", "deploy", "execute", "register", "db init", "remove", "set")


def _is_mutating(tool: str, inp: dict) -> bool:
    if tool in _MUTATING_TOOLS:
        return True
    if tool == "run_cast_command":
        first = str(inp.get("command", "")).strip().split()[:1]
        return bool(first) and first[0] in ("send", "publish") \
            or "anvil_mine" in str(inp.get("command", "")) \
            or "anvil_set" in str(inp.get("command", ""))
    if tool == "run_cli_command":
        blob = (str(inp.get("binary", "")) + " " + str(inp.get("args", ""))).lower()
        return any(h in blob for h in _CLI_MUTATING_HINTS)
    return False


# ── Execution-trail digest ────────────────────────────────────────────────────

def _short_hex(v, head: int = 48, tail: int = 16):
    if isinstance(v, str) and v.startswith("0x") and len(v) > head + tail + 12:
        return f"{v[:head]}…{v[-tail:]} (len {len(v)})"
    return v


def _digest_step(tool: str, inp: dict, out, status: str) -> dict:
    inp = inp or {}
    out = out if isinstance(out, dict) else {}
    d: dict = {"tool": tool, "status": status}

    if tool == "run_cast_command":
        cmd = str(inp.get("command", ""))
        d["target"] = "anvil (L1 tx)" if cmd.split()[:1] == ["send"] else "anvil"
        d["input"] = _short_hex(cmd[:220])
        stdout = str(out.get("stdout", ""))
        tx = None
        for line in stdout.splitlines():
            if line.startswith("transactionHash"):
                tx = line.split()[-1]
                break
        d["output"] = {"exit": out.get("returncode"),
                       **({"tx_hash": tx} if tx else {}),
                       "stdout_head": _short_hex(stdout[:160])}
    elif tool == "send_advance_input":
        d["target"] = "application (advance)"
        d["input"] = {"payload": _short_hex(inp.get("payload")),
                      "app_address": inp.get("app_address")}
        d["output"] = {"status_code": out.get("status_code"),
                       "body_head": str(out.get("body", ""))[:120]}
    elif tool == "call_jsonrpc":
        d["target"] = "node:jsonrpc-api"
        d["input"] = {"method": inp.get("method"), "params": inp.get("params")}
        res = out.get("result")
        d["output"] = _short_hex(json.dumps(res, default=str)[:300]) if res is not None \
            else {"error": str(out.get("error", ""))[:160]}
    elif tool == "call_inspect":
        d["target"] = "node:inspect"
        payload = str(inp.get("payload", ""))
        try:
            decoded = bytes.fromhex(payload[2:]).decode("utf-8")
            d["input"] = {"payload": payload[:80], "route": decoded[:60]}
        except Exception:
            d["input"] = {"payload": _short_hex(payload)}
        d["output"] = _short_hex(json.dumps(out.get("body", out), default=str)[:240])
    elif tool == "read_logs":
        d["target"] = f"container:{inp.get('component', '?')}"
        d["input"] = {"tail": inp.get("tail")}
        logs = out.get("logs") or out.get("lines") or ""
        text = "\n".join(logs) if isinstance(logs, list) else str(logs)
        d["output"] = {"lines": text.count("\n") + 1 if text else 0,
                       "last_line": text.strip().splitlines()[-1][:160] if text.strip() else ""}
    elif tool == "run_cli_command":
        d["target"] = f"container:{out.get('container') or inp.get('binary', '?')}"
        d["input"] = f"{inp.get('binary', '')} {str(inp.get('args', ''))[:160]}"
        d["output"] = {"exit": out.get("exit_code", out.get("returncode")),
                       "stdout_head": str(out.get("stdout", ""))[:160]}
    elif tool == "query_db":
        d["target"] = "platform-db"
        d["input"] = str(inp.get("sql", ""))[:160]
        rows = out.get("rows")
        d["output"] = {"row_count": len(rows) if isinstance(rows, list) else out.get("row_count")}
    elif tool == "query_graphql":
        d["target"] = "node:graphql"
        d["input"] = str(inp.get("query", ""))[:120]
        d["output"] = _short_hex(json.dumps(out, default=str)[:200])
    elif tool == "advance_time":
        d["target"] = "anvil"
        d["input"] = {"blocks": inp.get("blocks")}
        d["output"] = {"ok": bool(out.get("success", True))}
    elif tool == "verify_voucher":
        d["target"] = "node:outputs"
        d["input"] = {"input_index": inp.get("input_index"), "voucher_index": inp.get("voucher_index")}
        d["output"] = _short_hex(json.dumps(out, default=str)[:200])
    else:
        d["target"] = "local"
        d["input"] = _short_hex(json.dumps(inp, default=str)[:160])
        if status != "ok":
            d["output"] = {"error": str(out.get("error", ""))[:160]}
    return d


async def _claim_trail(conn, session_id: str) -> tuple[list[dict], list, bool, int]:
    """Gather the invocations this session has not yet attributed to a verdict.

    Attribution is by an immutable per-row claim (verdict_id IS NULL), in order —
    each tool call belongs to exactly one verdict (the next one recorded). This
    replaces the mutable slug/time-window heuristic the review flagged.

    Returns (digested_trail, raw_ids, truncated, mutating_count).
    """
    rows = await conn.fetch(
        """
        SELECT id, tool_name, input, output, status, duration_ms, created_at
        FROM ai.tool_invocations
        WHERE session_id = $1::uuid AND verdict_id IS NULL
          AND tool_name NOT IN ('read_test_definition', 'record_test_verdict', 'record_test_plan')
        ORDER BY created_at ASC
        LIMIT $2
        """,
        session_id, TRAIL_CAP + 1,
    )
    truncated = len(rows) > TRAIL_CAP
    rows = rows[:TRAIL_CAP]
    trail, ids, mutating = [], [], 0
    for r in rows:
        inp, out = r["input"], r["output"]
        if isinstance(inp, str):
            try: inp = json.loads(inp)
            except Exception: inp = {}
        if isinstance(out, str):
            try: out = json.loads(out)
            except Exception: out = {}
        if _is_mutating(r["tool_name"], inp or {}):
            mutating += 1
        step = _digest_step(r["tool_name"], inp or {}, out, r["status"])
        step["invocation_id"] = str(r["id"])
        step["duration_ms"] = r["duration_ms"]
        step["at"] = r["created_at"].isoformat()
        trail.append(step)
        ids.append(r["id"])
    return trail, ids, truncated, mutating


def _evidence_validated(reasoning: str, evidence: dict | None,
                        observations: Any, trail: list[dict]) -> bool:
    """True when the agent cites at least one concrete literal that the trail
    actually contains — a cheap programmatic hallucination check. Conservative:
    used as a FLAG (surfaced for the human gate), not an auto-reject."""
    import re
    claim_text = " ".join([
        reasoning or "",
        json.dumps(evidence or {}, default=str),
        json.dumps(observations or [], default=str),
    ])
    # Substantial literals: hex (>=10 chars), long numbers (>=4 digits).
    claims = set(re.findall(r"0x[0-9a-fA-F]{8,}", claim_text))
    claims |= set(re.findall(r"\b\d{4,}\b", claim_text))
    if not claims:
        return False
    corpus = json.dumps(trail, default=str)
    return any(c in corpus for c in claims)


async def record_test_verdict(
    session_id: str,
    sandbox_id: str | None,
    definition_slug: str,
    verdict: str,
    reasoning: str,
    inputs_used: dict | None = None,
    evidence: dict | None = None,
    duration_ms: int | None = None,
    confidence: float | None = None,
    observations: Any = None,
    # Provenance — injected by the executor, never by the model.
    model_id: str | None = None,
    model_params: dict | None = None,
    release_tag: str | None = None,
    image_tag: str | None = None,
    contracts_version: str | None = None,
) -> dict[str, Any]:
    """Insert/upsert one row into ai.test_verdicts with validation + provenance."""
    if verdict not in VALID_VERDICTS:
        return {"success": False,
                "error": f"verdict must be one of {VALID_VERDICTS}, got {verdict!r}"}
    if not definition_slug or not definition_slug.strip():
        return {"success": False, "error": "definition_slug must not be empty"}
    if not reasoning or not reasoning.strip():
        return {"success": False, "error": "reasoning must not be empty"}
    if not session_id:
        return {"success": False, "error": "no session_id on this executor"}
    if confidence is not None:
        try:
            confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            confidence = None

    pool = await get_pool()
    if pool is None:
        return {"success": False, "error": "no DB pool"}

    async with pool.acquire() as conn:
        async with conn.transaction():
            try:
                trail, ids, truncated, mutating = await _claim_trail(conn, session_id)
            except Exception as exc:
                log.warning("trail claim failed for %s: %s", definition_slug, exc)
                trail, ids, truncated, mutating = [], [], False, 0

            # ── VALIDATION GATE ─────────────────────────────────────────────
            original = verdict
            notes: list[str] = []
            if verdict in ("passed", "failed") and len(trail) == 0:
                verdict = "inconclusive"
                notes.append(
                    f"Auto-downgraded from '{original}': no execution trail — a verdict "
                    "cannot be passed/failed without at least one tool call attributable "
                    "to this test.")
            ev_validated = _evidence_validated(reasoning, evidence, observations, trail)
            if verdict in ("passed", "failed") and not ev_validated:
                notes.append(
                    "Evidence not corroborated: no concrete literal (tx hash / value) in "
                    "the reasoning or evidence was found in the captured trail.")
            if verdict in ("passed", "failed") and confidence is None:
                notes.append("No confidence score provided.")
            auto_downgraded_from = original if verdict != original else None
            validation_notes = " ".join(notes) or None

            # ── Frozen definition snapshot (version-drift-proof audit) ───────
            snapshot = None
            try:
                drow = await conn.fetchrow(
                    "SELECT name, version, definition_parsed FROM tests.definitions WHERE slug=$1",
                    definition_slug)
                if drow:
                    parsed = drow["definition_parsed"]
                    if isinstance(parsed, str):
                        parsed = json.loads(parsed)
                    parsed = parsed or {}
                    snapshot = {
                        "name": drow["name"], "version": drow["version"],
                        "assertions": parsed.get("assertions"),
                        "expected_behaviour": parsed.get("expected_behaviour")
                                              or parsed.get("expected"),
                        "steps": parsed.get("steps"),
                    }
            except Exception as exc:
                log.debug("definition snapshot failed: %s", exc)

            merged_evidence = dict(evidence or {})
            if trail:
                merged_evidence["execution_trail"] = trail

            row = await conn.fetchrow(
                """
                INSERT INTO ai.test_verdicts
                  (session_id, sandbox_id, definition_slug, verdict, reasoning,
                   inputs_used, evidence, duration_ms, confidence, observations,
                   evidence_validated, validation_notes, auto_downgraded_from,
                   trail_step_count, trail_mutating_count, trail_truncated,
                   definition_snapshot, model_id, model_params,
                   release_tag, image_tag, contracts_version)
                VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8,$9,$10::jsonb,
                        $11,$12,$13,$14,$15,$16,$17::jsonb,$18,$19::jsonb,$20,$21,$22)
                ON CONFLICT (session_id, definition_slug) DO UPDATE SET
                  verdict=EXCLUDED.verdict, reasoning=EXCLUDED.reasoning,
                  inputs_used=EXCLUDED.inputs_used, evidence=EXCLUDED.evidence,
                  duration_ms=EXCLUDED.duration_ms, confidence=EXCLUDED.confidence,
                  observations=EXCLUDED.observations,
                  evidence_validated=EXCLUDED.evidence_validated,
                  validation_notes=EXCLUDED.validation_notes,
                  auto_downgraded_from=EXCLUDED.auto_downgraded_from,
                  trail_step_count=EXCLUDED.trail_step_count,
                  trail_mutating_count=EXCLUDED.trail_mutating_count,
                  trail_truncated=EXCLUDED.trail_truncated,
                  definition_snapshot=EXCLUDED.definition_snapshot,
                  model_id=EXCLUDED.model_id, model_params=EXCLUDED.model_params,
                  release_tag=EXCLUDED.release_tag, image_tag=EXCLUDED.image_tag,
                  contracts_version=EXCLUDED.contracts_version, created_at=now()
                RETURNING id, created_at
                """,
                session_id, sandbox_id, definition_slug, verdict, reasoning,
                json.dumps(inputs_used) if inputs_used is not None else None,
                json.dumps(merged_evidence) if merged_evidence else None,
                duration_ms, confidence,
                json.dumps(observations) if observations is not None else None,
                ev_validated, validation_notes, auto_downgraded_from,
                len(trail), mutating, truncated,
                json.dumps(snapshot) if snapshot else None,
                model_id, json.dumps(model_params) if model_params else None,
                release_tag, image_tag, contracts_version,
            )
            verdict_id = row["id"]

            # ── Immutable verdict ↔ invocation link + correct slug tag ───────
            if ids:
                await conn.execute(
                    """
                    UPDATE ai.tool_invocations
                    SET verdict_id = $1, definition_slug = $2
                    WHERE id = ANY($3::uuid[]) AND verdict_id IS NULL
                    """,
                    verdict_id, definition_slug, ids,
                )

    log.info("Verdict %s → %s (session=%s, trail=%d, mutating=%d, validated=%s%s)",
             definition_slug, verdict, session_id, len(trail), mutating, ev_validated,
             f", downgraded from {auto_downgraded_from}" if auto_downgraded_from else "")
    return {
        "success": True,
        "verdict_id": str(verdict_id),
        "definition_slug": definition_slug,
        "verdict": verdict,
        "trail_steps_captured": len(trail),
        "evidence_validated": ev_validated,
        **({"auto_downgraded_from": auto_downgraded_from,
            "validation_notes": validation_notes} if auto_downgraded_from else {}),
        "created_at": row["created_at"].isoformat(),
    }


async def record_test_plan(
    session_id: str,
    definition_slug: str,
    objective: str,
    success_criteria: str | None = None,
    failure_criteria: str | None = None,
    planned_steps: Any = None,
) -> dict[str, Any]:
    """Persist the agent's understanding + plan for a test BEFORE executing it.
    One row per (session, test); upserts so a refined plan replaces the draft."""
    if not session_id:
        return {"success": False, "error": "no session_id on this executor"}
    if not definition_slug or not definition_slug.strip():
        return {"success": False, "error": "definition_slug must not be empty"}
    if not objective or not objective.strip():
        return {"success": False, "error": "objective must not be empty"}
    pool = await get_pool()
    if pool is None:
        return {"success": False, "error": "no DB pool"}
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO ai.test_plans
                  (session_id, definition_slug, objective, success_criteria,
                   failure_criteria, planned_steps)
                VALUES ($1,$2,$3,$4,$5,$6::jsonb)
                ON CONFLICT (session_id, definition_slug) DO UPDATE SET
                  objective=EXCLUDED.objective, success_criteria=EXCLUDED.success_criteria,
                  failure_criteria=EXCLUDED.failure_criteria, planned_steps=EXCLUDED.planned_steps,
                  created_at=now()
                RETURNING id
                """,
                session_id, definition_slug, objective, success_criteria,
                failure_criteria,
                json.dumps(planned_steps) if planned_steps is not None else None,
            )
        return {"success": True, "plan_id": str(row["id"]), "definition_slug": definition_slug}
    except Exception as exc:
        log.exception("record_test_plan failed")
        return {"success": False, "error": f"insert failed: {exc}"}
