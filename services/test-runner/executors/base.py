"""
services/test-runner/executors/base.py
Abstract base class for all assertion executors.
Adding a new assertion type = one new file implementing AssertionExecutor.

Port semantics by node major version
--------------------------------------
v1.x:
  node_port    → HTTP API (5004)
  graphql_port → GraphQL (4000)

v2.x (SDK compose stack):
  node_port    → jsonrpc-api  (10011) — GraphQL + JSON-RPC endpoint
  graphql_port → advancer     (10012) — Inspect API endpoint

v2.x GraphQL is served by jsonrpc-api at http://node_port/graphql (NOT graphql_port).
"""
import logging
import os
from abc import ABC, abstractmethod
from typing import Any

import httpx

# On Docker for Mac / Docker Desktop, containers access host-mapped ports
# via host.docker.internal rather than localhost.
SANDBOX_HOST = os.environ.get("SANDBOX_HOST", "host.docker.internal")

# v2.x devnet InputBox address (from cannon-deployer / DEVNET_ENV)
V2_DEVNET_INPUTBOX = "0x1b51e2992A2755Ba4D6F7094032DF91991a0Cfac"
# v1.x devnet InputBox address
V1_DEVNET_INPUTBOX = "0x59b22D57D4f067708AB0c00552767405926dc768"

# Deterministic CREATE2 portal addresses for rollups-contracts v2.x
V2_DEVNET_PORTALS = {
    "ether_portal":   "0xA632c5c05812c6a6149B7af5C56117d1D2603828",
    "erc20_portal":   "0xaca6586a0cf05bd831f2501e7b4aea550da6562d",
    "erc721_portal":  "0x9e8851dadb2b77103928518846c4678d48b5e371",
    "erc1155_portal": "0x18558398dd1a8ce20956287a4da7b76ae7a96662",
}


class AssertionResult:
    def __init__(
        self,
        assertion_type: str,
        passed:         bool,
        expected:       Any = None,
        actual:         Any = None,
        detail:         str | None = None,
        duration_ms:    int | None = None,
    ):
        self.assertion_type = assertion_type
        self.passed         = passed
        self.expected       = expected
        self.actual         = actual
        self.detail         = detail
        self.duration_ms    = duration_ms

    def to_dict(self) -> dict:
        return {
            "assertion_type": self.assertion_type,
            "passed":         self.passed,
            "expected":       self.expected,
            "actual":         self.actual,
            "detail":         self.detail,
            "duration_ms":    self.duration_ms,
        }


class AssertionExecutor(ABC):
    """Each executor handles one assertion type (graphql, log_contains, http_status, etc.)"""
    assertion_type: str = ""

    @abstractmethod
    async def execute(self, assertion: dict, context: "SandboxContext") -> AssertionResult:
        """Run the assertion. Never raises — catch exceptions and return a failed result."""
        ...


class SandboxContext:
    """Connection details for the live sandbox, version-aware."""

    def __init__(
        self,
        sandbox_id:           str,
        run_id:               str,
        anvil_port:           int,
        node_port:            int,
        graphql_port:         int,
        docker_network:       str,
        node_major_version:   int = 1,
        cli_container_name:   str | None = None,
        app_address:          str | None = None,
        inputbox_address:     str | None = None,
        ether_portal_address: str | None = None,
        erc20_portal_address: str | None = None,
        erc721_portal_address: str | None = None,
        erc1155_portal_address: str | None = None,
        erc20_token_address: str | None = None,
        erc721_token_address: str | None = None,
        erc1155_token_address: str | None = None,
    ):
        self.sandbox_id          = sandbox_id
        self.run_id              = run_id
        self.anvil_port          = anvil_port
        self.node_port           = node_port          # v1.x: HTTP port; v2.x: jsonrpc-api port
        self.graphql_port        = graphql_port       # v1.x: GraphQL port; v2.x: inspect port
        self.docker_network      = docker_network
        self.node_major_version  = node_major_version
        self.cli_container_name  = cli_container_name  # v2.x: name of the cli-tools container
        self.app_address         = app_address          # deployed application contract address (if any)
        # InputBox contract address — defaults to well-known devnet address per version
        if inputbox_address:
            self.inputbox_address = inputbox_address
        elif node_major_version >= 2:
            self.inputbox_address = V2_DEVNET_INPUTBOX
        else:
            self.inputbox_address = V1_DEVNET_INPUTBOX
        # Portal contract addresses — fall back to deterministic CREATE2 defaults
        self.ether_portal_address   = ether_portal_address   or V2_DEVNET_PORTALS["ether_portal"]
        self.erc20_portal_address   = erc20_portal_address   or V2_DEVNET_PORTALS["erc20_portal"]
        self.erc721_portal_address  = erc721_portal_address  or V2_DEVNET_PORTALS["erc721_portal"]
        self.erc1155_portal_address = erc1155_portal_address or V2_DEVNET_PORTALS["erc1155_portal"]
        # Pre-deployed test token addresses (None if not available — executor falls back to deployment)
        self.erc20_token_address    = erc20_token_address  or None
        self.erc721_token_address   = erc721_token_address or None
        self.erc1155_token_address  = erc1155_token_address or None

    # ── v2.x aliases ──────────────────────────────────────────────────────────

    @property
    def jsonrpc_port(self) -> int:
        """v2.x JSON-RPC API port (same slot as node_port)."""
        return self.node_port

    @property
    def inspect_port(self) -> int:
        """v2.x Inspect API port (same slot as graphql_port)."""
        return self.graphql_port

    # ── URL builders ──────────────────────────────────────────────────────────

    @property
    def jsonrpc_url(self) -> str:
        """v2.x JSON-RPC base URL (no path)."""
        return f"http://{SANDBOX_HOST}:{self.jsonrpc_port}"

    @property
    def jsonrpc_rpc_url(self) -> str:
        """v2.x Cartesi JSON-RPC endpoint path (/rpc)."""
        return f"http://{SANDBOX_HOST}:{self.jsonrpc_port}/rpc"

    @property
    def graphql_url(self) -> str:
        """v1.x GraphQL endpoint (graphql-server at port 4000)."""
        return f"http://{SANDBOX_HOST}:{self.graphql_port}/graphql"

    @property
    def inspect_url(self) -> str:
        """
        Inspect endpoint.
        v1.x: uses node_port (HTTP server at 5004)
        v2.x: uses graphql_port slot (advancer inspect at 10012)
        """
        if self.node_major_version >= 2:
            return f"http://{SANDBOX_HOST}:{self.inspect_port}/inspect"
        return f"http://{SANDBOX_HOST}:{self.node_port}/inspect"

    def app_inspect_url(self, path: str = "") -> str:
        """
        v2.x Inspect URL for the deployed application.
        Path should be the query payload (e.g. "status").
        If app_address is not set, falls back to /inspect/<path>.
        """
        base = f"http://{SANDBOX_HOST}:{self.inspect_port}/inspect"
        if self.app_address:
            return f"{base}/{self.app_address}/{path}".rstrip("/")
        return f"{base}/{path}".rstrip("/")

    def app_jsonrpc_url(self) -> str:
        """
        v2.x JSON-RPC base URL.  The RPC endpoint is the same for all apps on
        the node; callers distinguish apps via the `to` field in the transaction.
        """
        return self.jsonrpc_url

    @property
    def anvil_rpc_url(self) -> str:
        return f"http://{SANDBOX_HOST}:{self.anvil_port}"


# ── Shared state-query helpers ─────────────────────────────────────────────────

_helper_log = logging.getLogger("test-runner.executors.helpers")


async def fetch_input_count(rpc_url: str, app_id: str) -> int:
    """
    Query cartesi_listInputs and return the total indexed input count.
    Uses pagination.total_count to get the real total beyond the default page limit.
    Returns -1 on any error so callers can omit the stat rather than crash.
    """
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                rpc_url,
                json={"jsonrpc": "2.0", "method": "cartesi_listInputs",
                      "params": {"application": app_id, "limit": 1000}, "id": 1},
                headers={"Content-Type": "application/json"},
            )
            body = resp.json()
            result = body.get("result", {})
            pagination = result.get("pagination", {})
            if pagination and "total_count" in pagination:
                return pagination["total_count"]
            return len(result.get("data", []))
    except Exception as exc:
        _helper_log.debug("fetch_input_count failed: %s", exc)
        return -1


async def fetch_output_count(rpc_url: str, app_id: str) -> int:
    """
    Query cartesi_listOutputs and return the current total output count.
    Returns -1 on any error.
    """
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                rpc_url,
                json={"jsonrpc": "2.0", "method": "cartesi_listOutputs",
                      "params": {"application": app_id, "limit": 1000}, "id": 1},
                headers={"Content-Type": "application/json"},
            )
            body = resp.json()
            result = body.get("result", {})
            pagination = result.get("pagination", {})
            if pagination and "total_count" in pagination:
                return pagination["total_count"]
            return len(result.get("data", []))
    except Exception as exc:
        _helper_log.debug("fetch_output_count failed: %s", exc)
        return -1


def count_before_result(noun: str, count: int) -> "AssertionResult":
    """Probe assertion logged before an action to capture the starting count."""
    return AssertionResult(
        assertion_type="count_before",
        passed=True,
        detail=f"{noun} before: {count}",
        duration_ms=0,
    )


def count_after_result(noun: str, before: int, after: int,
                       require_increase: bool = True) -> "AssertionResult":
    """Verification assertion logged after an action to confirm the count changed."""
    if after > before:
        detail = f"{noun} after: {after} (+{after - before})"
        passed = True
    elif after == before:
        detail = f"{noun} after: {after} (no change)"
        passed = not require_increase
    else:
        detail = f"{noun} after: {after} (decreased from {before})"
        passed = False
    return AssertionResult(
        assertion_type="count_after",
        passed=passed,
        detail=detail,
        duration_ms=0,
    )
