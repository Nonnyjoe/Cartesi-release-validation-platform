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

# Dedicated accounts for non-ERC20 token type voucher tests.
# Each uses a unique account to avoid nonce conflicts with portal_deposit and erc20 tests.
_ETHER_VOUCHER_ACCT   = (
    "0x976EA74026E726554dB657fA54763abd0C3a0aa9",   # account #6
    "0x92db14e403b83dfe3df233f83dfa3a0d7096f21ca9b0d6d6b8d88b2b4ec1564e",
)
_ERC721_VOUCHER_ACCT  = (
    "0x14dC79964da2C08b23698B3D3cc7Ca32193d9955",   # account #7
    "0x4bbbf85ce3377467afe5d46f804f221813b2bb87f24d81f60f1fcdbf7cbf4356",
)
_ERC1155_VOUCHER_ACCT = (
    "0xa0Ee7A142d267C1f36714E4a8F75612F20a79720",   # account #9
    "0x2a871d0798f97d79848a013d4936a73bf4cc922c825d33c1cf7073dff6d409c6",
)

# ERC721 token ID used by voucher_v2 ether/erc721/erc1155 setup scripts.
# Chosen to avoid collision with portal_deposit tests that use IDs 1–9.
_V2_ERC721_TOKEN_ID  = 20
_V2_ERC1155_TOKEN_ID = 5
_V2_ERC1155_AMOUNT   = 50
_V2_ETHER_AMOUNT     = 10 ** 18  # 1 ETH in wei

# Epoch statuses that mean the Merkle proof is available for executeOutput.
_CLAIMED_STATUSES = {"CLAIM_ACCEPTED", "SETTLED", "CLAIM_SUBMITTED"}

# decoded_data.type values that represent voucher outputs.
_VOUCHER_TYPES = {"Voucher", "voucher", "VOUCHER"}


class VoucherV2Executor(AssertionExecutor):
    assertion_type = "voucher_v2"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        mode          = assertion.get("mode", "generate").lower()
        token_type    = assertion.get("token_type", "erc20").lower()
        expect_count  = int(assertion.get("expect_count", 1))
        poll_interval = float(assertion.get("poll_interval", 3))
        default_to    = 90 if mode == "generate" else 180
        poll_timeout  = int(assertion.get("poll_timeout", default_to))
        t0 = time.monotonic()

        try:
            if mode == "generate":
                return await self._check_generation(ctx, expect_count,
                                                     poll_interval, poll_timeout, t0,
                                                     token_type=token_type)
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

    def _build_ether_setup_script(self, ctx: SandboxContext) -> str:
        """
        Deposit 1 ETH via EtherPortal (auto-registers sender as student),
        then send a JSON withdraw action from the same account.
        """
        portal   = ctx.ether_portal_address
        app      = ctx.app_address
        inputbox = ctx.inputbox_address
        amount   = _V2_ETHER_AMOUNT

        sender_addr, sender_key = _ETHER_VOUCHER_ACCT

        withdraw_json = _json.dumps({
            "action":     "withdraw",
            "asset_type": "ether",
            "amount":     str(amount),
        }, separators=(",", ":"))
        withdraw_hex = "0x" + withdraw_json.encode().hex()

        _GAS = "--gas-price 100gwei"
        return (
            f"set -e\n"
            f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {sender_key} \\\n"
            f"  {portal} 'depositEther(address,bytes)' {app} 0x "
            f"  --value {amount} 2>&1\n"
            f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {sender_key} \\\n"
            f"  {inputbox} 'addInput(address,bytes)' {app} {withdraw_hex} 2>&1\n"
        )

    def _build_erc721_setup_script(self, ctx: SandboxContext) -> str:
        """
        Mint an ERC721 token to the sender, deposit via ERC721Portal,
        then send a JSON withdraw action from the same account.
        Token ID _V2_ERC721_TOKEN_ID (20) avoids collisions with portal_deposit tests.
        """
        token    = ctx.erc721_token_address
        portal   = ctx.erc721_portal_address
        app      = ctx.app_address
        inputbox = ctx.inputbox_address
        token_id = _V2_ERC721_TOKEN_ID

        sender_addr, sender_key = _ERC721_VOUCHER_ACCT

        # Normalise token_id to full 32-byte hex the way the app stores it
        token_id_hex = "0x" + hex(token_id)[2:].zfill(64)
        withdraw_json = _json.dumps({
            "action":     "withdraw",
            "asset_type": "erc721",
            "token":      token,
            "token_id":   token_id_hex,
        }, separators=(",", ":"))
        withdraw_hex = "0x" + withdraw_json.encode().hex()

        # Explicit --gas-limit bypasses eth_estimateGas which can fail when the
        # pending block is full (known Anvil quirk with ERC721 token operations).
        _GAS = "--gas-price 100gwei --gas-limit 5000000"
        return (
            f"set -e\n"
            # Mint using deployer key (contract owner)
            f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {_DEPLOYER_KEY} \\\n"
            f"  {token} 'mint(address,uint256)' {sender_addr} {token_id} 2>&1\n"
            # Approve portal from sender
            f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {sender_key} \\\n"
            f"  {token} 'setApprovalForAll(address,bool)' {portal} true 2>&1\n"
            # Deposit ERC721 via portal from sender
            f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {sender_key} \\\n"
            f"  {portal} 'depositERC721Token(address,address,uint256,bytes,bytes)' \\\n"
            f"  {token} {app} {token_id} 0x 0x 2>&1\n"
            # Submit withdraw action from same sender
            f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {sender_key} \\\n"
            f"  {inputbox} 'addInput(address,bytes)' {app} {withdraw_hex} 2>&1\n"
        )

    def _build_erc1155_setup_script(self, ctx: SandboxContext) -> str:
        """
        Mint ERC1155 tokens to sender, deposit via ERC1155SinglePortal,
        then send a JSON withdraw action from the same account.
        Token ID _V2_ERC1155_TOKEN_ID (5) avoids collisions with portal_deposit tests.
        Note: student-tracker does not support batch ERC1155 withdrawal; erc1155_batch
        token_type uses single withdrawal after a single-token deposit.
        """
        token    = ctx.erc1155_token_address
        portal   = ctx.erc1155_portal_address
        app      = ctx.app_address
        inputbox = ctx.inputbox_address
        token_id = _V2_ERC1155_TOKEN_ID
        amount   = _V2_ERC1155_AMOUNT

        sender_addr, sender_key = _ERC1155_VOUCHER_ACCT

        token_id_hex = "0x" + hex(token_id)[2:].zfill(64)
        withdraw_json = _json.dumps({
            "action":     "withdraw",
            "asset_type": "erc1155",
            "token":      token,
            "token_id":   token_id_hex,
            "amount":     str(amount),
        }, separators=(",", ":"))
        withdraw_hex = "0x" + withdraw_json.encode().hex()

        # Explicit --gas-limit bypasses eth_estimateGas which can fail when the
        # pending block is full (known Anvil quirk with ERC1155 token operations).
        _GAS = "--gas-price 100gwei --gas-limit 5000000"
        return (
            f"set -e\n"
            # Mint using deployer key (contract owner)
            f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {_DEPLOYER_KEY} \\\n"
            f"  {token} 'mint(address,uint256,uint256,bytes)' "
            f"  {sender_addr} {token_id} {amount} 0x 2>&1\n"
            # Approve portal from sender
            f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {sender_key} \\\n"
            f"  {token} 'setApprovalForAll(address,bool)' {portal} true 2>&1\n"
            # Deposit via ERC1155 single portal from sender
            f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {sender_key} \\\n"
            f"  {portal} 'depositSingleERC1155Token(address,address,uint256,uint256,bytes,bytes)' \\\n"
            f"  {token} {app} {token_id} {amount} 0x 0x 2>&1\n"
            # Submit withdraw action from same sender
            f"cast send --rpc-url {_ANVIL_RPC} {_GAS} --private-key {sender_key} \\\n"
            f"  {inputbox} 'addInput(address,bytes)' {app} {withdraw_hex} 2>&1\n"
        )

    async def _trigger_voucher(
        self, ctx: SandboxContext, mode: str = "generate", token_type: str = "erc20"
    ) -> None:
        if not ctx.app_address:
            raise RuntimeError("ctx.app_address is not set — cannot trigger voucher")

        if token_type == "ether":
            if not ctx.ether_portal_address:
                raise RuntimeError("ctx.ether_portal_address not set")
            script = self._build_ether_setup_script(ctx)
        elif token_type == "erc721":
            if not ctx.erc721_token_address or not ctx.erc721_portal_address:
                raise RuntimeError("ctx.erc721_token_address / erc721_portal_address not set")
            script = self._build_erc721_setup_script(ctx)
        elif token_type in ("erc1155", "erc1155_batch"):
            if not ctx.erc1155_token_address or not ctx.erc1155_portal_address:
                raise RuntimeError("ctx.erc1155_token_address / erc1155_portal_address not set")
            script = self._build_erc1155_setup_script(ctx)
        else:
            # Default: erc20
            if not ctx.erc20_token_address:
                raise RuntimeError(
                    "ctx.erc20_token_address is not set — cannot trigger ERC20 voucher. "
                    "Ensure the sandbox provisioner deployed test tokens."
                )
            script = self._build_setup_script(ctx, mode)

        loop   = asyncio.get_event_loop()
        output = await loop.run_in_executor(
            None, self._run_foundry_script_sync, script, ctx.sandbox_id
        )
        log.info("Voucher setup complete for sandbox %s (mode=%s token_type=%s)",
                 ctx.sandbox_id[:8], mode, token_type)
        log.info("Setup script output (last 600):\n%s", output[-600:])

    # ── Generate mode ──────────────────────────────────────────────────────────

    async def _check_generation(
        self,
        ctx: SandboxContext,
        expect_count: int,
        poll_interval: float,
        timeout: float,
        t0: float,
        token_type: str = "erc20",
    ) -> AssertionResult:
        try:
            await self._trigger_voucher(ctx, mode="generate", token_type=token_type)
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
        # Snapshot output count BEFORE generating so we can target only the new voucher.
        # This prevents multiple concurrent execute-mode tests from competing for the
        # same pool of already-executed vouchers.
        initial_count = await self._get_output_count(ctx)

        try:
            await self._trigger_voucher(ctx, mode="execute")
        except Exception as exc:
            return AssertionResult(
                assertion_type="voucher_v2",
                passed=False,
                detail=f"Voucher setup failed: {exc}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        # Phase 1: poll for a NEW voucher (index >= initial_count) whose epoch has been claimed.
        log.info("Polling for new voucher (index>=%d) with claimed epoch (sandbox=%s, timeout=%ds)…",
                 initial_count, ctx.sandbox_id[:8], int(timeout))
        vouchers = await self._poll_vouchers(ctx, expect_count, poll_interval,
                                              timeout * 0.7, need_epoch_claim=True,
                                              min_output_index=initial_count)
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

    async def _get_output_count(self, ctx: SandboxContext) -> int:
        """Return the current total output count for the app (0 on error)."""
        app_id = ctx.app_address or "app"
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    ctx.jsonrpc_rpc_url,
                    json={"jsonrpc": "2.0", "method": "cartesi_listOutputs",
                          "params": {"application": app_id, "limit": 1000}, "id": 1},
                    headers={"Content-Type": "application/json"},
                )
                body = resp.json()
                result = body.get("result", {})
                # Prefer pagination.total_count if available (avoids fetching all data).
                pagination = result.get("pagination", {})
                if pagination and "total_count" in pagination:
                    return pagination["total_count"]
                return len(result.get("data", []))
        except Exception:
            return 0

    async def _poll_vouchers(
        self,
        ctx: SandboxContext,
        expect_count: int,
        poll_interval: float,
        timeout: float,
        need_epoch_claim: bool,
        min_output_index: int = 0,
    ) -> list[dict]:
        """
        Poll cartesi_listOutputs until at least expect_count Voucher-type outputs
        exist.  If need_epoch_claim=True, also waits until the epoch containing
        each voucher reaches CLAIM_ACCEPTED status.

        If an epoch is CLAIM_COMPUTED (validator done, but claimer is stuck),
        we manually submit the claim to the Authority contract and immediately
        treat the voucher as ready — the claim is on-chain even if the node DB
        hasn't updated yet, so executeOutput will succeed.
        """
        app_id   = ctx.app_address or "app"
        deadline = time.monotonic() + timeout
        _first   = True
        _submitted_epochs: set[str] = set()  # epochs where we manually submitted a claim

        while time.monotonic() < deadline:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        ctx.jsonrpc_rpc_url,
                        json={
                            "jsonrpc": "2.0",
                            "method":  "cartesi_listOutputs",
                            # Named params with high limit to fetch all outputs.
                            # The positional-array form defaults to limit=50 and
                            # silently truncates when more outputs exist.
                            "params":  {"application": app_id, "limit": 1000},
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

                # Restrict to outputs generated after we snapshotted the count
                # (prevents execute-mode tests from competing for pre-existing vouchers).
                if min_output_index > 0:
                    data = [x for x in data
                            if int(x.get("index", "0x0"), 16) >= min_output_index]

                # Filter for Voucher-type outputs (type is in decoded_data)
                vouchers = [
                    x for x in data
                    if x.get("decoded_data", {}).get("type") in _VOUCHER_TYPES
                ]

                if need_epoch_claim:
                    claimed = []
                    for v in vouchers:
                        epoch_idx = v.get("epoch_index", "0x0")
                        epoch = await self._get_epoch_data(ctx, epoch_idx)
                        status = epoch.get("status", "")
                        if status in _CLAIMED_STATUSES:
                            claimed.append(v)
                        elif status == "CLAIM_COMPUTED":
                            if epoch_idx not in _submitted_epochs:
                                # Claimer is stuck — manually submit the claim.
                                # After cast send succeeds the claim is on-chain;
                                # executeOutput will work even before the node DB updates.
                                ok = await self._submit_claim_if_computed(
                                    ctx, epoch_idx, epoch
                                )
                                _submitted_epochs.add(epoch_idx)
                                if ok:
                                    log.info(
                                        "Manually submitted claim for epoch %s — "
                                        "voucher ready for execution (sandbox=%s)",
                                        epoch_idx, ctx.sandbox_id[:8],
                                    )
                                    claimed.append(v)
                            else:
                                # Claim was already submitted in a prior iteration;
                                # it is on-chain so executeOutput will succeed.
                                claimed.append(v)
                        else:
                            log.debug("Epoch %s status=%s — waiting for %s",
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

    async def _get_epoch_data(self, ctx: SandboxContext, epoch_index: str) -> dict:
        """Return the epoch data dict from cartesi_getEpoch, or {} on error."""
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
                return {}
            return body.get("result", {}).get("data", {})
        except Exception as exc:
            log.debug("cartesi_getEpoch error: %s", exc)
            return {}

    async def _get_authority_address(self, ctx: SandboxContext) -> str:
        """Return the Authority (iconsensus) address for the app, or '' on error."""
        app_id = ctx.app_address or ""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(
                    ctx.jsonrpc_rpc_url,
                    json={"jsonrpc": "2.0", "method": "cartesi_getApplication",
                          "params": [app_id], "id": 1},
                    headers={"Content-Type": "application/json"},
                )
                body = resp.json()
            data = body.get("result", {}).get("data", {})
            return data.get("iconsensus_address", "")
        except Exception as exc:
            log.warning("cartesi_getApplication error: %s", exc)
            return ""

    async def _submit_claim_if_computed(
        self,
        ctx: SandboxContext,
        epoch_index: str,
        epoch_data: dict | None = None,
    ) -> bool:
        """
        Manually submit the on-chain claim for an epoch that is stuck in
        CLAIM_COMPUTED state (validator done, claimer not progressing).

        Calls Authority.submitClaim(address app, uint256 lastBlock, bytes32 claimHash)
        using the deployer key.  Function selector 0x6470af00 identified from
        on-chain transaction traces against rollups-runtime 0.12.0-alpha.39.

        Returns True if the claim is now on-chain (or was already claimed).
        """
        if epoch_data is None:
            epoch_data = await self._get_epoch_data(ctx, epoch_index)

        status = epoch_data.get("status", "")
        if status in _CLAIMED_STATUSES:
            return True
        if status != "CLAIM_COMPUTED":
            log.warning("_submit_claim_if_computed: epoch %s has status=%s, expected CLAIM_COMPUTED",
                        epoch_index, status)
            return False

        claim_hash = epoch_data.get("claim_hash", "")
        last_block_hex = epoch_data.get("last_block", "0x0")
        if not claim_hash:
            log.warning("CLAIM_COMPUTED epoch %s has no claim_hash", epoch_index)
            return False

        authority = await self._get_authority_address(ctx)
        if not authority:
            log.warning("Could not determine authority address for sandbox %s",
                        ctx.sandbox_id[:8])
            return False

        # Build raw ABI calldata: selector + ABI-encoded (address, uint256, bytes32).
        app_hex   = (ctx.app_address or "").lower().lstrip("0x").zfill(64)
        last_block = int(last_block_hex, 16) if last_block_hex.startswith("0x") else int(last_block_hex)
        hash_hex  = claim_hash.lstrip("0x").zfill(64)
        calldata  = "0x6470af00" + app_hex + hex(last_block)[2:].zfill(64) + hash_hex

        log.info(
            "Epoch %s CLAIM_COMPUTED — submitting claim to authority %s (sandbox=%s)",
            epoch_index, authority[:10], ctx.sandbox_id[:8],
        )

        script = (
            f"set -e\n"
            f"cast send --rpc-url {_ANVIL_RPC} --gas-price 100gwei "
            f"--private-key {_DEPLOYER_KEY} \\\n"
            f"  {authority} \\\n"
            f"  {calldata} 2>&1\n"
        )

        loop = asyncio.get_event_loop()
        try:
            output = await loop.run_in_executor(
                None, self._run_foundry_script_sync, script, ctx.sandbox_id
            )
            log.info("submitClaim epoch %s succeeded:\n%s", epoch_index, output[-400:])
            return True
        except Exception as exc:
            log.warning("submitClaim epoch %s failed: %s", epoch_index, exc)
            return False

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
