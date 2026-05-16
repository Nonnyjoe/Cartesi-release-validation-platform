"""
services/test-runner/executors/log.py
Assertion type: log_contains
Fetches stdout logs from a named container and checks for a pattern.
"""
import re
import time
import logging

import docker

from .base import AssertionExecutor, AssertionResult, SandboxContext

log = logging.getLogger("test-runner.executor.log")


class LogContainsExecutor(AssertionExecutor):
    assertion_type = "log_contains"

    def __init__(self):
        self._docker = None  # lazy — connect on first use

    @property
    def docker(self):
        if self._docker is None:
            self._docker = docker.from_env()
        return self._docker

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        pattern   = assertion.get("pattern", "")
        component = assertion.get("component", "node")
        t0 = time.monotonic()

        container_name = f"rvp-{component}-{ctx.sandbox_id[:8]}"
        try:
            container = self.docker.containers.get(container_name)
            logs = container.logs(stdout=True, stderr=True, tail=500).decode("utf-8", errors="replace")
            found = bool(re.search(pattern, logs, re.IGNORECASE))
            return AssertionResult(
                assertion_type="log_contains",
                passed=found,
                expected=pattern,
                actual=f"{'found' if found else 'not found'} in last 500 lines",
                detail=f"Container: {container_name}, pattern: {pattern!r}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            log.warning("Log assertion error: %s", exc)
            return AssertionResult(
                assertion_type="log_contains",
                passed=False,
                detail=str(exc),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
