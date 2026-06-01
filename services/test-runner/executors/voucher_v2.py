"""
services/test-runner/executors/voucher_v2.py
Assertion type: voucher_v2

v2.x voucher tests via cartesi_listOutputs JSON-RPC.

Modes (set via `mode` field in the assertion YAML):
  generate (default)
      Deposit ERC20 tokens + send a withdraw action, then poll
      cartesi_listOutputs until a Voucher-type output appears.

  execute
      Same setup, then wait for the epoch to reach CLAIM_ACCEPTED status
      (claimer has submitted a claim), and call CartesiDApp.executeOutput
      on Anvil using a Foundry container.

CartesiDApp.executeOutput ABI (rollups-contracts v2.2.0)
--------------------------------------------------------
  executeOutput(bytes _output, (uint64 outputIndex, bytes32[] siblings) _proof)

  _output  — raw_data bytes from cartesi_listOutputs for the voucher
  _proof   — (flat leaf index in the epoch outputs tree, Merkle siblings)
             siblings come from output.output_hashes_siblings
"""
import asyncio
import json as _json
import logging
import time
import uuid

import httpx

from .base import AssertionExecutor, AssertionResult, SandboxContext

log = logging.getLogger("test-runner.executor.voucher_v2")

_DEPLOYER_KEY  = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
# Account #4 — dedicated to executeOutput calls; never used for token minting or deposits
_EXECUTE_OUT_KEY = "0x47e179ec197488593b187f80a00eb0da91f1b9d0b13f8733639f19c30a34926a"
_FOUNDRY_IMG   = "ghcr.io/foundry-rs/foundry:latest"
_ANVIL_RPC     = "http://localhost:8545"
_SETUP_AMOUNT  = 1000

# Dedicated Anvil accounts per mode to avoid nonce conflicts with concurrent portal tests.
_SETUP_ACCOUNTS = {
    "generate": (
        "0x70997970C51812dc3A010C7d01b50e0d17dc79C8",
        "0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d",
    ),
    "execute": (
        "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC",
        "0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a",
    ),
}

# Epoch statuses that mean the Merkle proof is available for executeOutput.
_CLAIMED_STATUSES = {"CLAIM_ACCEPTED", "SETTLED", "CLAIM_SUBMITTED"}

# decoded_data.type values that represent voucher outputs.
_VOUCHER_TYPES = {"Voucher", "voucher", "VOUCHER"}


class VoucherV2Executor(AssertionExecutor):
    assertion_type = "voucher_v2"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        mode          = assertion.get("mode", "generate").lower()
        expect_count  = int(assertion.get("expect_count", 1))
        poll_interval = float(assertion.get("poll_interval", 3))
        default_to    = 90 if mode == "generate" else 180
        poll_timeout  = int(assertion.get("poll_timeout", default_to))
        t0 = time.monotonic()

        try:
            if mode == "generate":
                return await self._check_generation(ctx, expect_count,
                                                     poll_interval, poll_timeout, t0)
            elif mode == "execute":
                return await self._execute_voucher(ctx, expect_count,
                                                    poll_interval, poll_timeout, t0)
            else:
                return AssertionResult(
                    assertion_type="voucher_v2",
                    passed=False,
                    detail=f"Unknown mode: {mode!r} (expected generate|execute)",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
        except Exception as exc:
            log.exception("voucher_v2 error: %s", exc)
            return AssertionResult(
                assertion_type="voucher_v2",
                passed=False,
                detail=f"{type(exc).__name__}: {exc}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

    # ── Voucher setup (deposit + withdraw to trigger voucher emission) ──────────

    def _build_setup_script(self, ctx: SandboxContext, mode: str) -> str:
        """
        Shell script that makes the student-tracker app emit a voucher:
        1. Mint ERC20 tokens to the test sender
        2. Approve and deposit via ERC20Portal (auto-registers sender in app)
        3. Submit a JSON withdraw action via InputBox (triggers ERC20 voucher)
        4. For execute mode: also mint tokens directly to the CartesiDApp so
           the ERC20 transfer voucher can succeed when executeOutput is called.
        """
        token    = ctx.erc20_token_address
        portal   = ctx.erc20_portal_address
        app      = ctx.app_address
        inputbox = ctx.inputbox_address
        amount   = _SETUP_AMOUNT

        sender_addr, deployer_key = _SETUP_ACCOUNTS.get(mode, _SETUP_ACCOUNTS["generate"])

        withdraw_json = _json.dumps({
            "action":     "withdraw",
            "asset_type": "erc20",
            "token":      token,
            "amount":     str(amount),
        }, separators=(",", ":"))
        withdraw_hex = "0x" + withdraw_json.encode().hex()

        # --gas-price 100gwei avoids "replacement transaction underpriced" on
        # Anvil interval mining when account #0 has an unresolved pending tx.
        _GAS = "--gas-price 100gwei"
        script = (
            f"set -e\n"
            f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {deployer_key} \\\n"
            f"  {token} 'mint(address,uint256)' {sender_addr} {amount} 2>&1\n"
            f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {deployer_key} \\\n"
            f"  {token} 'approve(address,uint256)' {portal} {amount} 2>&1\n"
            f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {deployer_key} \\\n"
            f"  {portal} 'depositERC20Tokens(address,address,uint256,bytes)' \\\n"
            f"  {token} {app} {amount} 0x 2>&1\n"
            f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {deployer_key} \\\n"
            f"  {inputbox} 'addInput(address,bytes)' {app} {withdraw_hex} 2>&1\n"
        )

        if mode == "execute":
            # Mint tokens directly to the CartesiDApp contract so the ERC20
            # transfer voucher (transfer(wallet, amount)) can succeed when
            # executeOutput is called on-chain. The deployer_key mints them.
            script += (
                f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {_DEPLOYER_KEY} \\\n"
                f"  {token} 'mint(address,uint256)' {app} {amount} 2>&1\n"
            )

        return script

    async def _trigger_voucher(self, ctx: SandboxContext, mode: str = "generate") -> None:
        if not ctx.erc20_token_address:
            raise RuntimeError(
                "ctx.erc20_token_address is not set — cannot trigger voucher. "
                "Ensure the sandbox provisioner deployed test tokens."
            )
        if not ctx.app_address:
            raise RuntimeError("ctx.app_address is not set — cannot trigger voucher")

        script = self._build_setup_script(ctx, mode)
        loop   = asyncio.get_event_loop()
        output = await loop.run_in_executor(
            None, self._run_foundry_script_sync, script, ctx.sandbox_id
        )
        log.info("Voucher setup complete for sandbox %s (mode=%s)", ctx.sandbox_id[:8], mode)
        log.info("Setup script output (last 600):\n%s", output[-600:])

    # ── Generate mode ──────────────────────────────────────────────────────────

    async def _check_generation(
        self,
        ctx: SandboxContext,
        expect_count: int,
        poll_interval: float,
        timeout: float,
        t0: float,
    ) -> AssertionResult:
        try:
            await self._trigger_voucher(ctx, mode="generate")
        except Exception as exc:
            return AssertionResult(
                assertion_type="voucher_v2",
                passed=False,
                detail=f"Voucher setup failed: {exc}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        vouchers = await self._poll_vouchers(ctx, expect_count, poll_interval,
                                              timeout, need_epoch_claim=False)
        passed = len(vouchers) >= expect_count
        app_id = ctx.app_address or "app"
        return AssertionResult(
            assertion_type="voucher_v2",
            passed=passed,
            expected=f">= {expect_count} voucher(s) in cartesi_listOutputs",
            actual=f"{len(vouchers)} voucher(s) found",
            detail=(
                f"cartesi_listOutputs({app_id[:10]}…) returned "
                f"{len(vouchers)} voucher(s) after polling "
                f"{int(time.monotonic() - t0)}s"
            ),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    # ── Execute mode ───────────────────────────────────────────────────────────

    async def _execute_voucher(
        self,
        ctx: SandboxContext,
        expect_count: int,
        poll_interval: float,
        timeout: float,
        t0: float,
    ) -> AssertionResult:
        try:
            await self._trigger_voucher(ctx, mode="execute")
        except Exception as exc:
            return AssertionResult(
                assertion_type="voucher_v2",
                passed=False,
                detail=f"Voucher setup failed: {exc}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        # Phase 1: poll for a voucher whose epoch has been claimed
        log.info("Polling for voucher with claimed epoch (sandbox=%s, timeout=%ds)…",
                 ctx.sandbox_id[:8], int(timeout))
        vouchers = await self._poll_vouchers(ctx, expect_count, poll_interval,
                                              timeout * 0.7, need_epoch_claim=True)
        if not vouchers:
            elapsed = int(time.monotonic() - t0)
            return AssertionResult(
                assertion_type="voucher_v2",
                passed=False,
                detail=(
                    f"No vouchers with a claimed epoch found after {elapsed}s. "
                    "Ensure CARTESI_EPOCH_LENGTH is set and the claimer has run."
                ),
                duration_ms=elapsed * 1000,
            )

        app_addr = ctx.app_address or ""

        # Phase 2: try each voucher until one executes successfully.
        # Multiple execute-mode tests run against the same pool of vouchers;
        # earlier tests may have already executed some, so we rotate through
        # the list and skip any that revert with OutputNotReexecutable.
        loop = asyncio.get_event_loop()
        last_detail = "no vouchers attempted"
        for voucher in vouchers:
            raw_data     = voucher.get("raw_data", "0x")
            output_index = int(voucher.get("index", "0x0"), 16)
            siblings     = voucher.get("output_hashes_siblings", [])

            log.info("Executing output: index=%d raw_data=%s…", output_index, raw_data[:12])
            script = self._build_execute_output_script(app_addr, raw_data, output_index, siblings)
            try:
                output = await loop.run_in_executor(
                    None, self._run_foundry_script_sync, script, ctx.sandbox_id
                )
            except Exception as exc:
                exc_str = str(exc)
                if "OutputNotReexecutable" in exc_str or "AlreadyExecuted" in exc_str:
                    log.info("Voucher index=%d already executed — trying next", output_index)
                    last_detail = f"index={output_index} OutputNotReexecutable"
                    continue
                return AssertionResult(
                    assertion_type="voucher_v2",
                    passed=False,
                    detail=f"executeOutput script failed: {exc_str[:400]}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

            passed = "status: 1" in output.lower() or "transactionhash" in output.lower()
            return AssertionResult(
                assertion_type="voucher_v2",
                passed=passed,
                expected="executeOutput tx status=1",
                actual="output executed on-chain" if passed else "execution failed",
                detail=(
                    f"executeOutput(index={output_index}, raw={raw_data[:10]}…) "
                    f"on CartesiDApp {app_addr[:10]}… — "
                    f"{'SUCCESS' if passed else 'FAILED'}"
                ),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        # All vouchers were already executed
        return AssertionResult(
            assertion_type="voucher_v2",
            passed=False,
            detail=f"All {len(vouchers)} voucher(s) already executed ({last_detail})",
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    # ── Polling helper ─────────────────────────────────────────────────────────

    async def _poll_vouchers(
        self,
        ctx: SandboxContext,
        expect_count: int,
        poll_interval: float,
        timeout: float,
        need_epoch_claim: bool,
    ) -> list[dict]:
        """
        Poll cartesi_listOutputs until at least expect_count Voucher-type outputs
        exist.  If need_epoch_claim=True, also waits until the epoch containing
        each voucher reaches CLAIM_ACCEPTED status.
        """
        app_id   = ctx.app_address or "app"
        deadline = time.monotonic() + timeout
        _first   = True

        while time.monotonic() < deadline:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        ctx.jsonrpc_rpc_url,
                        json={
                            "jsonrpc": "2.0",
                            "method":  "cartesi_listOutputs",
                            "params":  [app_id],
                            "id":      1,
                        },
                        headers={"Content-Type": "application/json"},
                    )
                    body = resp.json()

                if _first:
                    _first = False
                    log.info("cartesi_listOutputs first response for %s: %s",
                             app_id[:10], str(body)[:400])

                if "error" in body:
                    log.warning("cartesi_listOutputs error for %s: %s",
                                app_id[:10], body["error"])
                    await asyncio.sleep(poll_interval)
                    continue

                result = body.get("result", {})
                if not isinstance(result, dict):
                    log.warning("cartesi_listOutputs unexpected result type %s: %s",
                                type(result).__name__, str(result)[:200])
                    await asyncio.sleep(poll_interval)
                    continue

                data = result.get("data", [])
                if data:
                    log.info("cartesi_listOutputs: %d item(s) for %s — types: %s",
                             len(data), app_id[:10],
                             [x.get("decoded_data", {}).get("type") for x in data[:5]])

                # Filter for Voucher-type outputs (type is in decoded_data)
                vouchers = [
                    x for x in data
                    if x.get("decoded_data", {}).get("type") in _VOUCHER_TYPES
                ]

                if need_epoch_claim:
                    # Keep only vouchers whose epoch has been claimed
                    claimed = []
                    for v in vouchers:
                        epoch_idx = v.get("epoch_index", "0x0")
                        status = await self._get_epoch_status(ctx, epoch_idx)
                        if status in _CLAIMED_STATUSES:
                            claimed.append(v)
                        else:
                            log.debug("Epoch %s status=%s — not yet claimed for %s",
                                      epoch_idx, status, app_id[:10])
                    vouchers = claimed

                if len(vouchers) >= expect_count:
                    log.info("Found %d voucher(s)%s for %s",
                             len(vouchers),
                             " with claimed epoch" if need_epoch_claim else "",
                             app_id[:10])
                    return vouchers

            except Exception as exc:
                log.warning("cartesi_listOutputs poll error: %s", exc)

            await asyncio.sleep(poll_interval)

        return []

    async def _get_epoch_status(self, ctx: SandboxContext, epoch_index: str) -> str:
        """Return the epoch status string, or empty string on error."""
        app_id = ctx.app_address or "app"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    ctx.jsonrpc_rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "method":  "cartesi_getEpoch",
                        "params":  [app_id, epoch_index],
                        "id":      1,
                    },
                    headers={"Content-Type": "application/json"},
                )
                body = resp.json()
            if "error" in body:
                return ""
            data = body.get("result", {}).get("data", {})
            return data.get("status", "")
        except Exception as exc:
            log.debug("cartesi_getEpoch error: %s", exc)
            return ""

    # ── Shell script for executeOutput ─────────────────────────────────────────

    def _build_execute_output_script(
        self,
        app_addr:     str,
        raw_data:     str,
        output_index: int,
        siblings:     list,
    ) -> str:
        """
        Build a shell script that calls CartesiDApp.executeOutput via cast send.

        ABI: executeOutput(bytes _output, (uint64 outputIndex, bytes32[] siblings))
        """
        # Format the siblings array as [0x...,0x...,...] (no spaces)
        siblings_str = ",".join(siblings)
        proof_arg    = f"({output_index},[{siblings_str}])"

        return (
            f"set -e\n"
            f"cast send --rpc-url {_ANVIL_RPC} --gas-price 100gwei --private-key {_EXECUTE_OUT_KEY} \\\n"
            f"  {app_addr} \\\n"
            f"  'executeOutput(bytes,(uint64,bytes32[]))' \\\n"
            f"  {raw_data} \\\n"
            f"  '{proof_arg}' 2>&1\n"
        )

    # ── Docker / Foundry helpers ───────────────────────────────────────────────

    def _get_anvil_container_id(self, sandbox_id: str) -> str:
        import docker
        client     = docker.from_env(timeout=30)
        containers = client.containers.list(
            filters={"label": [
                f"rvp.sandbox_id={sandbox_id}",
                "rvp.component=anvil",
            ]}
        )
        if not containers:
            raise RuntimeError(
                f"No running Anvil container found for sandbox {sandbox_id[:8]}"
            )
        return containers[0].id

    def _run_foundry_script_sync(self, script: str, sandbox_id: str) -> str:
        import docker
        client   = docker.from_env(timeout=300)
        anvil_id = self._get_anvil_container_id(sandbox_id)
        cname    = f"rvp-voucher-{uuid.uuid4().hex[:8]}"

        try:
            client.containers.get(cname).remove(force=True)
        except Exception:
            pass

        log.info("Running executeVoucher script for sandbox %s (anvil=%s)",
                 sandbox_id[:8], anvil_id[:12])

        c = client.containers.run(
            _FOUNDRY_IMG,
            command=[script],
            name=cname,
            network_mode=f"container:{anvil_id}",
            detach=True,
            remove=False,
        )
        try:
            result = c.wait(timeout=60)
            output = c.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            log.debug("executeVoucher output:\n%s", output[-1500:])
            if result["StatusCode"] != 0:
                raise RuntimeError(
                    f"executeVoucher script exited {result['StatusCode']}. "
                    f"Output: {output[-800:]}"
                )
            return output
        finally:
            try:
                c.remove(force=True)
            except Exception:
                pass
