"""
services/test-runner/executors/service_restart.py
Assertion type: service_restart

Restarts a v2.x rollups-node service container and verifies it recovers by
polling its /healthz endpoint until it returns HTTP 200.

Container names follow: rvp-{service}-{sandbox_id[:8]}
Health ports: evm-reader=10001, advancer=10002, validator=10003,
              claimer=10004, jsonrpc=10005

Assertion YAML:
  - type: service_restart
    service: advancer             # evm-reader|advancer|validator|claimer|jsonrpc
    verify_path: /healthz         # /healthz (default) | /readyz
    verify_timeout: 60            # seconds to wait for healthy state (default 60)
    pre_inputs_required: false    # if true, skip if no inputs have been processed
"""
import logging
import subprocess
import time

from .base import AssertionExecutor, AssertionResult, SandboxContext

log = logging.getLogger("test-runner.executor.service_restart")

_SERVICE_PORTS = {
    "evm-reader": 10001,
    "advancer":   10002,
    "validator":  10003,
    "claimer":    10004,
    "jsonrpc":    10005,
}


class ServiceRestartExecutor(AssertionExecutor):
    assertion_type = "service_restart"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._run_sync, assertion, ctx)

    def _run_sync(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        service         = assertion.get("service", "advancer")
        verify_path     = assertion.get("verify_path", "/healthz")
        verify_timeout  = int(assertion.get("verify_timeout", 60))
        short           = ctx.sandbox_id[:8]
        container_name  = f"rvp-{service}-{short}"
        network         = ctx.docker_network or f"rvp-sbx-{short}"

        port = _SERVICE_PORTS.get(service)
        if port is None:
            return AssertionResult(
                assertion_type="service_restart",
                passed=False,
                detail=f"Unknown service '{service}'. Valid: {list(_SERVICE_PORTS)}",
            )

        t0 = time.monotonic()

        # 1. Restart the container
        try:
            restart_result = subprocess.run(
                ["docker", "restart", container_name],
                capture_output=True, text=True, timeout=30,
            )
            if restart_result.returncode != 0:
                return AssertionResult(
                    assertion_type="service_restart",
                    passed=False,
                    detail=(
                        f"docker restart {container_name} failed "
                        f"(exit={restart_result.returncode}): "
                        f"{restart_result.stderr[:200]}"
                    ),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
        except Exception as exc:
            return AssertionResult(
                assertion_type="service_restart",
                passed=False,
                detail=f"restart error: {exc}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        # 2. Poll /healthz until it returns 200
        url     = f"http://rvp-{service}-{short}:{port}{verify_path}"
        deadline = time.monotonic() + verify_timeout
        while time.monotonic() < deadline:
            try:
                result = subprocess.run(
                    [
                        "docker", "run", "--rm",
                        "--network", network,
                        "alpine:latest",
                        "wget", "-q", "-O", "-", url,
                    ],
                    capture_output=True, text=True, timeout=10,
                )
                if result.returncode == 0:
                    duration_ms = int((time.monotonic() - t0) * 1000)
                    return AssertionResult(
                        assertion_type="service_restart",
                        passed=True,
                        detail=(
                            f"{service} restarted and healthy "
                            f"({duration_ms}ms)"
                        ),
                        duration_ms=duration_ms,
                    )
            except Exception:
                pass
            time.sleep(3)

        duration_ms = int((time.monotonic() - t0) * 1000)
        return AssertionResult(
            assertion_type="service_restart",
            passed=False,
            detail=(
                f"{service} did not recover within {verify_timeout}s "
                f"after restart"
            ),
            duration_ms=duration_ms,
        )
