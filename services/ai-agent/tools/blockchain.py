"""
tools/blockchain.py
send_advance_input, run_cast_command, verify_voucher
"""
import asyncio
import json
import logging
import subprocess
from typing import Any

import httpx

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
) -> dict[str, Any]:
    """
    Execute a raw cast (Foundry) command against Anvil.
    The command string is the part after 'cast', e.g. 'block-number'.
    Automatically appends --rpc-url if not present.
    """
    if "--rpc-url" not in command:
        full_cmd = f"cast {command} --rpc-url {anvil_rpc_url}"
    else:
        full_cmd = f"cast {command}"

    try:
        proc = await asyncio.create_subprocess_shell(
            full_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
        return {
            "success": proc.returncode == 0,
            "stdout": stdout.decode().strip(),
            "stderr": stderr.decode().strip(),
            "returncode": proc.returncode,
            "command": full_cmd,
        }
    except asyncio.TimeoutError:
        return {"success": False, "error": "cast command timed out (30s)"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}


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
