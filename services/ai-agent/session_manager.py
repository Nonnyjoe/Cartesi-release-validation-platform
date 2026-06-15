"""
services/ai-agent/session_manager.py
Manages the lifecycle of all three session modes.
Persists session state to ai.sessions in PostgreSQL.
Streams events to the publisher (RabbitMQ + Redis).
"""
import asyncio
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from agent_loop import AgentLoop
from context.assembler import build_system_prompt
from crypto import decrypt_key
from tool_executor import ToolExecutor
from tools.reporting import get_all_findings, clear_findings

log = logging.getLogger("ai-agent.session_manager")

DATABASE_URL = os.environ.get("DATABASE_URL", "").replace(
    "postgresql://", "postgresql+asyncpg://"
)
engine       = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class SessionManager:
    """
    One SessionManager instance handles one AI session from start to finish.
    """

    def __init__(self, request: dict, publish_event: Callable[[dict], None]):
        self.session_id   = request.get("session_id") or str(uuid.uuid4())
        self.run_id       = request.get("run_id")
        self.sandbox_id   = request.get("sandbox_id")
        self.mode         = request["mode"]
        self.goal         = request.get("goal")
        # 'runner' = delegate via trigger_test; 'ai_manual' = the agent reads each
        # definition, decides inputs, executes steps itself, records verdicts.
        self.execution_mode = request.get("execution_mode") or "runner"
        self.selected_tests = request.get("selected_tests") or []
        # bootstrap=true: a provisioning run was queued at session creation; the
        # agent must wait for the sandbox to be ready before its loop starts.
        self.bootstrap    = bool(request.get("bootstrap"))
        self.base_test_id = request.get("base_test_id")
        self.release_tag  = request.get("release_tag") or "unknown"
        self.pr_summaries = request.get("pr_summaries") or []
        self.changelog    = request.get("changelog")
        self.created_by   = request.get("created_by")
        self.anvil_port   = request.get("anvil_port", 8545)
        self.node_port    = request.get("node_port", 5004)
        self.graphql_port = request.get("graphql_port", 4000)
        self.docker_network = request.get("docker_network")
        self.sandbox_metadata: dict = {}
        self._publish     = publish_event

    async def _load_sandbox_ports(self) -> None:
        """If sandbox_id is set, replace the request-provided default ports with the
        real ones and capture the deployment metadata (addresses, container names)."""
        if not self.sandbox_id:
            return
        async with SessionLocal() as db:
            row = await db.execute(
                text(
                    "SELECT anvil_port, node_port, graphql_port, docker_network, metadata "
                    "FROM sandbox.sandboxes WHERE id = :sid",
                ),
                {"sid": self.sandbox_id},
            )
            r = row.fetchone()
        if not r:
            return
        if r.anvil_port:     self.anvil_port     = r.anvil_port
        if r.node_port:      self.node_port      = r.node_port
        if r.graphql_port:   self.graphql_port   = r.graphql_port
        if r.docker_network: self.docker_network = r.docker_network
        meta = r.metadata or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except Exception:
                meta = {}
        self.sandbox_metadata = meta
        log.info(
            "Loaded sandbox ports: anvil=%s node=%s graphql=%s network=%s",
            self.anvil_port, self.node_port, self.graphql_port, self.docker_network,
        )

    def _sandbox_manifest(self) -> str:
        """Per-sandbox deployment manifest injected into the system prompt so the
        agent knows exactly which app/contracts it is testing against — paired with
        the static student-tracker behaviour doc (test-app-behavior.md) in project knowledge."""
        if not self.sandbox_id:
            return ""
        meta  = self.sandbox_metadata or {}
        short = self.sandbox_id[:8]
        app_label = meta.get("app_name") or "test-app"
        lines = [
            "## Sandbox Deployment Manifest (this session's environment)",
            "",
            f"The deployed application (registered as `{app_label}`) is the "
            "**student-tracker** dApp described in the application behaviour doc in "
            "project knowledge: JSON advance actions (`ping`/`register`/`withdraw`), "
            "portal-deposit ledger, string inspect routes, and REAL vouchers via "
            "`withdraw` after a portal deposit. Malformed payloads are REJECTED by "
            "design — that's app behaviour, not a node bug.",
            "",
            f"- sandbox_id: `{self.sandbox_id}`",
            f"- containers: advancer `rvp-advancer-{short}`, anvil `rvp-anvil-{short}`"
            + (f", cli `{meta['cli_container_name']}`" if meta.get("cli_container_name") else ""),
            f"- ports (host-mapped): anvil={self.anvil_port}, jsonrpc={self.node_port}, "
            f"graphql={self.graphql_port}",
            f"- node major version: {meta.get('node_major_version', 2)}",
        ]
        addr_keys = [
            ("app_address",            "Application"),
            ("inputbox_address",       "InputBox"),
            ("ether_portal_address",   "EtherPortal"),
            ("erc20_portal_address",   "ERC20Portal"),
            ("erc721_portal_address",  "ERC721Portal"),
            ("erc1155_portal_address", "ERC1155Portal"),
            ("erc20_token_address",    "Test ERC20 token"),
            ("erc721_token_address",   "Test ERC721 token"),
            ("erc1155_token_address",  "Test ERC1155 token"),
        ]
        addrs = [(label, meta.get(k)) for k, label in addr_keys if meta.get(k)]
        if addrs:
            lines.append("- deployed addresses:")
            lines += [f"  - {label}: `{addr}`" for label, addr in addrs]
        else:
            lines.append(
                "- deployed addresses: not recorded in sandbox metadata — discover them "
                "via `cartesi_listApplications` and the contracts-devnet project knowledge."
            )
        lines.append(
            "\nNever invent addresses: use this manifest first, then "
            "`cartesi_listApplications` / project knowledge as fallback."
        )
        return "\n".join(lines)

    async def _manual_plan_message(self) -> str:
        """Initial message for execution_mode='ai_manual': a phase-grouped work plan.
        The agent decides the final execution order — health/environment checks
        first, destructive or stress tests last."""
        # Enrich slugs with phase + name so the agent can sort sensibly without
        # burning tool calls on discovery.
        info: dict[str, tuple[str, str]] = {}
        try:
            async with SessionLocal() as db:
                rows = (await db.execute(
                    text("""
                        SELECT slug, COALESCE(phase, 'Unphased') AS phase, name
                        FROM tests.definitions WHERE slug = ANY(:slugs)
                    """),
                    {"slugs": list(self.selected_tests)},
                )).fetchall()
            info = {r.slug: (r.phase, r.name) for r in rows}
        except Exception as exc:
            log.warning("Could not enrich plan with phases: %s", exc)

        by_phase: dict[str, list[str]] = {}
        for slug in self.selected_tests:
            phase, name = info.get(slug, ("Unphased", ""))
            by_phase.setdefault(phase, []).append(
                f"  - `{slug}`" + (f" — {name}" if name else ""))
        plan = "\n".join(
            f"{phase} ({len(items)} tests):\n" + "\n".join(items)
            for phase, items in by_phase.items()
        )

        goal_line = f"\nAdditional instructions from the operator: {self.goal}\n" if self.goal else ""
        return (
            f"Begin MANUAL validation of Cartesi rollups node release {self.release_tag}.\n"
            f"{goal_line}\n"
            "You must execute each of the following selected tests YOURSELF — do NOT use "
            "`trigger_test`. For each test, follow this protocol IN ORDER:\n"
            "1. `read_test_definition` to load it; study the Steps, assertions and Expected Behaviour.\n"
            "2. `record_test_plan` — persist your objective, success_criteria, failure_criteria "
            "and ordered planned_steps BEFORE executing. This is your proof of understanding.\n"
            "3. Decide the concrete inputs yourself (payloads, amounts, CLI args) — vary them "
            "meaningfully rather than copying defaults, and note why. The deployed application's "
            "semantics (see the Sandbox Deployment Manifest and the application behaviour doc) "
            "define what outputs your inputs must produce.\n"
            "4. Execute every step with primitive tools (run_cli_command, call_jsonrpc, "
            "run_cast_command, send_advance_input, call_inspect, read_logs, ...).\n"
            "5. Verify each expectation yourself against what you observe.\n"
            "6. Record exactly one `record_test_verdict` with reasoning, inputs_used, "
            "observations (your interpretations), evidence (cite ≥1 concrete value from your "
            "tool outputs), and a `confidence` 0.0–1.0. Call `report_finding` for any node bug.\n\n"
            f"Selected tests, grouped by phase:\n{plan}\n\n"
            "VALIDATION GATE (important): a 'passed'/'failed' verdict with NO executed tool "
            "calls for that test is automatically downgraded to 'inconclusive'. You cannot pass "
            "or fail a test you did not execute — actually run the steps. Evidence is "
            "cross-checked against your captured trail.\n\n"
            "YOU decide the execution order: run environment/health checks first, then "
            "functional flows (inputs, outputs, vouchers, epochs), and stress/limit tests "
            "last so earlier results aren't polluted. State your chosen order before you "
            "start. Budget your tool calls across ALL tests — if running low, prefer honest "
            "'inconclusive'/'blocked' verdicts over leaving tests unrecorded.\n\n"
            "Keep narration MINIMAL: at most one short line between tool calls — your analysis "
            "belongs in the verdict's reasoning/observations, not the stream. Every tool call "
            "you make for a test is auto-captured into that verdict's execution trail (exact "
            "inputs + outputs), so never re-quote tool output in text or evidence. Start with "
            "`get_node_state`, and finish with a one-line-per-test verdict summary."
        )

    async def _record_missing_verdicts(self) -> int:
        """After a manual session ends, write 'blocked' verdicts for any selected
        test the agent never recorded (budget/time ran out, crash, …) so the
        verdict table is always complete. Returns the number of rows written."""
        if self.execution_mode != "ai_manual" or not self.selected_tests:
            return 0
        try:
            async with SessionLocal() as db:
                rows = (await db.execute(
                    text("SELECT definition_slug FROM ai.test_verdicts WHERE session_id = :sid"),
                    {"sid": self.session_id},
                )).fetchall()
                recorded = {r.definition_slug for r in rows}
                missing = [s for s in self.selected_tests if s not in recorded]
                for slug in missing:
                    await db.execute(
                        text("""
                            INSERT INTO ai.test_verdicts
                              (session_id, sandbox_id, definition_slug, verdict, reasoning)
                            VALUES (:sid, :sbx, :slug, 'blocked',
                                    'Auto-recorded: the session ended (tool/time budget or '
                                    'failure) before the agent reached this test.')
                            ON CONFLICT (session_id, definition_slug) DO NOTHING
                        """),
                        {"sid": self.session_id, "sbx": self.sandbox_id, "slug": slug},
                    )
                await db.commit()
            for slug in missing:
                self._emit("verdict", definition_slug=slug, verdict="blocked",
                           reasoning="Auto-recorded: session ended before this test was reached.")
            if missing:
                log.info("Auto-recorded %d blocked verdicts for session %s",
                         len(missing), self.session_id)
            return len(missing)
        except Exception as exc:
            log.warning("Could not auto-record missing verdicts: %s", exc)
            return 0

    def _manual_max_tool_calls(self) -> int | None:
        """Manual execution budget. Multi-step flows (register → deposit →
        withdraw → epoch → execute voucher) need ~15 calls plus session
        overhead; cap at the collaborative ceiling."""
        if self.execution_mode != "ai_manual" or not self.selected_tests:
            return None
        return min(200, max(60, 15 * len(self.selected_tests) + 15))

    def _manual_max_duration(self) -> int | None:
        """~3 min per test, floor 10 min, ceiling 1 h (the collaborative limit)."""
        if self.execution_mode != "ai_manual" or not self.selected_tests:
            return None
        return min(3600, max(600, 180 * len(self.selected_tests)))

    def _build_executor(self) -> ToolExecutor:
        return ToolExecutor(
            sandbox_id=self.sandbox_id,
            anvil_port=self.anvil_port,
            node_port=self.node_port,
            graphql_port=self.graphql_port,
            session_id=self.session_id,
            docker_network=self.docker_network,
        )

    def _excluded_tools(self) -> list[str]:
        """Tool schemas to omit from the Claude request for this session.
        Fewer schemas = fewer prompt tokens AND fewer wrong-tool choices."""
        excluded: list[str] = []
        if self.execution_mode == "ai_manual":
            # Manual execution forbids trigger_test outright (the prompt says so —
            # not sending the schema enforces it for free).
            excluded.append("trigger_test")
        if self.bootstrap or self.sandbox_id:
            # The environment is managed by the platform for this session; the
            # agent must not provision or tear down sandboxes itself.
            excluded += ["provision_sandbox", "teardown_sandbox"]
        return excluded

    # ── Bootstrap phase ────────────────────────────────────────────────────────

    BOOTSTRAP_TIMEOUT_S   = int(os.environ.get("AI_BOOTSTRAP_TIMEOUT_S", "900"))
    BOOTSTRAP_POLL_S      = 5
    BOOTSTRAP_LOG_BATCH   = 8     # max provisioning log lines relayed per poll

    async def _bootstrap_environment(self) -> None:
        """Wait for the session's provisioning run to produce a ready sandbox,
        relaying progress + provisioning logs to the session's event stream.
        Sets self.sandbox_id and flips the session row to 'active' on success.
        Raises RuntimeError on provisioning failure or timeout."""
        if not self.run_id:
            raise RuntimeError("bootstrap requested but the session has no run_id")

        self._emit("bootstrap_started",
                   run_id=self.run_id,
                   release_tag=self.release_tag,
                   message="Provisioning sandbox environment (contracts, tokens, node, app)…")

        start = time.monotonic()
        last_status: str | None = None
        last_log_ts = None
        while time.monotonic() - start < self.BOOTSTRAP_TIMEOUT_S:
            async with SessionLocal() as db:
                # User may cancel from the dashboard while provisioning is in
                # flight — stop waiting and leave the 'aborted' status intact.
                sess = (await db.execute(
                    text("SELECT status FROM ai.sessions WHERE id = :id"),
                    {"id": self.session_id},
                )).fetchone()
                if sess and sess.status == "aborted":
                    raise asyncio.CancelledError("session aborted during bootstrap")
                row = (await db.execute(
                    text("""
                        SELECT id, status, metadata, failure_reason
                        FROM sandbox.sandboxes WHERE run_id = :rid
                        ORDER BY provisioned_at DESC NULLS LAST LIMIT 1
                    """),
                    {"rid": self.run_id},
                )).fetchone()
                log_q = """
                    SELECT source, level, message, ts FROM orchestrator.run_logs
                    WHERE run_id = :rid {after} ORDER BY ts ASC LIMIT :lim
                """.format(after="AND ts > :after" if last_log_ts else "")
                params: dict = {"rid": self.run_id, "lim": self.BOOTSTRAP_LOG_BATCH}
                if last_log_ts:
                    params["after"] = last_log_ts
                log_rows = (await db.execute(text(log_q), params)).fetchall()

            for L in log_rows:
                last_log_ts = L.ts
                self._emit("bootstrap_log", source=L.source,
                           message=str(L.message)[:300])

            status = row.status if row else None
            if status != last_status:
                self._emit("bootstrap_progress",
                           sandbox_status=status or "queued",
                           sandbox_id=str(row.id) if row else None,
                           elapsed_s=int(time.monotonic() - start))
                last_status = status

            if status == "ready":
                self.sandbox_id = str(row.id)
                meta = row.metadata or {}
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:
                        meta = {}
                async with SessionLocal() as db:
                    await db.execute(
                        text("""
                            UPDATE ai.sessions
                            SET sandbox_id = :sbx, status = 'active'
                            WHERE id = :id
                        """),
                        {"sbx": self.sandbox_id, "id": self.session_id},
                    )
                    await db.commit()
                self._emit("bootstrap_ready",
                           sandbox_id=self.sandbox_id,
                           app_address=meta.get("app_address"),
                           elapsed_s=int(time.monotonic() - start),
                           message=f"Sandbox ready in {int(time.monotonic() - start)}s — starting agent.")
                return

            if status == "failed":
                reason = (row.failure_reason or "unknown") if row else "unknown"
                raise RuntimeError(f"Sandbox provisioning failed: {reason[:400]}")

            await asyncio.sleep(self.BOOTSTRAP_POLL_S)

        raise RuntimeError(
            f"Bootstrap timed out after {self.BOOTSTRAP_TIMEOUT_S}s waiting for a ready sandbox")

    async def _load_provenance(self, loop) -> dict:
        """Reproducibility provenance stamped onto every verdict: model id+params
        (from the loop), and release/image/contracts from the bound run/sandbox."""
        prov = {
            "model_id": getattr(loop, "model", None),
            "model_params": getattr(loop, "model_params", None),
            "release_tag": self.release_tag,
            "image_tag": None,
            "contracts_version": None,
        }
        try:
            async with SessionLocal() as db:
                if self.run_id:
                    r = (await db.execute(
                        text("SELECT release_tag, image_tag FROM orchestrator.runs WHERE id = :id"),
                        {"id": self.run_id},
                    )).fetchone()
                    if r:
                        prov["release_tag"] = r.release_tag or prov["release_tag"]
                        prov["image_tag"] = r.image_tag
                # contracts_version lives in sandbox metadata when present.
                cv = (self.sandbox_metadata or {}).get("contracts_version")
                if cv:
                    prov["contracts_version"] = cv
        except Exception as exc:
            log.debug("provenance load partial: %s", exc)
        return prov

    async def _load_credentials(self) -> tuple[str | None, str]:
        """Return (api_key, model_id) from the session row.

        Both may be None/empty if the session was created before per-session keys
        existed — AgentLoop falls back to the global ANTHROPIC_API_KEY in that case.
        """
        async with SessionLocal() as db:
            row = await db.execute(
                text(
                    "SELECT anthropic_key_ciphertext, anthropic_key_nonce, model_id "
                    "FROM ai.sessions WHERE id = :id",
                ),
                {"id": self.session_id},
            )
            r = row.fetchone()
            if not r:
                return None, "claude-opus-4-6"
            try:
                api_key = decrypt_key(r.anthropic_key_ciphertext, r.anthropic_key_nonce)
            except Exception as exc:
                log.error("Failed to decrypt session key for %s: %s", self.session_id, exc)
                api_key = None
            return api_key, (r.model_id or "claude-opus-4-6")

    # Internal AgentLoop event names → the dashboard's WS protocol
    # (Session.tsx switches on these exact event_type strings and reads
    # the fields from a `payload` object — see types.ts WSEventType).
    _EVENT_NAME_MAP = {
        "text_delta":       "ai.token",
        "tool_call":        "ai.tool_call",
        "tool_result":      "ai.tool_result",
        "finding":          "ai.finding",
        "verdict":          "ai.verdict",
        "session_complete": "ai.completed",
        "limit_reached":    "ai.limit_reached",
    }
    _PAYLOAD_KEY_MAP = {
        "tool_name":   "tool",
        "tool_input":  "input",
        "tool_output": "result",
    }

    def _emit(self, event_type: str, **kwargs):
        """Emit a session event to the publisher in the dashboard WS shape."""
        self._publish({
            "event_id":   str(uuid.uuid4()),
            "session_id": self.session_id,
            "run_id":     self.run_id,
            "service":    "ai-agent",
            "ts":         datetime.now(tz=timezone.utc).isoformat(),
            "event_type": self._EVENT_NAME_MAP.get(event_type, event_type),
            "payload":    {self._PAYLOAD_KEY_MAP.get(k, k): v for k, v in kwargs.items()},
        })

    async def _save_session(self, status: str, summary: dict | None = None,
                            transcript: dict | None = None):
        findings = get_all_findings()
        # Persist the reasoning transcript (review §4/§5: the chain-of-thought was
        # previously discarded — message_history always written as '[]'). On
        # interim saves (status='active') there is no transcript yet; keep '[]'.
        history_json = json.dumps(transcript, default=str) if transcript else "[]"
        async with SessionLocal() as db:
            await db.execute(
                text("""
                    INSERT INTO ai.sessions
                      (id, sandbox_id, run_id, mode, goal, base_test_id, status,
                       message_history, tool_calls, findings, created_by,
                       tool_call_count, total_tokens, execution_mode, selected_tests)
                    VALUES
                      (:id, :sbx, :run, :mode, :goal, :base, :status,
                       CAST(:history AS jsonb), '[]'::jsonb, CAST(:findings AS jsonb), :by, :tc, :tok,
                       :exec_mode, :selected)
                    ON CONFLICT (id) DO UPDATE SET
                      status=EXCLUDED.status,
                      findings=EXCLUDED.findings,
                      -- only overwrite the transcript when a real one is supplied
                      message_history=CASE WHEN :has_transcript
                                           THEN EXCLUDED.message_history
                                           ELSE ai.sessions.message_history END,
                      tool_call_count=EXCLUDED.tool_call_count,
                      total_tokens=EXCLUDED.total_tokens,
                      execution_mode=EXCLUDED.execution_mode,
                      selected_tests=COALESCE(ai.sessions.selected_tests, EXCLUDED.selected_tests),
                      closed_at=now()
                """),
                {
                    "id":      self.session_id,
                    "exec_mode": self.execution_mode,
                    "selected":  self.selected_tests or None,
                    "sbx":     self.sandbox_id,
                    "run":     self.run_id,
                    "mode":    self.mode,
                    "goal":    self.goal,
                    "base":    self.base_test_id,
                    "status":  status,
                    "history": history_json,
                    "has_transcript": transcript is not None,
                    "findings": json.dumps(findings),
                    "by":      self.created_by,
                    "tc":      summary.get("tool_call_count", 0) if summary else 0,
                    "tok":     summary.get("total_tokens", 0) if summary else 0,
                },
            )
            await db.commit()

    async def run_autonomous(self) -> dict:
        """
        Autonomous mode: agent is given a goal and runs completely solo.
        """
        log.info("Starting AUTONOMOUS session %s for run %s", self.session_id, self.run_id)
        clear_findings()

        if self.bootstrap and not self.sandbox_id:
            try:
                await self._bootstrap_environment()
            except Exception as exc:
                log.exception("Bootstrap failed for session %s: %s", self.session_id, exc)
                await self._save_session("failed")
                self._emit("session_failed", error=f"bootstrap: {exc}"[:500])
                raise

        await self._load_sandbox_ports()   # before prompt build: manifest needs metadata

        system_prompt = build_system_prompt(
            mode="autonomous",
            release_tag=self.release_tag,
            pr_summaries=self.pr_summaries,
            changelog=self.changelog,
            goal=self.goal,
            sandbox_id=self.sandbox_id,
            execution_mode=self.execution_mode,
            sandbox_manifest=self._sandbox_manifest(),
        )

        executor = self._build_executor()

        def on_event(evt: dict):
            self._emit(evt.get("type", "unknown"), **{k: v for k, v in evt.items() if k != "type"})

        api_key, model_id = await self._load_credentials()
        loop = AgentLoop(system_prompt, executor, "autonomous", on_event,
                         api_key=api_key, model=model_id,
                         max_tool_calls=self._manual_max_tool_calls(),
                         max_duration=self._manual_max_duration(),
                         exclude_tools=self._excluded_tools())
        # Stamp reproducibility provenance onto every verdict this session records.
        executor.provenance = await self._load_provenance(loop)

        if self.execution_mode == "ai_manual" and self.selected_tests:
            initial_message = await self._manual_plan_message()
        else:
            initial_message = (
                f"Begin validation of Cartesi rollups node release {self.release_tag}.\n"
                f"Goal: {self.goal or 'Comprehensive release validation.'}\n\n"
                "Start by checking the node state, then systematically test all key components."
            )

        await self._save_session("active")
        try:
            summary = await loop.run(initial_message)
        except Exception as exc:
            # Never leave the session stuck in 'active' — mark failed + notify.
            log.exception("Autonomous session %s crashed: %s", self.session_id, exc)
            await self._record_missing_verdicts()
            await self._save_session("failed", {
                "tool_call_count": loop.tool_call_count,
                "total_tokens":    loop.total_tokens,
            }, transcript=loop.transcript())
            self._emit("session_failed", error=str(exc)[:500])
            raise
        await self._record_missing_verdicts()
        await self._save_session("completed", summary, transcript=loop.transcript())

        self._emit("session_completed",
                   total_tokens=summary["total_tokens"],
                   tool_call_count=summary["tool_call_count"],
                   findings_count=summary["findings_count"])

        return summary

    async def run_collaborative(self, user_message_queue: asyncio.Queue) -> dict:
        """
        Collaborative mode: user picks a test, agent proposes → user approves → agent executes.
        user_message_queue: asyncio.Queue that receives user messages mid-session.
        """
        import asyncio
        log.info("Starting COLLABORATIVE session %s", self.session_id)
        clear_findings()

        if self.bootstrap and not self.sandbox_id:
            try:
                await self._bootstrap_environment()
            except Exception as exc:
                log.exception("Bootstrap failed for session %s: %s", self.session_id, exc)
                await self._save_session("failed")
                self._emit("session_failed", error=f"bootstrap: {exc}"[:500])
                raise

        await self._load_sandbox_ports()

        system_prompt = build_system_prompt(
            mode="collaborative",
            release_tag=self.release_tag,
            pr_summaries=self.pr_summaries,
            changelog=self.changelog,
            goal=self.goal,
            base_test_slug=self.base_test_id,
            sandbox_id=self.sandbox_id,
            execution_mode=self.execution_mode,
            sandbox_manifest=self._sandbox_manifest(),
        )

        executor = self._build_executor()

        def on_event(evt: dict):
            self._emit(evt.get("type", "unknown"), **{k: v for k, v in evt.items() if k != "type"})

        api_key, model_id = await self._load_credentials()
        loop = AgentLoop(system_prompt, executor, "collaborative", on_event,
                         api_key=api_key, model=model_id,
                         exclude_tools=self._excluded_tools())
        executor.provenance = await self._load_provenance(loop)
        await self._save_session("active")

        # Kickoff message
        initial = (
            f"I'd like to work with you on validating release {self.release_tag}. "
            + (f"Start from the test: `{self.base_test_id}`." if self.base_test_id
               else "Let's start with an overview of what we should test.")
        )
        self.messages = [{"role": "user", "content": initial}]
        await loop.send_user_message(initial)

        # Message loop — process user messages until "done" or timeout
        while True:
            try:
                user_msg = await asyncio.wait_for(user_message_queue.get(), timeout=3600)
                if user_msg in ("__done__", "__timeout__"):
                    break
                await loop.send_user_message(user_msg)
            except asyncio.TimeoutError:
                log.info("Collaborative session %s timed out", self.session_id)
                break

        summary = {
            "tool_call_count": loop.tool_call_count,
            "total_tokens":    loop.total_tokens,
            "findings":        get_all_findings(),
            "findings_count":  len(get_all_findings()),
        }
        await self._save_session("completed", summary, transcript=loop.transcript())
        self._emit("session_completed", **summary)
        return summary

    async def run_interactive(self, user_message_queue) -> dict:
        """
        Interactive mode: AI-assisted terminal — user types commands, agent executes and explains.
        """
        import asyncio
        log.info("Starting INTERACTIVE session %s", self.session_id)
        clear_findings()

        if self.bootstrap and not self.sandbox_id:
            try:
                await self._bootstrap_environment()
            except Exception as exc:
                log.exception("Bootstrap failed for session %s: %s", self.session_id, exc)
                await self._save_session("failed")
                self._emit("session_failed", error=f"bootstrap: {exc}"[:500])
                raise

        await self._load_sandbox_ports()

        system_prompt = build_system_prompt(
            mode="interactive",
            release_tag=self.release_tag,
            pr_summaries=self.pr_summaries,
            changelog=self.changelog,
            sandbox_id=self.sandbox_id,
            sandbox_manifest=self._sandbox_manifest(),
        )

        executor = self._build_executor()

        def on_event(evt: dict):
            self._emit(evt.get("type", "unknown"), **{k: v for k, v in evt.items() if k != "type"})

        api_key, model_id = await self._load_credentials()
        loop = AgentLoop(system_prompt, executor, "interactive", on_event,
                         api_key=api_key, model=model_id,
                         exclude_tools=self._excluded_tools())
        executor.provenance = await self._load_provenance(loop)
        await self._save_session("active")

        self._emit("session_started", message="Interactive session ready. Type a command or ask a question.")

        while True:
            try:
                user_msg = await asyncio.wait_for(user_message_queue.get(), timeout=3600)
                if user_msg in ("__done__", "__timeout__"):
                    break
                await loop.send_user_message(user_msg)
            except asyncio.TimeoutError:
                log.info("Interactive session %s timed out", self.session_id)
                break

        summary = {
            "tool_call_count": loop.tool_call_count,
            "total_tokens":    loop.total_tokens,
            "findings":        get_all_findings(),
            "findings_count":  len(get_all_findings()),
        }
        await self._save_session("completed", summary, transcript=loop.transcript())
        self._emit("session_completed", **summary)
        return summary


    async def run_chaos(self, goal: str | None = None) -> dict:
        """Chaos mode — adversarial agent that injects faults to test node robustness.

        NOTE: not yet reachable from the dashboard/API (ai_mode enum and the
        /sessions Literal only allow autonomous/collaborative/interactive).
        Kept functional for direct invocation and future enablement.
        """
        log.info("Starting CHAOS session %s for run %s", self.session_id, self.run_id)
        clear_findings()

        await self._load_sandbox_ports()

        system_prompt = build_system_prompt(
            mode="chaos",
            release_tag=self.release_tag,
            pr_summaries=self.pr_summaries,
            changelog=self.changelog,
            goal=goal or self.goal,
            sandbox_id=self.sandbox_id,
            sandbox_manifest=self._sandbox_manifest(),
        )

        executor = self._build_executor()

        def on_event(evt: dict):
            self._emit(evt.get("type", "unknown"), **{k: v for k, v in evt.items() if k != "type"})

        api_key, model_id = await self._load_credentials()
        loop = AgentLoop(system_prompt, executor, "chaos", on_event,
                         api_key=api_key, model=model_id)

        initial_message = (
            goal or self.goal or
            "Begin chaos testing. Inject faults systematically: malformed inputs, "
            "concurrent stress, container restarts, and network partitions. "
            "Report every finding via report_finding."
        )

        summary = await loop.run(initial_message)
        self._emit("session_completed", **{
            k: summary[k] for k in ("total_tokens", "tool_call_count", "findings_count")
        })
        return summary

import asyncio  # noqa: E402 (needed for type hints above)
