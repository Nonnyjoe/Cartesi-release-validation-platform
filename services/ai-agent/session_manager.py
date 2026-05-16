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
import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from agent_loop import AgentLoop
from context.assembler import build_system_prompt
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
        self.sandbox_id   = request["sandbox_id"]
        self.mode         = request["mode"]
        self.goal         = request.get("goal")
        self.base_test_id = request.get("base_test_id")
        self.release_tag  = request["release_tag"]
        self.pr_summaries = request.get("pr_summaries") or []
        self.changelog    = request.get("changelog")
        self.created_by   = request.get("created_by")
        self.anvil_port   = request.get("anvil_port", 8545)
        self.node_port    = request.get("node_port", 5004)
        self.graphql_port = request.get("graphql_port", 4000)
        self._publish     = publish_event

    def _emit(self, event_type: str, **kwargs):
        """Emit a session event to the publisher."""
        self._publish({
            "event_id":   str(uuid.uuid4()),
            "session_id": self.session_id,
            "run_id":     self.run_id,
            "service":    "ai-agent",
            "ts":         datetime.now(tz=timezone.utc).isoformat(),
            "event_type": event_type,
            **kwargs,
        })

    async def _save_session(self, status: str, summary: dict | None = None):
        findings = get_all_findings()
        async with SessionLocal() as db:
            await db.execute(
                text("""
                    INSERT INTO ai.sessions
                      (id, sandbox_id, run_id, mode, goal, base_test_id, status,
                       message_history, tool_calls, findings, created_by,
                       tool_call_count, total_tokens)
                    VALUES
                      (:id, :sbx, :run, :mode, :goal, :base, :status,
                       '[]'::jsonb, '[]'::jsonb, CAST(:findings AS jsonb), :by, :tc, :tok)
                    ON CONFLICT (id) DO UPDATE SET
                      status=EXCLUDED.status,
                      findings=EXCLUDED.findings,
                      tool_call_count=EXCLUDED.tool_call_count,
                      total_tokens=EXCLUDED.total_tokens,
                      closed_at=now()
                """),
                {
                    "id":      self.session_id,
                    "sbx":     self.sandbox_id,
                    "run":     self.run_id,
                    "mode":    self.mode,
                    "goal":    self.goal,
                    "base":    self.base_test_id,
                    "status":  status,
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

        system_prompt = build_system_prompt(
            mode="autonomous",
            release_tag=self.release_tag,
            pr_summaries=self.pr_summaries,
            changelog=self.changelog,
            goal=self.goal,
            sandbox_id=self.sandbox_id,
        )

        executor = ToolExecutor(
            sandbox_id=self.sandbox_id,
            anvil_port=self.anvil_port,
            node_port=self.node_port,
            graphql_port=self.graphql_port,
        )

        def on_event(evt: dict):
            self._emit(evt.get("type", "unknown"), **{k: v for k, v in evt.items() if k != "type"})

        loop = AgentLoop(system_prompt, executor, "autonomous", on_event)

        initial_message = (
            f"Begin validation of Cartesi rollups node release {self.release_tag}.\n"
            f"Goal: {self.goal or 'Comprehensive release validation.'}\n\n"
            "Start by checking the node state, then systematically test all key components."
        )

        await self._save_session("active")
        summary = await loop.run(initial_message)
        await self._save_session("completed", summary)

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

        system_prompt = build_system_prompt(
            mode="collaborative",
            release_tag=self.release_tag,
            pr_summaries=self.pr_summaries,
            changelog=self.changelog,
            goal=self.goal,
            base_test_slug=self.base_test_id,
            sandbox_id=self.sandbox_id,
        )

        executor = ToolExecutor(
            sandbox_id=self.sandbox_id,
            anvil_port=self.anvil_port,
            node_port=self.node_port,
            graphql_port=self.graphql_port,
        )

        def on_event(evt: dict):
            self._emit(evt.get("type", "unknown"), **{k: v for k, v in evt.items() if k != "type"})

        loop = AgentLoop(system_prompt, executor, "collaborative", on_event)
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
        await self._save_session("completed", summary)
        self._emit("session_completed", **summary)
        return summary

    async def run_interactive(self, user_message_queue) -> dict:
        """
        Interactive mode: AI-assisted terminal — user types commands, agent executes and explains.
        """
        import asyncio
        log.info("Starting INTERACTIVE session %s", self.session_id)
        clear_findings()

        system_prompt = build_system_prompt(
            mode="interactive",
            release_tag=self.release_tag,
            pr_summaries=self.pr_summaries,
            changelog=self.changelog,
            sandbox_id=self.sandbox_id,
        )

        executor = ToolExecutor(
            sandbox_id=self.sandbox_id,
            anvil_port=self.anvil_port,
            node_port=self.node_port,
            graphql_port=self.graphql_port,
        )

        def on_event(evt: dict):
            self._emit(evt.get("type", "unknown"), **{k: v for k, v in evt.items() if k != "type"})

        loop = AgentLoop(system_prompt, executor, "interactive", on_event)
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
        await self._save_session("completed", summary)
        self._emit("session_completed", **summary)
        return summary


    async def run_chaos(self, goal: str | None = None) -> None:
        """Chaos mode — adversarial agent that injects faults to test node robustness."""
        initial_message = (
            goal or
            "Begin chaos testing. Inject faults systematically: malformed inputs, "
            "concurrent stress, container restarts, and network partitions. "
            "Report every finding via report_finding."
        )
        await self._run_session(initial_message, mode="chaos")

import asyncio  # noqa: E402 (needed for type hints above)
