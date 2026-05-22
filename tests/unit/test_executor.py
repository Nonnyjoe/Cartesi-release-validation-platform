"""
tests/unit/test_executor.py
Unit tests for the run_test() dispatcher in services/test-runner/executor.py.

Executors are replaced with controlled AsyncMocks so no network or Docker
calls are made.  The tests verify that:
  - all-pass  → status "passed"
  - any-fail  → status "failed"
  - unknown type → status "failed" with detail message
  - empty list   → status "passed" (vacuously true)
  - timeout      → status "timeout"
  - executor exception → handled gracefully (status "error")
"""
import sys
import os

os.environ.setdefault("SANDBOX_HOST", "testhost")
_TR = os.path.join(os.path.dirname(__file__), "../../services/test-runner")
if _TR not in sys.path:
    sys.path.insert(0, _TR)

import asyncio
import pytest
from unittest.mock import AsyncMock, patch

import executor as executor_module
from executor import run_test
from executors.base import AssertionResult, SandboxContext


# ─── Helpers ──────────────────────────────────────────────────────────────────

def ctx() -> SandboxContext:
    return SandboxContext(
        sandbox_id    = "sbx-test",
        run_id        = "run-test",
        anvil_port    = 28545,
        node_port     = 25000,
        graphql_port  = 24000,
        docker_network = "test-net",
    )


def mock_exec(atype: str, passed: bool = True):
    """Return a mock executor instance that always returns the given result."""
    m = AsyncMock()
    m.assertion_type = atype
    m.execute = AsyncMock(return_value=AssertionResult(
        assertion_type = atype,
        passed         = passed,
        detail         = f"mock({'ok' if passed else 'fail'})",
    ))
    return m


def defn(assertions: list, timeout: int = 30) -> dict:
    return {
        "slug": "test-slug",
        "timeout_seconds": timeout,
        "definition_parsed": {"assertions": assertions},
    }


# ─── Basic dispatch ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_all_assertions_pass():
    asserts = [{"type": "t1"}, {"type": "t1"}]
    with patch.object(executor_module, "_EXECUTORS", {"t1": mock_exec("t1", True)}):
        result = await run_test(defn(asserts), ctx())
    assert result["status"] == "passed"
    assert len(result["assertion_results"]) == 2
    assert all(ar["passed"] for ar in result["assertion_results"])


@pytest.mark.asyncio
async def test_one_assertion_fails_marks_failed():
    asserts = [{"type": "pass"}, {"type": "fail"}]
    with patch.object(executor_module, "_EXECUTORS", {
        "pass": mock_exec("pass", True),
        "fail": mock_exec("fail", False),
    }):
        result = await run_test(defn(asserts), ctx())
    assert result["status"] == "failed"
    assert result["assertion_results"][0]["passed"] is True
    assert result["assertion_results"][1]["passed"] is False


@pytest.mark.asyncio
async def test_all_assertions_fail():
    asserts = [{"type": "t"}, {"type": "t"}]
    with patch.object(executor_module, "_EXECUTORS", {"t": mock_exec("t", False)}):
        result = await run_test(defn(asserts), ctx())
    assert result["status"] == "failed"
    assert all(not ar["passed"] for ar in result["assertion_results"])


@pytest.mark.asyncio
async def test_empty_assertions_list_passes():
    """Vacuously true — a test with no assertions should pass."""
    with patch.object(executor_module, "_EXECUTORS", {}):
        result = await run_test(defn([]), ctx())
    assert result["status"] == "passed"
    assert result["assertion_results"] == []


# ─── Unknown assertion type ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_unknown_assertion_type_fails_with_detail():
    asserts = [{"type": "nonexistent"}]
    with patch.object(executor_module, "_EXECUTORS", {}):
        result = await run_test(defn(asserts), ctx())
    assert result["status"] == "failed"
    assert "Unknown assertion type" in result["assertion_results"][0]["detail"]


# ─── Timeout ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_timeout_yields_timeout_status():
    async def slow(assertion, ctx_arg):
        await asyncio.sleep(10)
        return AssertionResult(assertion_type="slow", passed=True)

    slow_exec = AsyncMock()
    slow_exec.assertion_type = "slow"
    slow_exec.execute = slow

    with patch.object(executor_module, "_EXECUTORS", {"slow": slow_exec}):
        result = await run_test(defn([{"type": "slow"}], timeout=0.01), ctx())

    assert result["status"] == "timeout"
    assert result["error_message"] is not None
    assert "timeout" in result["error_message"].lower()


# ─── Executor exception ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_executor_exception_yields_error_status():
    async def crashing(assertion, ctx_arg):
        raise RuntimeError("simulated crash")

    crash_exec = AsyncMock()
    crash_exec.assertion_type = "boom"
    crash_exec.execute = crashing

    with patch.object(executor_module, "_EXECUTORS", {"boom": crash_exec}):
        result = await run_test(defn([{"type": "boom"}]), ctx())

    assert result["status"] == "error"
    assert result["error_message"] is not None


# ─── duration_ms ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duration_ms_is_non_negative_integer():
    with patch.object(executor_module, "_EXECUTORS", {"t": mock_exec("t", True)}):
        result = await run_test(defn([{"type": "t"}]), ctx())
    assert isinstance(result["duration_ms"], int)
    assert result["duration_ms"] >= 0
