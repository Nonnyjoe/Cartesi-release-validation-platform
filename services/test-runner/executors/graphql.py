"""
services/test-runner/executors/graphql.py
Assertion type: graphql
Sends a GraphQL query to the node API and asserts on a JSON path in the response.
"""
import time
import logging
from typing import Any

import httpx

from .base import AssertionExecutor, AssertionResult, SandboxContext

log = logging.getLogger("test-runner.executor.graphql")


def _resolve_path(obj: Any, path: str) -> Any:
    """Resolve a dotted path like 'inputs.edges[0].node.payload' into a value."""
    import re
    parts = re.split(r"\.|\[(\d+)\]", path)
    for part in parts:
        if part is None or part == "":
            continue
        if part.isdigit():
            obj = obj[int(part)]
        else:
            obj = obj[part]
    return obj


class GraphQLExecutor(AssertionExecutor):
    assertion_type = "graphql"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        query    = assertion.get("query", "")
        expect   = assertion.get("expect", {})
        path     = expect.get("path")
        expected = expect.get("value")

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    ctx.graphql_url,
                    json={"query": query},
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json().get("data", {})

            actual = _resolve_path(data, path) if path else data
            passed = actual == expected
            return AssertionResult(
                assertion_type="graphql",
                passed=passed,
                expected=expected,
                actual=actual,
                detail=f"Path '{path}': expected={expected!r} actual={actual!r}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            log.warning("GraphQL assertion error: %s", exc)
            return AssertionResult(
                assertion_type="graphql",
                passed=False,
                detail=str(exc),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
