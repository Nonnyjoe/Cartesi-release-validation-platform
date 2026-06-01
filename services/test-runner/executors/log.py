"""
services/test-runner/executors/log.py
Assertion type: log_contains

Fetches stdout logs from a named sandbox container and checks for a pattern.

Field aliases (both forms accepted):
  component / service  — container service name (e.g. advancer, evm-reader)
  pattern   / text     — regex pattern to search for in last N log lines

Extra fields:
  expect_absent: true   — pass if pattern NOT found (fail immediately if found)
  timeout_seconds: N    — for presence tests: poll until found or timeout;
                          for absence tests: single check only
  tail: 500             — number of log lines to read (default 500)
"""
import asyncio
import re
import time
import logging

import docker

from .base import AssertionExecutor, AssertionResult, SandboxContext

log = logging.getLogger("test-runner.executor.log")


class LogContainsExecutor(AssertionExecutor):
    assertion_type = "log_contains"

    def __init__(self):
        self._docker = None

    @property
    def docker(self):
        if self._docker is None:
            self._docker = docker.from_env()
        return self._docker

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        # Accept either canonical or legacy alias field names
        pattern       = assertion.get("pattern") or assertion.get("text", "")
        component     = assertion.get("component") or assertion.get("service", "node")
        timeout_s     = int(assertion.get("timeout_seconds", 0))
        expect_absent = assertion.get("expect_absent", False)
        tail          = int(assertion.get("tail", 500))

        # Guard: empty pattern is always a definition bug — fail fast with a clear message
        # rather than silently matching everything (re.search("", s) always returns truthy).
        if not pattern:
            return AssertionResult(
                assertion_type="log_contains",
                passed=False,
                detail=(
                    "log_contains: empty pattern — definition must specify "
                    "'pattern' (or 'text') with a non-empty value"
                ),
            )

        # v2.x has no single "node" container — map to the primary processing service.
        if ctx.node_major_version >= 2 and component == "node":
            component = "advancer"

        container_name = f"rvp-{component}-{ctx.sandbox_id[:8]}"
        t0 = time.monotonic()

        # Absence check: single read — no point polling; if it appeared once it's a failure
        if expect_absent:
            try:
                container = self.docker.containers.get(container_name)
                logs = container.logs(
                    stdout=True, stderr=True, tail=tail
                ).decode("utf-8", errors="replace")
                found = bool(re.search(pattern, logs, re.IGNORECASE))
                return AssertionResult(
                    assertion_type="log_contains",
                    passed=not found,
                    expected=f"pattern absent: {pattern!r}",
                    actual="absent" if not found else "FOUND (unexpected)",
                    detail=(
                        f"Container: {container_name}, pattern: {pattern!r} — "
                        f"{'absent as expected' if not found else 'present (expected absent)'}"
                    ),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
            except Exception as exc:
                log.warning("log_contains absence check error: %s", exc)
                return AssertionResult(
                    assertion_type="log_contains",
                    passed=False,
                    detail=str(exc),
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

        # Presence check: poll until found or timeout
        deadline   = t0 + (timeout_s if timeout_s > 0 else 5)
        last_exc   = None
        poll_sleep = 2.0

        while time.monotonic() < deadline:
            try:
                container = self.docker.containers.get(container_name)
                logs = container.logs(
                    stdout=True, stderr=True, tail=tail
                ).decode("utf-8", errors="replace")
                found = bool(re.search(pattern, logs, re.IGNORECASE))
                if found:
                    return AssertionResult(
                        assertion_type="log_contains",
                        passed=True,
                        expected=pattern,
                        actual="found",
                        detail=f"Container: {container_name}, pattern: {pattern!r}",
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )
            except Exception as exc:
                last_exc = exc
                log.warning("log_contains poll error (%s): %s", container_name, exc)

            if timeout_s > 0 and time.monotonic() + poll_sleep < deadline:
                await asyncio.sleep(poll_sleep)
            else:
                break

        if last_exc:
            return AssertionResult(
                assertion_type="log_contains",
                passed=False,
                detail=str(last_exc),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        elapsed = int(time.monotonic() - t0)
        return AssertionResult(
            assertion_type="log_contains",
            passed=False,
            expected=pattern,
            actual="not found",
            detail=(
                f"Container: {container_name}, pattern: {pattern!r} "
                f"not found in last {tail} lines after {elapsed}s"
            ),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )
