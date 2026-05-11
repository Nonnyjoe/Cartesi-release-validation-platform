"""
services/test-runner/executors/chain.py
Assertion type: chain_tx
Sends an advance-state input to the InputBox contract via the Cartesi HTTP bridge.
"""
import time
import logging
import httpx

from .base import AssertionExecutor, AssertionResult, SandboxContext

log = logging.getLogger("test-runner.executor.chain")

# Standard Cartesi InputBox address on Anvil dev chains
INPUTBOX_ENDPOINT_PATH = "/box"


class ChainTxExecutor(AssertionExecutor):
    assertion_type = "chain_tx"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        payload  = assertion.get("payload", "0xdeadbeef")
        app_addr = assertion.get("app_address", "0x0000000000000000000000000000000000000001")
        t0 = time.monotonic()

        # Use the Cartesi node's HTTP advance endpoint
        url = f"http://localhost:{ctx.node_port}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    f"{url}/box",
                    json={"payload": payload},
                    headers={"Content-Type": "application/json"},
                )
                passed = resp.status_code in (200, 201, 202)
                return AssertionResult(
                    assertion_type="chain_tx",
                    passed=passed,
                    expected="2xx",
                    actual=resp.status_code,
                    detail=f"POST {url}/box payload={payload!r} → {resp.status_code}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
        except Exception as exc:
            log.warning("chain_tx assertion error: %s", exc)
            return AssertionResult(
                assertion_type="chain_tx",
                passed=False,
                detail=str(exc),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
