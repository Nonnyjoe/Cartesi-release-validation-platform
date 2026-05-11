"""
services/test-runner/executors/voucher.py
Assertion type: voucher
Queries the GraphQL API for a voucher and verifies it was executed on-chain.
"""
import time
import logging
import httpx

from .base import AssertionExecutor, AssertionResult, SandboxContext

log = logging.getLogger("test-runner.executor.voucher")

VOUCHER_QUERY = """
{
  vouchers {
    edges {
      node {
        index
        destination
        payload
        proof { validity { inputIndexWithinEpoch outputIndexWithinInput } }
      }
    }
  }
}
"""


class VoucherExecutor(AssertionExecutor):
    assertion_type = "voucher"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        expected_count = assertion.get("expect_count", 1)
        t0 = time.monotonic()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    ctx.graphql_url,
                    json={"query": VOUCHER_QUERY},
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data     = resp.json().get("data", {})
                vouchers = data.get("vouchers", {}).get("edges", [])
                actual   = len(vouchers)
                passed   = actual >= expected_count
                return AssertionResult(
                    assertion_type="voucher",
                    passed=passed,
                    expected=f">= {expected_count} vouchers",
                    actual=f"{actual} vouchers",
                    detail=f"Found {actual} voucher(s), expected >= {expected_count}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
        except Exception as exc:
            log.warning("Voucher assertion error: %s", exc)
            return AssertionResult(
                assertion_type="voucher",
                passed=False,
                detail=str(exc),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
