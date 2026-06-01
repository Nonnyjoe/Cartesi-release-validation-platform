"""
services/test-runner/executors/health_check.py
Assertion type: health_check

Checks the /healthz, /readyz, or /metrics endpoint of a v2.x rollups-node
service by spawning an Alpine container on the sandbox Docker network and
making an HTTP request to the named service container.

v2.x service container names follow the pattern: rvp-{service}-{sandbox_id[:8]}
Internal health ports:
  evm-reader  → 10001
  advancer    → 10002
  validator   → 10003
  claimer     → 10004
  jsonrpc     → 10005

Assertion YAML:
  - type: health_check
    service: advancer          # evm-reader | advancer | validator | claimer | jsonrpc
    path: /healthz             # /healthz (default) | /readyz | /metrics
    expect_status: 200         # default 200
    expect_body_contains: ""   # optional substring check on response body
"""
import logging
import subprocess
import time

from .base import AssertionExecutor, AssertionResult, SandboxContext

log = logging.getLogger("test-runner.executor.health_check")

_SERVICE_PORTS = {
    "evm-reader": 10001,
    "advancer":   10002,
    "validator":  10003,
    "claimer":    10004,
    "jsonrpc":    10005,
}


class HealthCheckExecutor(AssertionExecutor):
    assertion_type = "health_check"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run_sync, assertion, ctx)

    def _run_sync(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        service = assertion.get("service", "advancer")
        path    = assertion.get("path", "/healthz")
        expect_status  = int(assertion.get("expect_status", 200))
        expect_contains = assertion.get("expect_body_contains", "")
        short = ctx.sandbox_id[:8]

        t0 = time.monotonic()

        port = _SERVICE_PORTS.get(service)
        if port is None:
            return AssertionResult(
                assertion_type="health_check",
                passed=False,
                detail=f"Unknown service '{service}'. Valid: {list(_SERVICE_PORTS)}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        container_host = f"rvp-{service}-{short}"
        url = f"http://{container_host}:{port}{path}"
        network = ctx.docker_network or f"rvp-sbx-{short}"

        try:
            result = subprocess.run(
                [
                    "docker", "run", "--rm",
                    "--network", network,
                    "alpine:latest",
                    "sh", "-c",
                    f"wget -qS -O - '{url}' 2>&1 || (echo 'EXIT:'$?; exit 1)",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout + result.stderr
            duration_ms = int((time.monotonic() - t0) * 1000)

            # wget -qS prints response headers to stderr and body to stdout.
            # Exit code 0 = HTTP 200-299, non-zero = failure.
            if result.returncode != 0:
                # Try to extract HTTP status from wget -S output
                status_line = next(
                    (ln for ln in output.splitlines() if "HTTP/" in ln), None
                )
                detail = f"{service}{path} → wget exit={result.returncode}"
                if status_line:
                    detail += f" ({status_line.strip()})"
                return AssertionResult(
                    assertion_type="health_check",
                    passed=(expect_status >= 400),  # expected failure?
                    expected=f"HTTP {expect_status}",
                    actual=f"exit {result.returncode}",
                    detail=detail,
                    duration_ms=duration_ms,
                )

            if expect_contains and expect_contains not in output:
                return AssertionResult(
                    assertion_type="health_check",
                    passed=False,
                    expected=f"body contains {expect_contains!r}",
                    actual=output[:200],
                    detail=f"{service}{path} body missing expected substring",
                    duration_ms=duration_ms,
                )

            return AssertionResult(
                assertion_type="health_check",
                passed=True,
                expected=f"HTTP {expect_status}",
                actual="HTTP 200",
                detail=f"{service}{path} → OK",
                duration_ms=duration_ms,
            )

        except subprocess.TimeoutExpired:
            return AssertionResult(
                assertion_type="health_check",
                passed=False,
                detail=f"{service}{path} timed out (30s)",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            log.warning("health_check error for %s%s: %s", service, path, exc)
            return AssertionResult(
                assertion_type="health_check",
                passed=False,
                detail=str(exc),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
