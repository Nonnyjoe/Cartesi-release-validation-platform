"""
services/test-runner/executors/metrics_check.py
Assertion type: metrics_check

Fetches Prometheus /metrics endpoint via Alpine container on sandbox Docker
network and validates the response format and content.

Assertion YAML:
  - type: metrics_check
    service: advancer               # evm-reader|advancer|validator|claimer|jsonrpc
    expect_metric: cartesi_inputs_processed_total  # assert metric name present
    expect_metric_changed: true     # assert metric value > 0 (incremented)
    expect_format_valid: true       # assert response is valid Prometheus text format
"""
import re
import subprocess
import time
import logging

from .base import AssertionExecutor, AssertionResult, SandboxContext

log = logging.getLogger("test-runner.executor.metrics_check")

SERVICE_PORTS = {
    "evm-reader": 10001,
    "advancer":   10002,
    "validator":  10003,
    "claimer":    10004,
    "jsonrpc":    10005,
}


class MetricsCheckExecutor(AssertionExecutor):
    assertion_type = "metrics_check"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        service            = assertion.get("service", "advancer")
        expect_metric      = assertion.get("expect_metric")
        expect_metric_gt   = assertion.get("expect_metric_changed", False)
        expect_format_valid = assertion.get("expect_format_valid", True)

        port = SERVICE_PORTS.get(service, 10002)
        short = ctx.sandbox_id[:8]
        container = f"rvp-{service}-{short}"
        url = f"http://{container}:{port}/metrics"

        t0 = time.monotonic()
        try:
            result = subprocess.run(
                [
                    "docker", "run", "--rm",
                    "--network", ctx.docker_network,
                    "alpine:latest",
                    "sh", "-c", f"wget -qO - '{url}' 2>&1",
                ],
                capture_output=True,
                text=True,
                timeout=15,
            )
            body = result.stdout

            if result.returncode != 0 or not body.strip():
                return AssertionResult(
                    assertion_type="metrics_check",
                    passed=False,
                    detail=f"{service} /metrics unreachable: {body[:200] or result.stderr[:200]}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

            # Basic Prometheus format check: look for # HELP or # TYPE lines
            if expect_format_valid:
                has_help_or_type = bool(re.search(r"^#\s+(HELP|TYPE)\s+\w+", body, re.MULTILINE))
                if not has_help_or_type:
                    return AssertionResult(
                        assertion_type="metrics_check",
                        passed=False,
                        detail=f"{service} /metrics body missing Prometheus # HELP/# TYPE lines",
                        actual=body[:300],
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )

            # Specific metric check
            if expect_metric:
                found = expect_metric in body
                if not found:
                    return AssertionResult(
                        assertion_type="metrics_check",
                        passed=False,
                        detail=f"{service} /metrics: metric '{expect_metric}' not found",
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )
                # Check metric value > 0
                if expect_metric_gt:
                    match = re.search(
                        rf"^{re.escape(expect_metric)}(?:\{{[^}}]*\}})?\s+(\S+)",
                        body, re.MULTILINE
                    )
                    if match:
                        try:
                            val = float(match.group(1))
                            if val <= 0:
                                return AssertionResult(
                                    assertion_type="metrics_check",
                                    passed=False,
                                    detail=f"{service} {expect_metric}={val} (expected > 0)",
                                    duration_ms=int((time.monotonic() - t0) * 1000),
                                )
                        except ValueError:
                            pass

            return AssertionResult(
                assertion_type="metrics_check",
                passed=True,
                detail=f"{service} /metrics OK ({len(body)} bytes)",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        except subprocess.TimeoutExpired:
            return AssertionResult(
                assertion_type="metrics_check",
                passed=False,
                detail=f"{service} /metrics timed out",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            log.warning("metrics_check error: %s", exc)
            return AssertionResult(
                assertion_type="metrics_check",
                passed=False,
                detail=str(exc),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
