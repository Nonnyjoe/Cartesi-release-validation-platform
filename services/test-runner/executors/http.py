"""
services/test-runner/executors/http.py
Assertion type: http_status
GETs an endpoint and checks the HTTP status code.

Endpoint routing by node version
---------------------------------
v1.x:
  Relative paths → node_port (HTTP API at 5004)

v2.x:
  /inspect/* → graphql_port slot (advancer inspect at 10012)
  all others  → node_port slot   (jsonrpc-api at 10011)

An assertion can also specify an explicit "port_override" (int) to bypass
routing and target a specific host port directly.
"""
import time
import logging
import httpx

from .base import AssertionExecutor, AssertionResult, SandboxContext, SANDBOX_HOST

log = logging.getLogger("test-runner.executor.http")


class HttpStatusExecutor(AssertionExecutor):
    assertion_type = "http_status"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        raw_endpoint   = assertion.get("endpoint", "/healthz")
        expected       = assertion.get("expect", 200)
        port_override  = assertion.get("port_override")

        if port_override:
            url = f"http://{SANDBOX_HOST}:{port_override}{raw_endpoint}"
        elif raw_endpoint.startswith("/"):
            url = _resolve_endpoint(raw_endpoint, ctx)
        else:
            url = raw_endpoint

        t0 = time.monotonic()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
            actual = resp.status_code
            passed = actual == expected
            return AssertionResult(
                assertion_type="http_status",
                passed=passed,
                expected=expected,
                actual=actual,
                detail=f"GET {url} → {actual}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            log.warning("HTTP assertion error: %s", exc)
            return AssertionResult(
                assertion_type="http_status",
                passed=False,
                detail=str(exc),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )


def _resolve_endpoint(path: str, ctx: SandboxContext) -> str:
    """Map a relative path to the correct host:port for this sandbox version."""
    if ctx.node_major_version >= 2:
        # Inspect paths go to the advancer's inspect port
        if path.startswith("/inspect"):
            return f"http://{SANDBOX_HOST}:{ctx.inspect_port}{path}"
        # Everything else (health, inputs, etc.) goes to jsonrpc-api
        return f"http://{SANDBOX_HOST}:{ctx.jsonrpc_port}{path}"
    # v1.x: all relative paths use node_port
    return f"http://{SANDBOX_HOST}:{ctx.node_port}{path}"
