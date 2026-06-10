"""
services/ai-agent/tool_executor.py
Receives a Claude tool_use block and dispatches it to the correct Python function.
Injects sandbox connection context into every tool call.
"""
import logging
import os
from typing import Any

from tools.blockchain import send_advance_input, run_cast_command, verify_voucher
from tools.chaos_executor import execute_restart_component, execute_pause_network
from tools.node import read_logs, get_node_state
from tools.graphql import query_graphql, call_inspect
from tools.payload_gen import generate_payload
from tools.time import advance_time
from tools.reporting import report_finding

# New AI-operator tools
from tools.audit import record_invocation, AuditedCall
from tools.cli import run_cli_command
from tools.db_query import query_db
from tools.jsonrpc import call_jsonrpc
from tools.sandbox import provision_sandbox, teardown_sandbox
from tools.skill_lookup import lookup_skill
from tools.test_trigger import read_test_definition, trigger_test

log = logging.getLogger("ai-agent.tool_executor")

# Sandboxes expose host-mapped ports; reach them from inside containers via this host.
SANDBOX_HOST = os.environ.get("SANDBOX_HOST", "host.docker.internal")


class ToolExecutor:
    """
    Wraps all agent tools and injects sandbox connection details so the agent
    loop only needs to pass tool name + input — not URLs or sandbox IDs.
    """

    def __init__(self, sandbox_id: str, anvil_port: int, node_port: int, graphql_port: int,
                 session_id: str | None = None, docker_network: str | None = None):
        self.sandbox_id     = sandbox_id
        self.session_id     = session_id
        self.anvil_port     = anvil_port
        self.node_port      = node_port
        self.graphql_port   = graphql_port
        self.docker_network = docker_network
        self.anvil_rpc_url  = f"http://{SANDBOX_HOST}:{anvil_port}"
        self.node_http_url  = f"http://{SANDBOX_HOST}:{node_port}"
        self.graphql_url    = f"http://{SANDBOX_HOST}:{graphql_port}/graphql"

    def _chaos_ctx(self) -> dict:
        """Container names (Docker SDK accepts names where IDs are expected) +
        network for the chaos tools."""
        short = self.sandbox_id[:8] if self.sandbox_id else ""
        return {
            "docker_network": self.docker_network or "",
            "container_ids": {
                "node":  f"rvp-advancer-{short}",
                "anvil": f"rvp-anvil-{short}",
            },
        }

    async def execute(self, tool_name: str, tool_input: dict) -> Any:
        """Dispatch a tool call, record the invocation to ai.tool_invocations.

        Returns a JSON-serialisable result dict. Never raises.
        """
        log.info("Tool call: %s  input=%s", tool_name, str(tool_input)[:200])
        call = AuditedCall(self.session_id, tool_name, tool_input)
        with call:
            try:
                result = await self._dispatch(tool_name, tool_input)
                if isinstance(result, dict) and result.get("success") is False:
                    call.mark_error(result)
                else:
                    call.mark_ok(result)
                log.debug("Tool result: %s → %s", tool_name, str(result)[:300])
            except Exception as exc:
                log.exception("Unhandled error in tool %s: %s", tool_name, exc)
                result = {"success": False, "error": f"Internal error: {exc}"}
                call.mark_error(result)

        # Fire-and-forget audit write
        try:
            await record_invocation(
                self.session_id, call.tool_name, call.tool_input,
                call.output, call.status, call.elapsed_ms,
            )
        except Exception as exc:  # never bubble up
            log.debug("audit write failed: %s", exc)
        return result

    async def _dispatch(self, tool_name: str, inp: dict) -> Any:
        if tool_name == "send_advance_input":
            return await send_advance_input(
                payload=inp["payload"],
                anvil_rpc_url=self.anvil_rpc_url,
                node_http_url=self.node_http_url,
                app_address=inp.get("app_address", "0x0000000000000000000000000000000000000001"),
            )

        elif tool_name == "query_graphql":
            return await query_graphql(
                query=inp["query"],
                graphql_url=self.graphql_url,
                variables=inp.get("variables"),
            )

        elif tool_name == "call_inspect":
            return await call_inspect(
                payload=inp["payload"],
                node_http_url=self.node_http_url,
            )

        elif tool_name == "read_logs":
            return await read_logs(
                sandbox_id=self.sandbox_id,
                component=inp.get("component", "node"),
                tail=inp.get("tail", 100),
            )

        elif tool_name == "run_cast_command":
            return await run_cast_command(
                command=inp["command"],
                anvil_rpc_url=self.anvil_rpc_url,
                sandbox_id=self.sandbox_id or "",
            )

        elif tool_name == "generate_payload":
            return generate_payload(
                mode=inp.get("mode", "random"),
                size_bytes=inp.get("size_bytes", 32),
                structured_type=inp.get("structured_type"),
            )

        elif tool_name == "get_node_state":
            return await get_node_state(
                graphql_url=self.graphql_url,
                node_http_url=self.node_http_url,
            )

        elif tool_name == "verify_voucher":
            return await verify_voucher(
                input_index=inp["input_index"],
                voucher_index=inp["voucher_index"],
                graphql_url=self.graphql_url,
            )

        elif tool_name == "advance_time":
            return await advance_time(
                blocks=inp["blocks"],
                anvil_rpc_url=self.anvil_rpc_url,
            )

        elif tool_name == "report_finding":
            return report_finding(
                title=inp["title"],
                severity=inp["severity"],
                component=inp["component"],
                description=inp["description"],
                evidence=inp.get("evidence"),
                reproduction_steps=inp.get("reproduction_steps"),
            )

        # ── New AI-operator tools ────────────────────────────────────────
        elif tool_name == "trigger_test":
            return await trigger_test(
                session_id=self.session_id or "",
                sandbox_id=self.sandbox_id,
                definition_slug=inp["definition_slug"],
                parameter_overrides=inp.get("parameter_overrides") or {},
                wait_seconds=int(inp.get("wait_seconds", 90)),
            )

        elif tool_name == "read_test_definition":
            return await read_test_definition(slug=inp["definition_slug"])

        elif tool_name == "run_cli_command":
            return await run_cli_command(
                sandbox_id=self.sandbox_id,
                binary=inp["binary"],
                args=inp["args"],
                container=inp.get("container"),
            )

        elif tool_name == "call_jsonrpc":
            # node_port is the host-mapped JSON-RPC port; jsonrpc endpoint sits at /rpc
            return await call_jsonrpc(
                sandbox_id=self.sandbox_id,
                method=inp["method"],
                params=inp.get("params"),
                rpc_url=f"http://{SANDBOX_HOST}:{self.node_port}/rpc",
            )

        elif tool_name == "query_db":
            return await query_db(sql=inp["sql"])

        elif tool_name == "provision_sandbox":
            return await provision_sandbox(
                release_tag=inp.get("release_tag"),
                image_tag=inp.get("image_tag"),
                app_id=inp.get("app_id"),
            )

        elif tool_name == "teardown_sandbox":
            return await teardown_sandbox(run_id=inp["run_id"])

        elif tool_name == "lookup_skill":
            return lookup_skill(
                skill_name=inp["skill_name"],
                section=inp.get("section"),
            )

        # ── Chaos-mode tools ─────────────────────────────────────────────
        elif tool_name == "restart_component":
            return await execute_restart_component(inp, self._chaos_ctx())

        elif tool_name == "pause_network":
            return await execute_pause_network(inp, self._chaos_ctx())

        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
