"""
tools/blockchain.py
send_advance_input, run_cast_command, verify_voucher

run_cast_command executes `cast` via docker exec inside the sandbox's Anvil
container (ghcr.io/foundry-rs/foundry — the only sandbox container that ships
Foundry). The ai-agent image itself does NOT have cast installed.
"""
import asyncio
import json
import logging
import shlex
from typing import Any

import httpx

from tools.cli import _run_exec

log = logging.getLogger("ai-agent.tools.blockchain")

INPUTBOX_ADDRESS = "0x59b22D57D4f067708AB0c00552767405926dc768"
DEFAULT_PRIVATE_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"


async def send_advance_input(
    payload: str,
    anvil_rpc_url: str,
    node_http_url: str,
    app_address: str = "0x0000000000000000000000000000000000000001",
) -> dict[str, Any]:
    """
    Send an advance-state input to the Cartesi node via the HTTP bridge.
    Returns the response body.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{node_http_url}/box",
                json={"payload": payload},
                headers={"Content-Type": "application/json"},
            )
        return {
            "status_code": resp.status_code,
            "body": resp.text,
            "success": resp.status_code in (200, 201, 202),
        }
    except Exception as exc:
        log.warning("send_advance_input error: %s", exc)
        return {"success": False, "error": str(exc)}


async def run_cast_command(
    command: str,
    anvil_rpc_url: str,
    sandbox_id: str = "",
) -> dict[str, Any]:
    """
    Execute a raw cast (Foundry) command via docker exec inside the sandbox's
    Anvil container. The command string is the part after 'cast',
    e.g. 'block-number'. Automatically appends --rpc-url if not present.

    Inside the Anvil container the chain listens on localhost:8545, so that is
    the default RPC target (NOT the host-mapped port).
    """
    if not sandbox_id:
        return {"success": False,
                "error": "No sandbox bound to this session — cast runs inside rvp-anvil-<id>."}

    if "--rpc-url" not in command:
        full_cmd = f"cast {command} --rpc-url http://localhost:8545"
    else:
        full_cmd = f"cast {command}"

    try:
        argv = shlex.split(full_cmd)
    except ValueError as exc:
        return {"success": False, "error": f"invalid command: {exc}"}

    container_name = f"rvp-anvil-{sandbox_id[:8]}"
    try:
        result = await asyncio.wait_for(
            asyncio.to_thread(_run_exec, container_name, argv),
            timeout=30,
        )
    except asyncio.TimeoutError:
        return {"success": False, "error": "cast command timed out (30s)",
                "container": container_name}
    out = {
        "success": result.get("success", False),
        "stdout": (result.get("stdout") or "").strip(),
        "stderr": (result.get("stderr") or "").strip(),
        "returncode": result.get("exit_code"),
        "command": full_cmd,
        "container": container_name,
    }
    if result.get("error"):
        out["error"] = result["error"]
    return out


async def verify_voucher(
    input_index: int,
    voucher_index: int,
    graphql_url: str,
) -> dict[str, Any]:
    """
    Fetch a voucher's proof from GraphQL and verify it is valid.
    Returns voucher details and proof validity.
    """
    query = """
    query GetVoucher($inputIndex: Int!, $voucherIndex: Int!) {
      voucher(inputIndex: $inputIndex, voucherIndex: $voucherIndex) {
        index
        destination
        payload
        proof {
          validity {
            inputIndexWithinEpoch
            outputIndexWithinInput
            outputHashesRootHash
            vouchersEpochRootHash
          }
          context
        }
      }
    }
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                graphql_url,
                json={"query": query, "variables": {
                    "inputIndex": input_index,
                    "voucherIndex": voucher_index,
                }},
            )
            data = resp.json()
        voucher = data.get("data", {}).get("voucher")
        if not voucher:
            return {"success": False, "error": "Voucher not found", "data": data}
        has_proof = voucher.get("proof") is not None
        return {
            "success": True,
            "voucher": voucher,
            "has_proof": has_proof,
            "is_executable": has_proof,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}
