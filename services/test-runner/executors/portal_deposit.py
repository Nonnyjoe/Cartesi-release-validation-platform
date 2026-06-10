"""
services/test-runner/executors/portal_deposit.py
Assertion type: portal_deposit

Sends an asset deposit to a Cartesi portal contract on the sandbox Anvil:
  token_type: ether    → EtherPortal.depositEther(app, 0x)
  token_type: erc20    → deploy test ERC20 → mint → approve → ERC20Portal.depositERC20Tokens
  token_type: erc721   → deploy test ERC721 → mint → setApprovalForAll → ERC721Portal.depositERC721Token
  token_type: erc1155  → deploy test ERC1155 → mint → setApprovalForAll → ERC1155SinglePortal.depositSingleERC1155Token

For ERC20/ERC721/ERC1155 the executor spins up a temporary Foundry container
(ghcr.io/foundry-rs/foundry:latest) in the Anvil container's network namespace,
writes minimal Solidity source via base64, compiles with `forge create`, then
interacts with the portal using `cast send`.  The Docker socket must be mounted
into the test-runner container (it is, per docker-compose.yml).

Assertion YAML fields:
  type: portal_deposit
  token_type: ether | erc20 | erc721 | erc1155
  amount: <int>   # wei for ether; token units (no decimals) for ERC20; ignored for ERC721
  token_id: <int> # token ID for ERC721 / ERC1155 (default 1)
"""
import asyncio
import base64
import logging
import time
import uuid

import httpx

from .base import (AssertionExecutor, AssertionResult, SandboxContext,
                   fetch_input_count, count_before_result, count_after_result)

log = logging.getLogger("test-runner.executor.portal_deposit")

# Dedicated Anvil accounts per token type to avoid nonce conflicts when
# ERC20, ERC721, and ERC1155 portal tests run concurrently on the same sandbox.
_FOUNDRY_IMG  = "ghcr.io/foundry-rs/foundry:latest"
_ANVIL_RPC    = "http://localhost:8545"

# Account #0 — deployer / ether tests (unlocked for eth_sendTransaction)
_DEPLOYER_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
_SENDER       = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

# Account #3 — ERC721 portal tests
_ERC721_KEY    = "0x7c852118294e51e653712a81e05800f419141751be58f605c371e15141b007a6"
_ERC721_SENDER = "0x90F79bf6EB2c4f870365E785982E1f101E93b906"

# Account #5 — ERC20 direct/e2e portal tests (separate from account #0 to avoid nonce conflicts)
_ERC20_E2E_KEY    = "0x8b3a350cf5c34c9194ca85829a2df0ec3153be0318b5e2d3348e872092edffba"
_ERC20_E2E_SENDER = "0x9965507D1a55bcC2695C58ba16FB37d819B0A4dc"

# Account #8 — ERC1155 portal tests (separate from ERC20/ERC721 to avoid nonce conflicts)
_ERC1155_KEY    = "0xdbda1821b80551c9d65939329250132c444d90ea74307f05f60ce6b0c942d0c8"
_ERC1155_SENDER = "0x23618e81E3f5cdF7f54C3d65f7FBc0aBf5B21E8f"

# ── Test token Solidity sources (OpenZeppelin wrappers) ──────────────────────
# Thin wrappers that inherit from OpenZeppelin standard implementations.
# Used only as a fallback when tokens were not pre-deployed by the provisioner.
# The deploy scripts install OZ via forge soldeer (no git required).
# Identical to the contracts in services/sandbox-manager/provisioner.py
# — keep in sync.

_ERC20_SOL = """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts/token/ERC20/ERC20.sol";
contract TestERC20 is ERC20 {
    constructor() ERC20("Test Token", "TST") {}
    function mint(address to, uint256 amount) external { _mint(to, amount); }
}
"""

_ERC721_SOL = """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
contract TestERC721 is ERC721 {
    constructor() ERC721("Test NFT", "TNFT") {}
    function mint(address to, uint256 tokenId) external { _safeMint(to, tokenId); }
}
"""

_ERC1155_SOL = """\
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;
import "@openzeppelin/contracts/token/ERC1155/ERC1155.sol";
contract TestERC1155 is ERC1155 {
    constructor() ERC1155("") {}
    function mint(address to, uint256 id, uint256 amount) external { _mint(to, id, amount, ""); }
}
"""


def _b64(s: str) -> str:
    return base64.b64encode(s.encode()).decode()


def _pad32(val: str) -> str:
    """Left-pad a hex value (no 0x prefix) to 64 hex chars (32 bytes)."""
    return val.lower().removeprefix("0x").zfill(64)


def _abi_encode_deposit_ether(app_address: str, exec_layer_data: str = "0x") -> str:
    """
    ABI-encode EtherPortal.depositEther(address _dapp, bytes calldata _execLayerData).
    Selector: keccak256("depositEther(address,bytes)")[:4] = 0x938c054f
    """
    selector = "938c054f"
    addr   = _pad32(app_address)
    offset = _pad32("40")   # offset to bytes param = 64
    data_bytes = bytes.fromhex(exec_layer_data.removeprefix("0x")) if exec_layer_data and exec_layer_data != "0x" else b""
    length = _pad32(hex(len(data_bytes))[2:])
    # Pad data to 32-byte boundary
    padded = data_bytes + b"\x00" * ((32 - len(data_bytes) % 32) % 32)
    return "0x" + selector + addr + offset + length + padded.hex()


def _abi_encode_erc721_mint(to_addr: str, token_id: int) -> str:
    """ABI-encode mint(address,uint256) calldata. Selector: 0x40c10f19"""
    return "0x" + (
        bytes.fromhex("40c10f19")
        + bytes.fromhex(to_addr[2:]).rjust(32, b'\x00')
        + token_id.to_bytes(32, 'big')
    ).hex()


def _abi_encode_erc721_deposit(token: str, app: str, token_id: int) -> str:
    """
    ABI-encode depositERC721Token(address,address,uint256,bytes,bytes)
    with empty bytes for baseLayerData and execLayerData. Selector: 0x28911e83
    """
    head = (
        bytes.fromhex(token[2:]).rjust(32, b'\x00')
        + bytes.fromhex(app[2:]).rjust(32, b'\x00')
        + token_id.to_bytes(32, 'big')
        + (160).to_bytes(32, 'big')   # offset to bytes1 tail = 5*32
        + (192).to_bytes(32, 'big')   # offset to bytes2 tail = 5*32 + 1*32
    )
    tail = (0).to_bytes(32, 'big') + (0).to_bytes(32, 'big')  # empty bytes lengths
    return "0x" + (bytes.fromhex("28911e83") + head + tail).hex()


def _abi_encode_erc1155_mint(to_addr: str, token_id: int, amount: int) -> str:
    """ABI-encode mint(address,uint256,uint256) calldata. Selector: 0x156e29f6"""
    return "0x" + (
        bytes.fromhex("156e29f6")
        + bytes.fromhex(to_addr[2:]).rjust(32, b'\x00')
        + token_id.to_bytes(32, 'big')
        + amount.to_bytes(32, 'big')
    ).hex()


def _abi_encode_set_approval_for_all(operator: str, approved: bool) -> str:
    """ABI-encode setApprovalForAll(address,bool) calldata. Selector: 0xa22cb465"""
    return "0x" + (
        bytes.fromhex("a22cb465")
        + bytes.fromhex(operator[2:]).rjust(32, b'\x00')
        + int(approved).to_bytes(32, 'big')
    ).hex()


def _abi_encode_erc1155_deposit(token: str, app: str, token_id: int, amount: int) -> str:
    """
    ABI-encode depositSingleERC1155Token(address,address,uint256,uint256,bytes,bytes)
    with empty bytes for the last two arguments. Selector: 0xdec07dca
    """
    head = (
        bytes.fromhex(token[2:]).rjust(32, b'\x00')
        + bytes.fromhex(app[2:]).rjust(32, b'\x00')
        + token_id.to_bytes(32, 'big')
        + amount.to_bytes(32, 'big')
        + (192).to_bytes(32, 'big')   # offset to bytes1 tail = 6*32
        + (224).to_bytes(32, 'big')   # offset to bytes2 tail = 6*32+32
    )
    tail = (0).to_bytes(32, 'big') + (0).to_bytes(32, 'big')  # empty bytes lengths
    return "0x" + (bytes.fromhex("dec07dca") + head + tail).hex()


class PortalDepositExecutor(AssertionExecutor):
    assertion_type = "portal_deposit"

    async def execute(self, assertion: dict, ctx: SandboxContext) -> AssertionResult:
        token_type = assertion.get("token_type", "ether").lower()
        amount     = int(assertion.get("amount", 1_000_000_000_000_000_000))  # 1 ETH / 1e18 tokens
        token_id   = int(assertion.get("token_id", 1))
        t0 = time.monotonic()

        # Snapshot input count before deposit so the detail shows the delta.
        before_count = (
            await fetch_input_count(ctx.jsonrpc_rpc_url, ctx.app_address or "app")
            if ctx.node_major_version >= 2 else -1
        )

        try:
            if token_type == "ether":
                result = await self._deposit_ether(assertion, ctx, amount, t0)
            elif token_type == "erc20":
                result = await self._deposit_erc20(assertion, ctx, amount, t0)
            elif token_type == "erc721":
                result = await self._deposit_erc721(assertion, ctx, token_id, t0)
            elif token_type == "erc1155":
                result = await self._deposit_erc1155(assertion, ctx, token_id, amount, t0)
            elif token_type == "erc1155_batch":
                result = await self._deposit_erc1155_batch(assertion, ctx, t0)
            else:
                return AssertionResult(
                    assertion_type="portal_deposit",
                    passed=False,
                    detail=f"Unknown token_type: {token_type!r} (expected ether|erc20|erc721|erc1155|erc1155_batch)",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
        except Exception as exc:
            log.exception("portal_deposit error: %s", exc)
            return AssertionResult(
                assertion_type="portal_deposit",
                passed=False,
                detail=f"{type(exc).__name__}: {exc}",
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
                result,
                count_after_result("inputs", before_count, after_count),
            ]
        return result

    # ── Ether deposit ──────────────────────────────────────────────────────────

    async def _deposit_ether(self, assertion: dict, ctx: SandboxContext,
                              amount: int, t0: float) -> AssertionResult:
        portal  = ctx.ether_portal_address
        app     = ctx.app_address or "0x0000000000000000000000000000000000000001"
        rpc_url = ctx.anvil_rpc_url

        # Verify portal has code (sanity check for address correctness)
        code = await self._get_code(rpc_url, portal)
        if code == "0x":
            return AssertionResult(
                assertion_type="portal_deposit",
                passed=False,
                detail=f"EtherPortal has no bytecode at {portal} — wrong address or not deployed",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        exec_layer_data = assertion.get("exec_layer_data", "0x")
        calldata   = _abi_encode_deposit_ether(app, exec_layer_data)
        hex_amount = hex(amount)

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(rpc_url, json={
                    "jsonrpc": "2.0",
                    "method":  "eth_sendTransaction",
                    "params":  [{
                        "from":  _SENDER,
                        "to":    portal,
                        "data":  calldata,
                        "value": hex_amount,
                    }],
                    "id": 1,
                })
                data = resp.json()
                if "error" in data:
                    raise RuntimeError(f"eth_sendTransaction error: {data['error']}")
                tx_hash = data.get("result")

            # Wait for receipt
            receipt = await self._wait_receipt(rpc_url, tx_hash)
            status  = int(receipt.get("status", "0x0"), 16)
            passed  = (status == 1)
            return AssertionResult(
                assertion_type="portal_deposit",
                passed=passed,
                expected="ether deposit tx status=1",
                actual=f"tx status={status}",
                detail=(
                    f"EtherPortal.depositEther(app={app[:10]}…, 0x) "
                    f"value={amount} wei → tx={tx_hash[:12]}… status={status}"
                ),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            log.warning("ether deposit error: %s", exc)
            return AssertionResult(
                assertion_type="portal_deposit",
                passed=False,
                detail=str(exc),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

    # ── ERC20 deposit ──────────────────────────────────────────────────────────

    async def _deposit_erc20(self, assertion: dict, ctx: SandboxContext,
                              amount: int, t0: float) -> AssertionResult:
        portal   = ctx.erc20_portal_address
        app      = ctx.app_address or "0x0000000000000000000000000000000000000001"
        token    = ctx.erc20_token_address  # pre-deployed by provisioner (may be None)
        use_alt  = assertion.get("use_alt_sender", False)
        rpc_url  = ctx.anvil_rpc_url

        code = await self._get_code(rpc_url, portal)
        if code == "0x":
            return AssertionResult(
                assertion_type="portal_deposit",
                passed=False,
                detail=f"ERC20Portal has no bytecode at {portal}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        # Direct path: use JSON-RPC directly to avoid cast nonce races on
        # interval-mining Anvil (--block-time 1). Preferred when a pre-deployed
        # token is available and the caller requests the alternative account.
        if token and use_alt:
            try:
                detail = await self._deposit_erc20_direct(token, portal, app, amount, rpc_url)
                return AssertionResult(
                    assertion_type="portal_deposit",
                    passed=True,
                    expected="ERC20 deposit tx status=1",
                    actual="deposit transaction confirmed",
                    detail=detail,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
            except Exception as exc:
                return AssertionResult(
                    assertion_type="portal_deposit",
                    passed=False,
                    detail=f"ERC20 direct deposit failed: {exc}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

        loop = asyncio.get_event_loop()
        if token:
            # Fast path: token already deployed — just mint, approve, deposit
            script = self._build_erc20_deposit_script(token, portal, app, amount)
        else:
            # Fallback: deploy token first then deposit (slow, ~60 s)
            script = self._build_erc20_script(portal, app, amount)

        try:
            output = await loop.run_in_executor(
                None, self._run_foundry_script_sync, script, ctx.sandbox_id
            )
        except Exception as exc:
            return AssertionResult(
                assertion_type="portal_deposit",
                passed=False,
                detail=f"ERC20 deposit script failed: {exc}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        # Script exits non-zero on any cast send failure; if we reach here all txs succeeded.
        token_label = token or self._parse_deployed(output) or "?"
        return AssertionResult(
            assertion_type="portal_deposit",
            passed=True,
            expected="ERC20 deposit tx status=1",
            actual="deposit transaction confirmed",
            detail=(
                f"TestERC20 at {token_label[:12]}…  "
                f"mint({amount}) → approve(ERC20Portal) → "
                f"depositERC20Tokens(token, app={app[:10]}…, amount={amount})"
            ),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    async def _deposit_erc20_direct(self, token: str, portal: str, app: str,
                                     amount: int, rpc_url: str) -> str:
        """
        Perform ERC20 deposit via direct eth_sendTransaction calls using account #5.
        Avoids cast nonce races when multiple ERC20 tests run on interval-mining Anvil.
        """
        async def send_and_wait(sender: str, to: str, data: str) -> None:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(rpc_url, json={
                    "jsonrpc": "2.0",
                    "method":  "eth_sendTransaction",
                    "params":  [{"from": sender, "to": to, "data": data}],
                    "id":      1,
                })
                result = resp.json()
                if "error" in result:
                    raise RuntimeError(f"eth_sendTransaction error: {result['error']}")
                tx_hash = result["result"]
            receipt = await self._wait_receipt(rpc_url, tx_hash)
            if int(receipt.get("status", "0x0"), 16) != 1:
                raise RuntimeError(f"Transaction reverted: {tx_hash}")

        # mint(address,uint256): selector 0x40c10f19
        # _SENDER (account #0) is the token owner and can mint to the alt sender
        mint_data = "0x" + (
            bytes.fromhex("40c10f19")
            + bytes.fromhex(_ERC20_E2E_SENDER[2:]).rjust(32, b'\x00')
            + amount.to_bytes(32, 'big')
        ).hex()
        await send_and_wait(_SENDER, token, mint_data)

        # approve(address,uint256): selector 0x095ea7b3
        approve_data = "0x" + (
            bytes.fromhex("095ea7b3")
            + bytes.fromhex(portal[2:]).rjust(32, b'\x00')
            + amount.to_bytes(32, 'big')
        ).hex()
        await send_and_wait(_ERC20_E2E_SENDER, token, approve_data)

        # depositERC20Tokens(address,address,uint256,bytes): selector 0x21425ee0
        deposit_data = "0x" + (
            bytes.fromhex("21425ee0")
            + bytes.fromhex(token[2:]).rjust(32, b'\x00')
            + bytes.fromhex(app[2:]).rjust(32, b'\x00')
            + amount.to_bytes(32, 'big')
            + (128).to_bytes(32, 'big')   # offset to execLayerData
            + (0).to_bytes(32, 'big')     # length of execLayerData = 0
        ).hex()
        await send_and_wait(_ERC20_E2E_SENDER, portal, deposit_data)

        return (
            f"TestERC20 at {token[:12]}…  "
            f"mint({amount}) → approve(ERC20Portal) → "
            f"depositERC20Tokens(token, app={app[:10]}…, amount={amount})"
        )

    # ── ERC721 deposit ─────────────────────────────────────────────────────────

    async def _deposit_erc721(self, assertion: dict, ctx: SandboxContext,
                               token_id: int, t0: float) -> AssertionResult:
        portal = ctx.erc721_portal_address
        app    = ctx.app_address or "0x0000000000000000000000000000000000000001"
        token  = ctx.erc721_token_address

        code = await self._get_code(ctx.anvil_rpc_url, portal)
        if code == "0x":
            return AssertionResult(
                assertion_type="portal_deposit",
                passed=False,
                detail=f"ERC721Portal has no bytecode at {portal}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        if token:
            # Fast path: direct JSON-RPC (no cast gas estimation).
            # eth_estimateGas fails when the token already exists (re-mint on
            # same sandbox) or when the pending Anvil block is full. Using
            # eth_sendTransaction directly bypasses this.
            try:
                detail = await self._deposit_erc721_direct(
                    token, portal, app, token_id, ctx.anvil_rpc_url
                )
                return AssertionResult(
                    assertion_type="portal_deposit",
                    passed=True,
                    expected="ERC721 deposit tx status=1",
                    actual="deposit transaction confirmed",
                    detail=detail,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
            except Exception as exc:
                return AssertionResult(
                    assertion_type="portal_deposit",
                    passed=False,
                    detail=f"ERC721 direct deposit failed: {exc}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

        loop = asyncio.get_event_loop()
        script = self._build_erc721_script(portal, app, token_id)

        try:
            output = await loop.run_in_executor(
                None, self._run_foundry_script_sync, script, ctx.sandbox_id
            )
        except Exception as exc:
            return AssertionResult(
                assertion_type="portal_deposit",
                passed=False,
                detail=f"ERC721 deposit script failed: {exc}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        token_label = self._parse_deployed(output) or "?"
        return AssertionResult(
            assertion_type="portal_deposit",
            passed=True,
            expected="ERC721 deposit tx status=1",
            actual="deposit transaction confirmed",
            detail=(
                f"TestERC721 at {token_label[:12]}…  "
                f"mint(id={token_id}) → setApprovalForAll(ERC721Portal) → "
                f"depositERC721Token(token, app={app[:10]}…, id={token_id})"
            ),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    # ── ERC1155 deposit ────────────────────────────────────────────────────────

    async def _deposit_erc1155(self, assertion: dict, ctx: SandboxContext,
                                token_id: int, amount: int, t0: float) -> AssertionResult:
        portal  = ctx.erc1155_portal_address
        app     = ctx.app_address or "0x0000000000000000000000000000000000000001"
        token   = ctx.erc1155_token_address
        rpc_url = ctx.anvil_rpc_url

        code = await self._get_code(rpc_url, portal)
        if code == "0x":
            return AssertionResult(
                assertion_type="portal_deposit",
                passed=False,
                detail=f"ERC1155SinglePortal has no bytecode at {portal}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        if token:
            # Fast path: direct JSON-RPC (no cast gas estimation).
            # eth_estimateGas fails when the pending Anvil block is full during
            # concurrent test execution. Using eth_sendTransaction directly bypasses
            # this by letting Anvil handle gas estimation internally.
            try:
                detail = await self._deposit_erc1155_direct(
                    token, portal, app, token_id, amount, rpc_url
                )
                return AssertionResult(
                    assertion_type="portal_deposit",
                    passed=True,
                    expected="ERC1155 deposit tx status=1",
                    actual="deposit transaction confirmed",
                    detail=detail,
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )
            except Exception as exc:
                return AssertionResult(
                    assertion_type="portal_deposit",
                    passed=False,
                    detail=f"ERC1155 direct deposit failed: {exc}",
                    duration_ms=int((time.monotonic() - t0) * 1000),
                )

        # Fallback: use Foundry container to compile + deploy token, then deposit.
        loop = asyncio.get_event_loop()
        script = self._build_erc1155_script(portal, app, token_id, amount)
        try:
            output = await loop.run_in_executor(
                None, self._run_foundry_script_sync, script, ctx.sandbox_id
            )
        except Exception as exc:
            return AssertionResult(
                assertion_type="portal_deposit",
                passed=False,
                detail=f"ERC1155 deposit script failed: {exc}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        token_label = self._parse_deployed(output) or "?"
        return AssertionResult(
            assertion_type="portal_deposit",
            passed=True,
            expected="ERC1155 deposit tx status=1",
            actual="deposit transaction confirmed",
            detail=(
                f"TestERC1155 at {token_label[:12]}…  "
                f"mint({amount}×id={token_id}) → setApprovalForAll(ERC1155Portal) → "
                f"depositSingleERC1155Token(token, app={app[:10]}…, id={token_id}, value={amount})"
            ),
            duration_ms=int((time.monotonic() - t0) * 1000),
        )

    async def _deposit_erc1155_batch(self, assertion: dict, ctx: SandboxContext,
                                      t0: float) -> AssertionResult:
        """
        Simulate an ERC1155 batch deposit by making multiple sequential single deposits
        via ERC1155SinglePortal. Used when token_type: erc1155_batch is specified.
        token_ids and amounts must be parallel lists.
        """
        portal   = ctx.erc1155_portal_address
        app      = ctx.app_address or "0x0000000000000000000000000000000000000001"
        token    = ctx.erc1155_token_address
        rpc_url  = ctx.anvil_rpc_url
        token_ids = [int(x) for x in assertion.get("token_ids", [1, 2])]
        amounts   = [int(x) for x in assertion.get("amounts", [100, 100])]
        if len(token_ids) != len(amounts):
            return AssertionResult(
                assertion_type="portal_deposit",
                passed=False,
                detail="erc1155_batch: token_ids and amounts must have the same length",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        code = await self._get_code(rpc_url, portal)
        if code == "0x":
            return AssertionResult(
                assertion_type="portal_deposit",
                passed=False,
                detail=f"ERC1155SinglePortal has no bytecode at {portal}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        if not token:
            return AssertionResult(
                assertion_type="portal_deposit",
                passed=False,
                detail="erc1155_batch requires a pre-deployed ERC1155 token (erc1155_token_address not set in context)",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

        try:
            async def send_and_wait(to: str, data: str) -> None:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(rpc_url, json={
                        "jsonrpc": "2.0",
                        "method":  "eth_sendTransaction",
                        "params":  [{"from": _ERC1155_SENDER, "to": to, "data": data}],
                        "id":      1,
                    })
                    result = resp.json()
                    if "error" in result:
                        raise RuntimeError(f"eth_sendTransaction error: {result['error']}")
                    tx_hash = result["result"]
                receipt = await self._wait_receipt(rpc_url, tx_hash)
                if int(receipt.get("status", "0x0"), 16) != 1:
                    raise RuntimeError(f"Transaction reverted: {tx_hash}")

            # Mint all token IDs and set approval once
            for tid, amt in zip(token_ids, amounts):
                await send_and_wait(token, _abi_encode_erc1155_mint(_ERC1155_SENDER, tid, amt))
            await send_and_wait(token, _abi_encode_set_approval_for_all(portal, True))
            # Deposit each token ID separately via ERC1155SinglePortal
            for tid, amt in zip(token_ids, amounts):
                await send_and_wait(portal, _abi_encode_erc1155_deposit(token, app, tid, amt))

            return AssertionResult(
                assertion_type="portal_deposit",
                passed=True,
                expected=f"ERC1155 batch deposit ({len(token_ids)} tokens) via SinglePortal",
                actual="all deposits confirmed",
                detail=(
                    f"Deposited {len(token_ids)} token IDs via ERC1155SinglePortal: "
                    + ", ".join(f"id={t}×{a}" for t, a in zip(token_ids, amounts))
                ),
                duration_ms=int((time.monotonic() - t0) * 1000),
            )
        except Exception as exc:
            return AssertionResult(
                assertion_type="portal_deposit",
                passed=False,
                detail=f"erc1155_batch deposit failed: {exc}",
                duration_ms=int((time.monotonic() - t0) * 1000),
            )

    async def _deposit_erc721_direct(self, token: str, portal: str, app: str,
                                      token_id: int, rpc_url: str) -> str:
        """
        Perform ERC721 deposit via direct eth_sendTransaction calls (no cast).
        Bypasses eth_estimateGas failures that occur when the pending Anvil block
        is full. Uses a timestamp-derived token ID to avoid re-minting the same
        token ID on repeat runs on the same sandbox (each token ID is unique to
        one owner and gets transferred to the portal on deposit).
        Uses unlocked Anvil account #3 (_ERC721_SENDER).
        """
        # Use a unique effective token ID so the same sandbox can run this test
        # multiple times without hitting "token already owned by portal" errors.
        effective_id = token_id + int(time.monotonic() * 1000) % (10 ** 9) * 1000

        async def send_and_wait(to: str, data: str) -> None:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(rpc_url, json={
                    "jsonrpc": "2.0",
                    "method":  "eth_sendTransaction",
                    "params":  [{"from": _ERC721_SENDER, "to": to, "data": data}],
                    "id":      1,
                })
                result = resp.json()
                if "error" in result:
                    raise RuntimeError(f"eth_sendTransaction error: {result['error']}")
                tx_hash = result["result"]
            receipt = await self._wait_receipt(rpc_url, tx_hash)
            if int(receipt.get("status", "0x0"), 16) != 1:
                raise RuntimeError(f"Transaction reverted: {tx_hash}")

        await send_and_wait(token, _abi_encode_erc721_mint(_ERC721_SENDER, effective_id))
        await send_and_wait(token, _abi_encode_set_approval_for_all(portal, True))
        await send_and_wait(portal, _abi_encode_erc721_deposit(token, app, effective_id))

        return (
            f"TestERC721 at {token[:12]}…  "
            f"mint(id={effective_id}) → setApprovalForAll(ERC721Portal) → "
            f"depositERC721Token(token, app={app[:10]}…, id={effective_id})"
        )

    async def _deposit_erc1155_direct(self, token: str, portal: str, app: str,
                                       token_id: int, amount: int, rpc_url: str) -> str:
        """
        Perform ERC1155 deposit via direct eth_sendTransaction calls (no cast).
        Bypasses eth_estimateGas failures that occur when the Anvil pending block
        is full during concurrent test execution.
        Uses unlocked Anvil account #8 (_ERC1155_SENDER).
        """
        async def send_and_wait(to: str, data: str) -> None:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(rpc_url, json={
                    "jsonrpc": "2.0",
                    "method":  "eth_sendTransaction",
                    "params":  [{"from": _ERC1155_SENDER, "to": to, "data": data}],
                    "id":      1,
                })
                result = resp.json()
                if "error" in result:
                    raise RuntimeError(f"eth_sendTransaction error: {result['error']}")
                tx_hash = result["result"]
            receipt = await self._wait_receipt(rpc_url, tx_hash)
            if int(receipt.get("status", "0x0"), 16) != 1:
                raise RuntimeError(f"Transaction reverted: {tx_hash}")

        await send_and_wait(token, _abi_encode_erc1155_mint(_ERC1155_SENDER, token_id, amount))
        await send_and_wait(token, _abi_encode_set_approval_for_all(portal, True))
        await send_and_wait(portal, _abi_encode_erc1155_deposit(token, app, token_id, amount))

        return (
            f"TestERC1155 at {token[:12]}…  "
            f"mint({amount}×id={token_id}) → setApprovalForAll(ERC1155Portal) → "
            f"depositSingleERC1155Token(token, app={app[:10]}…, id={token_id}, value={amount})"
        )

    # ── Fast-path script builders (pre-deployed token, no forge compile) ────────

    def _build_erc20_deposit_script(self, token: str, portal: str, app: str, amount: int) -> str:
        """mint → approve → depositERC20Tokens using an already-deployed token contract."""
        _GAS = "--gas-price 100gwei"
        return (
            f"set -e\n"
            f"cast send --private-key {_DEPLOYER_KEY} {_GAS} --rpc-url {_ANVIL_RPC} "
            f"  {token} 'mint(address,uint256)' {_SENDER} {amount} 2>&1\n"
            f"cast send --private-key {_DEPLOYER_KEY} {_GAS} --rpc-url {_ANVIL_RPC} "
            f"  {token} 'approve(address,uint256)' {portal} {amount} 2>&1\n"
            f"cast send --private-key {_DEPLOYER_KEY} {_GAS} --rpc-url {_ANVIL_RPC} "
            f"  {portal} 'depositERC20Tokens(address,address,uint256,bytes)' "
            f"  {token} {app} {amount} 0x 2>&1\n"
        )

    def _build_erc721_deposit_script(self, token: str, portal: str, app: str, token_id: int) -> str:
        """mint → setApprovalForAll → depositERC721Token using an already-deployed token contract."""
        return (
            f"set -e\n"
            f"cast send --private-key {_ERC721_KEY} --rpc-url {_ANVIL_RPC} "
            f"  {token} 'mint(address,uint256)' {_ERC721_SENDER} {token_id} 2>&1\n"
            f"cast send --private-key {_ERC721_KEY} --rpc-url {_ANVIL_RPC} "
            f"  {token} 'setApprovalForAll(address,bool)' {portal} true 2>&1\n"
            f"cast send --private-key {_ERC721_KEY} --rpc-url {_ANVIL_RPC} "
            f"  {portal} 'depositERC721Token(address,address,uint256,bytes,bytes)' "
            f"  {token} {app} {token_id} 0x 0x 2>&1\n"
        )

    # ── Fallback script builders (deploy token + deposit in one container) ─────

    def _build_erc20_script(self, portal: str, app: str, amount: int) -> str:
        sol_b64 = _b64(_ERC20_SOL)
        return (
            f"set -e\n"
            f"PROJ=/tmp/tokens && mkdir -p $PROJ/src && cd $PROJ\n"
            f"printf '[profile.default]\\nsrc = \"src\"\\nout = \"out\"\\nlibs = [\"lib\"]\\n' > foundry.toml\n"
            f"forge install --no-git OpenZeppelin/openzeppelin-contracts@v5.0.0 2>&1\n"
            f"printf '@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/\\n' > remappings.txt\n"
            f"echo '{sol_b64}' | base64 -d > src/TestERC20.sol\n"
            f"forge create src/TestERC20.sol:TestERC20 "
            f"  --rpc-url {_ANVIL_RPC} --private-key {_DEPLOYER_KEY} --broadcast 2>&1 | tee /tmp/forge_out.txt\n"
            f"TOKEN=$(grep 'Deployed to:' /tmp/forge_out.txt | awk '{{print $3}}')\n"
            f"echo \"DEPLOYED_TOKEN=$TOKEN\"\n"
            f"cast send --private-key {_DEPLOYER_KEY} --rpc-url {_ANVIL_RPC} "
            f"  $TOKEN 'mint(address,uint256)' {_SENDER} {amount} 2>&1\n"
            f"cast send --private-key {_DEPLOYER_KEY} --rpc-url {_ANVIL_RPC} "
            f"  $TOKEN 'approve(address,uint256)' {portal} {amount} 2>&1\n"
            f"cast send --private-key {_DEPLOYER_KEY} --rpc-url {_ANVIL_RPC} "
            f"  {portal} 'depositERC20Tokens(address,address,uint256,bytes)' "
            f"  $TOKEN {app} {amount} 0x 2>&1\n"
        )

    def _build_erc721_script(self, portal: str, app: str, token_id: int) -> str:
        sol_b64 = _b64(_ERC721_SOL)
        return (
            f"set -e\n"
            f"PROJ=/tmp/tokens && mkdir -p $PROJ/src && cd $PROJ\n"
            f"printf '[profile.default]\\nsrc = \"src\"\\nout = \"out\"\\nlibs = [\"lib\"]\\n' > foundry.toml\n"
            f"forge install --no-git OpenZeppelin/openzeppelin-contracts@v5.0.0 2>&1\n"
            f"printf '@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/\\n' > remappings.txt\n"
            f"echo '{sol_b64}' | base64 -d > src/TestERC721.sol\n"
            f"forge create src/TestERC721.sol:TestERC721 "
            f"  --rpc-url {_ANVIL_RPC} --private-key {_ERC721_KEY} --broadcast 2>&1 | tee /tmp/forge_out.txt\n"
            f"TOKEN=$(grep 'Deployed to:' /tmp/forge_out.txt | awk '{{print $3}}')\n"
            f"echo \"DEPLOYED_TOKEN=$TOKEN\"\n"
            f"cast send --private-key {_ERC721_KEY} --rpc-url {_ANVIL_RPC} "
            f"  $TOKEN 'mint(address,uint256)' {_ERC721_SENDER} {token_id} 2>&1\n"
            f"cast send --private-key {_ERC721_KEY} --rpc-url {_ANVIL_RPC} "
            f"  $TOKEN 'setApprovalForAll(address,bool)' {portal} true 2>&1\n"
            f"cast send --private-key {_ERC721_KEY} --rpc-url {_ANVIL_RPC} "
            f"  {portal} 'depositERC721Token(address,address,uint256,bytes,bytes)' "
            f"  $TOKEN {app} {token_id} 0x 0x 2>&1\n"
        )

    def _build_erc1155_script(self, portal: str, app: str, token_id: int, amount: int) -> str:
        sol_b64 = _b64(_ERC1155_SOL)
        return (
            f"set -e\n"
            f"PROJ=/tmp/tokens && mkdir -p $PROJ/src && cd $PROJ\n"
            f"printf '[profile.default]\\nsrc = \"src\"\\nout = \"out\"\\nlibs = [\"lib\"]\\n' > foundry.toml\n"
            f"forge install --no-git OpenZeppelin/openzeppelin-contracts@v5.0.0 2>&1\n"
            f"printf '@openzeppelin/contracts/=lib/openzeppelin-contracts/contracts/\\n' > remappings.txt\n"
            f"echo '{sol_b64}' | base64 -d > src/TestERC1155.sol\n"
            f"forge create src/TestERC1155.sol:TestERC1155 "
            f"  --rpc-url {_ANVIL_RPC} --private-key {_ERC1155_KEY} --broadcast 2>&1 | tee /tmp/forge_out.txt\n"
            f"TOKEN=$(grep 'Deployed to:' /tmp/forge_out.txt | awk '{{print $3}}')\n"
            f"echo \"DEPLOYED_TOKEN=$TOKEN\"\n"
            f"cast send --private-key {_ERC1155_KEY} --rpc-url {_ANVIL_RPC} "
            f"  $TOKEN 'mint(address,uint256,uint256)' {_ERC1155_SENDER} {token_id} {amount} 2>&1\n"
            f"cast send --private-key {_ERC1155_KEY} --rpc-url {_ANVIL_RPC} "
            f"  $TOKEN 'setApprovalForAll(address,bool)' {portal} true 2>&1\n"
            f"cast send --private-key {_ERC1155_KEY} --rpc-url {_ANVIL_RPC} "
            f"  {portal} 'depositSingleERC1155Token(address,address,uint256,uint256,bytes,bytes)' "
            f"  $TOKEN {app} {token_id} {amount} 0x 0x 2>&1\n"
        )

    # ── Docker / Foundry helpers ───────────────────────────────────────────────

    def _get_anvil_container_id(self, sandbox_id: str) -> str:
        """Look up the Anvil container ID using Docker labels."""
        import docker
        client = docker.from_env(timeout=30)
        containers = client.containers.list(
            filters={"label": [
                f"rvp.sandbox_id={sandbox_id}",
                "rvp.component=anvil",
            ]}
        )
        if not containers:
            raise RuntimeError(
                f"No running Anvil container found for sandbox {sandbox_id[:8]} "
                "— is the Docker socket mounted in the test-runner?"
            )
        return containers[0].id

    def _run_foundry_script_sync(self, script: str, sandbox_id: str) -> str:
        """
        Run a multi-step shell script inside a Foundry container that shares
        Anvil's network namespace (so localhost:8545 reaches the sandbox Anvil).

        Returns the combined stdout+stderr output.
        Raises RuntimeError on non-zero exit.
        """
        import docker
        client   = docker.from_env(timeout=300)
        anvil_id = self._get_anvil_container_id(sandbox_id)
        cname    = f"rvp-portal-{uuid.uuid4().hex[:8]}"

        try:
            client.containers.get(cname).remove(force=True)
        except Exception:
            pass

        log.info("Running portal deposit script for sandbox %s (anvil=%s)",
                 sandbox_id[:8], anvil_id[:12])

        c = client.containers.run(
            _FOUNDRY_IMG,
            # Single-element list: ENTRYPOINT=['/bin/sh', '-c'] + CMD=['script']
            # → runs the whole script as a shell program.
            command=[script],
            name=cname,
            network_mode=f"container:{anvil_id}",
            detach=True,
            remove=False,
        )
        try:
            # OZ compilation (fallback path) takes ~60-90s; allow up to 5 min
            result = c.wait(timeout=300)
            output = c.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            log.debug("Portal script output:\n%s", output[-2000:])
            if result["StatusCode"] != 0:
                raise RuntimeError(
                    f"Foundry portal script exited {result['StatusCode']}. "
                    f"Output: {output[-1200:]}"
                )
            return output
        finally:
            try:
                c.remove(force=True)
            except Exception:
                pass

    def _parse_deployed(self, output: str) -> str | None:
        """Extract the deployed token address from forge create output."""
        for line in output.splitlines():
            if "Deployed to:" in line:
                parts = line.split()
                if len(parts) >= 3:
                    return parts[-1].strip()
        return None

    # ── Anvil JSON-RPC helpers ─────────────────────────────────────────────────

    async def _get_code(self, rpc_url: str, address: str) -> str:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.post(rpc_url, json={
                    "jsonrpc": "2.0",
                    "method":  "eth_getCode",
                    "params":  [address, "latest"],
                    "id":      1,
                })
                return resp.json().get("result", "0x")
        except Exception:
            return "0x"

    async def _wait_receipt(self, rpc_url: str, tx_hash: str, timeout: float = 20.0) -> dict:
        deadline = time.monotonic() + timeout
        async with httpx.AsyncClient(timeout=10.0) as client:
            while time.monotonic() < deadline:
                resp = await client.post(rpc_url, json={
                    "jsonrpc": "2.0",
                    "method":  "eth_getTransactionReceipt",
                    "params":  [tx_hash],
                    "id":      1,
                })
                receipt = resp.json().get("result")
                if receipt:
                    return receipt
                await asyncio.sleep(1)
        raise RuntimeError(f"Timeout waiting for receipt of {tx_hash}")
