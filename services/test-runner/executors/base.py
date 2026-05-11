"""
services/test-runner/executors/base.py
Abstract base class for all assertion executors.
Adding a new assertion type = one new file implementing AssertionExecutor.
"""
from abc import ABC, abstractmethod
from typing import Any


class AssertionResult:
    def __init__(
        self,
        assertion_type: str,
        passed: bool,
        expected: Any = None,
        actual: Any = None,
        detail: str | None = None,
        duration_ms: int | None = None,
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
    """
    Each executor handles one assertion type (graphql, log_contains, http_status, etc.)
    """
    assertion_type: str = ""

    @abstractmethod
    async def execute(self, assertion: dict, context: "SandboxContext") -> AssertionResult:
        """Run the assertion. Never raises — catch exceptions and return a failed result."""
        ...


class SandboxContext:
    """Connection details for the live sandbox."""
    def __init__(
        self,
        sandbox_id: str,
        run_id: str,
        anvil_port: int,
        node_port: int,
        graphql_port: int,
        docker_network: str,
    ):
        self.sandbox_id     = sandbox_id
        self.run_id         = run_id
        self.anvil_port     = anvil_port
        self.node_port      = node_port
        self.graphql_port   = graphql_port
        self.docker_network = docker_network

    @property
    def graphql_url(self) -> str:
        return f"http://localhost:{self.graphql_port}/graphql"

    @property
    def inspect_url(self) -> str:
        return f"http://localhost:{self.node_port}/inspect"

    @property
    def anvil_rpc_url(self) -> str:
        return f"http://localhost:{self.anvil_port}"
