"""
services/test-runner/executors/chain.py
Assertion type: chain_tx

v1.x: POST to the Cartesi HTTP bridge (/box) on the node HTTP port.
v2.x: Submit an on-chain transaction to InputBox.addInput(appContract, payload)
      via Anvil's JSON-RPC, using the well-known test account.
"""
import asyncio
import time
import logging
import httpx

from .base import (AssertionExecutor, AssertionResult, SandboxContext, SANDBOX_HOST,
                   fetch_input_count, count_before_result, count_after_result)

log = logging.getLogger("test-runner.executor.chain")

# addInput(address,bytes) — keccak256 of the signature, first 4 bytes
# keccak256("addInput(address,bytes)") = 0x1789cd63 (pre-computed)
_ADD_INPUT_SELECTOR = "1789cd63"

# Anvil well-known account #0 (from test mnemonic)
_SENDER = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


def _abi_encode_add_input(app_address: str, payload_hex: str) -> str:
    """
    ABI-encode InputBox.addInput(address appContract, bytes payload).
    Returns the full calldata as a 0x-prefixed hex string.

    ABI layout (dynamic types):
      [0:4]   selector
      [4:36]  appContract, padded to 32 bytes
      [36:68] offset to bytes data = 64 (0x40)
      [68:100] length of payload
      [100:..] payload padded to 32-byte boundary
    """
    addr = app_address.lower().removeprefix("0x").zfill(64)
    offset = "0000000000000000000000000000000000000000000000000000000000000040"

    raw = payload_hex.lower().removeprefix("0x").replace(" ", "")
    length_val = len(raw) // 2  # byte length
    length_enc = hex(length_val)[2:].zfill(64)
    # Pad payload to multiple of 32 bytes
    padded_len = ((length_val + 31) // 32) * 32
    payload_enc = raw.ljust(padded_len * 2, "0")

    return "0x" + _ADD_INPUT_SELECTOR + addr + offset + length_enc + payload_enc


class ChainTxExecutor(AssertionExecutor):
    assertion_type = "chain_tx"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        raw_payload    = assertion.get("payload", "0xdeadbeef")
        # Accept plain JSON/string payloads — auto-encode to hex if not 0x-prefixed
        if isinstance(raw_payload, str) and not raw_payload.startswith("0x"):
            payload = "0x" + raw_payload.encode("utf-8").hex()
        else:
            payload = raw_payload
        expect_revert  = assertion.get("expect_revert", False)
        repeat         = max(1, int(assertion.get("repeat", 1)))
        # For v2.x use deployed app address from context; fall back to assertion value
        app_addr = assertion.get("app_address", "")
        if ctx.node_major_version >= 2:
            app_addr = ctx.app_address or app_addr or "0x0000000000000000000000000000000000000001"
        else:
            app_addr = app_addr or "0x0000000000000000000000000000000000000001"

        t0 = time.monotonic()

        if ctx.node_major_version >= 2:
            before_count = await fetch_input_count(ctx.jsonrpc_rpc_url, ctx.app_address or "app")

            last_result = AssertionResult("chain_tx", False, detail="no iterations")
            for i in range(repeat):
                last_result = await self._submit_v2(
                    payload, app_addr, ctx, t0, expect_revert=expect_revert
                )
                if not last_result.passed:
                    last_result = AssertionResult(
                        assertion_type="chain_tx",
                        passed=False,
                        detail=f"[{i+1}/{repeat}] {last_result.detail}",
                        duration_ms=int((time.monotonic() - t0) * 1000),
                    )
                    parts = ([count_before_result("inputs", before_count)]
                             if before_count >= 0 else [])
                    return parts + [last_result]
            if repeat > 1:
                last_result = AssertionResult(
                    assertion_type="chain_tx",
                    passed=True,
                    expected=f"all {repeat} inputs accepted",
                    actual=f"{repeat} inputs submitted",
                    detail=f"Sent {repeat}× InputBox.addInput to {app_addr[:10]}…",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
            if before_count >= 0:
                # Poll up to 15s for the evm-reader to index the new input(s)
                after_count = before_count
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    after_count = await fetch_input_count(
                        ctx.jsonrpc_rpc_url, ctx.app_address or "app"
                    )
                    if after_count > before_count:
                        break
                    await asyncio.sleep(2)
                return [
                    count_before_result("inputs", before_count),
                    last_result,
                    count_after_result("inputs", before_count, after_count),
                ]
            return last_result
        else:
            return await self._submit_v1(payload, ctx, t0)

    async def _submit_v1(self, payload: str, ctx: SandboxContext, t0: float) -> AssertionResult:
        url = f"http://{SANDBOX_HOST}:{ctx.node_port}/box"
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json={"payload": payload},
                                         headers={"Content-Type": "application/json"})
                passed = resp.status_code in (200, 201, 202)
                return AssertionResult(
                    assertion_type="chain_tx",
                    passed=passed,
                    expected="2xx",
                    actual=resp.status_code,
                    detail=f"POST {url} payload={payload!r} → {resp.status_code}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
        except Exception as exc:
            log.warning("chain_tx v1 error: %s", exc)
            return AssertionResult("chain_tx", False,
                                   detail=str(exc),
                                   duration_ms=int((time.monotonic() - t0) * 1000))

    async def _submit_v2(self, payload: str, app_addr: str,
                         ctx: SandboxContext, t0: float,
                         expect_revert: bool = False) -> AssertionResult:
        """
        Submit an input by calling InputBox.addInput on Anvil via eth_sendTransaction.
        Anvil's unlocked accounts allow unsigned transactions from _SENDER.
        After sending, mine one block and wait for the receipt.
        """
        calldata = _abi_encode_add_input(app_addr, payload)
        rpc_url  = ctx.anvil_rpc_url

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Send the transaction
                send_resp = await client.post(rpc_url, json={
                    "jsonrpc": "2.0",
                    "method":  "eth_sendTransaction",
                    "params":  [{"from": _SENDER, "to": ctx.inputbox_address, "data": calldata}],
                    "id":      1,
                })
                send_data = send_resp.json()
                if "error" in send_data:
                    raise RuntimeError(f"eth_sendTransaction error: {send_data['error']}")
                tx_hash = send_data.get("result")
                if not tx_hash:
                    raise RuntimeError(f"No tx hash returned: {send_data}")

            # Poll for receipt (Anvil mines every 1s)
            deadline = time.monotonic() + 15
            async with httpx.AsyncClient(timeout=10.0) as client:
                while time.monotonic() < deadline:
                    receipt_resp = await client.post(rpc_url, json={
                        "jsonrpc": "2.0",
                        "method":  "eth_getTransactionReceipt",
                        "params":  [tx_hash],
                        "id":      2,
                    })
                    receipt = receipt_resp.json().get("result")
                    if receipt:
                        status = int(receipt.get("status", "0x0"), 16)
                        if expect_revert:
                            passed = (status == 0)
                            exp_str = "tx reverted (status=0)"
                        else:
                            passed = (status == 1)
                            exp_str = "tx status=1"
                        return AssertionResult(
                            assertion_type="chain_tx",
                            passed=passed,
                            expected=exp_str,
                            actual=f"tx status={status}",
                            detail=(
                                f"InputBox.addInput(app={app_addr[:10]}…, "
                                f"payload={payload!r}) → tx={tx_hash[:12]}… "
                                f"status={status}"
                            ),
                            duration_ms=int((time.monotonic() - t0) * 1000),
                        )
                    await asyncio.sleep(1)

            return AssertionResult("chain_tx", False,
                                   detail=f"Timeout waiting for receipt of {tx_hash}",
                                   duration_ms=int((time.monotonic() - t0) * 1000))

        except Exception as exc:
            log.warning("chain_tx v2 error: %s", exc)
            return AssertionResult("chain_tx", False,
                                   detail=str(exc),
                                   duration_ms=int((time.monotonic() - t0) * 1000))
