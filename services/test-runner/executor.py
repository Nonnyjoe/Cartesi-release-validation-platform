"""
services/test-runner/executor.py
Dispatches assertions to the right executor.
Runs all assertions for a test definition sequentially and compiles results.
"""
import asyncio
import logging
import time
from typing import Any

from executors.base import AssertionExecutor, AssertionResult, SandboxContext
from executors.graphql import GraphQLExecutor
from executors.http import HttpStatusExecutor
from executors.log import LogContainsExecutor
from executors.chain import ChainTxExecutor
from executors.voucher import VoucherExecutor
from executors.jsonrpc import JsonRpcExecutor
from executors.portal_deposit import PortalDepositExecutor
from executors.voucher_v2 import VoucherV2Executor

log = logging.getLogger("test-runner.executor")

# Registry: assertion_type → executor instance
_EXECUTORS: dict[str, AssertionExecutor] = {
    e.assertion_type: e for e in [
        GraphQLExecutor(),
        HttpStatusExecutor(),
        LogContainsExecutor(),
        ChainTxExecutor(),
        VoucherExecutor(),
        JsonRpcExecutor(),
        PortalDepositExecutor(),
        VoucherV2Executor(),
    ]
}


async def run_test(definition: dict, ctx: SandboxContext) -> dict[str, Any]:
    """
    Run all assertions in a test definition.
    Returns a result dict: status, duration_ms, assertion_results, error_message.
    """
    assertions = definition.get("definition_parsed", {}).get("assertions", [])
    timeout    = definition.get("timeout_seconds", 120)

    slug = definition.get("slug", definition.get("id", "unknown"))
    log.info("Running test '%s' (%d assertions, timeout=%ds)", slug, len(assertions), timeout)

    results: list[dict] = []
    t_start = time.monotonic()
    overall_status = "passed"
    error_message  = None

    try:
        async with asyncio.timeout(timeout):
            for assertion in assertions:
                atype    = assertion.get("type")
                executor = _EXECUTORS.get(atype)

                if not executor:
                    log.warning("No executor for assertion type '%s' — skipping", atype)
                    results.append({
                        "assertion_type": atype,
                        "passed": False,
                        "detail": f"Unknown assertion type: {atype}",
                    })
                    overall_status = "failed"
                    continue

                result = await executor.execute(assertion, ctx)
                results.append(result.to_dict())

                if not result.passed:
                    overall_status = "failed"
                    log.info("Assertion FAILED: %s — %s", atype, result.detail)
                else:
                    log.debug("Assertion passed: %s", atype)

    except asyncio.TimeoutError:
        overall_status = "timeout"
        error_message  = f"Test exceeded timeout of {timeout}s"
        log.warning("Test '%s' timed out after %ds", slug, timeout)
    except Exception as exc:
        overall_status = "error"
        error_message  = str(exc)
        log.exception("Test '%s' encountered an error: %s", slug, exc)

    duration_ms = int((time.monotonic() - t_start) * 1000)
    log.info("Test '%s' → %s (%dms)", slug, overall_status, duration_ms)

    return {
        "status":            overall_status,
        "duration_ms":       duration_ms,
        "assertion_results": results,
        "error_message":     error_message,
    }
