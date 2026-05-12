"""
services/ai-agent/tool_executor.py
Receives a Claude tool_use block and dispatches it to the correct Python function.
Injects sandbox connection context into every tool call.
"""
import logging
from typing import Any

from tools.blockchain import send_advance_input, run_cast_command, verify_voucher
from tools.node import read_logs, get_node_state
from tools.graphql import query_graphql, call_inspect
from tools.payload_gen import generate_payload
from tools.time import advance_time
from tools.reporting import report_finding

log = logging.getLogger("ai-agent.tool_executor")


class ToolExecutor:
    """
    Wraps all agent tools and injects sandbox connection details so the agent
    loop only needs to pass tool name + input — not URLs or sandbox IDs.
    """

    def __init__(self, sandbox_id: str, anvil_port: int, node_port: int, graphql_port: int):
        self.sandbox_id    = sandbox_id
        self.anvil_rpc_url = f"http://localhost:{anvil_port}"
        self.node_http_url = f"http://localhost:{node_port}"
        self.graphql_url   = f"http://localhost:{graphql_port}/graphql"

    async def execute(self, tool_name: str, tool_input: dict) -> Any:
        """
        Dispatch a tool call. Returns a JSON-serialisable result dict.
        Never raises — catches all exceptions and returns an error dict.
        """
        log.info("Tool call: %s  input=%s", tool_name, str(tool_input)[:200])
        try:
            result = await self._dispatch(tool_name, tool_input)
            log.debug("Tool result: %s → %s", tool_name, str(result)[:300])
            return result
        except Exception as exc:
            log.exception("Unhandled error in tool %s: %s", tool_name, exc)
            return {"success": False, "error": f"Internal error: {exc}"}

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

        else:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}
