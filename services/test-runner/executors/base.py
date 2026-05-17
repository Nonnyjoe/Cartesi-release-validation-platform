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
  node_port    → jsonrpc-api  (10011) — JSON-RPC endpoint
  graphql_port → advancer     (10012) — Inspect API endpoint
"""
import os
from abc import ABC, abstractmethod
from typing import Any

# On Docker for Mac / Docker Desktop, containers access host-mapped ports
# via host.docker.internal rather than localhost.
SANDBOX_HOST = os.environ.get("SANDBOX_HOST", "host.docker.internal")


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
        sandbox_id:          str,
        run_id:              str,
        anvil_port:          int,
        node_port:           int,
        graphql_port:        int,
        docker_network:      str,
        node_major_version:  int = 1,
        cli_container_name:  str | None = None,
        app_address:         str | None = None,
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
    def graphql_url(self) -> str:
        """v1.x GraphQL endpoint."""
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
