"""
services/test-runner/executors/http.py
Assertion type: http_status
GETs an endpoint and checks the HTTP status code.
"""
import time
import logging
import httpx

from .base import AssertionExecutor, AssertionResult, SandboxContext

log = logging.getLogger("test-runner.executor.http")


class HttpStatusExecutor(AssertionExecutor):
    assertion_type = "http_status"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        raw_endpoint = assertion.get("endpoint", "/healthz")
        expected     = assertion.get("expect", 200)

        # Resolve relative endpoints against the node port
        if raw_endpoint.startswith("/"):
            url = f"http://localhost:{ctx.node_port}{raw_endpoint}"
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
