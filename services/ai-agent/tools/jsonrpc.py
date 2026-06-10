"""Direct Cartesi JSON-RPC tool.

POSTs to the sandbox's rvp-jsonrpc-{short_id}:10011 endpoint with cartesi_* methods.
Validates the method prefix to keep the tool scoped.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

log = logging.getLogger("ai-agent.jsonrpc_tool")

ALLOWED_PREFIXES = ("cartesi_",)
TIMEOUT_S = 15.0


async def call_jsonrpc(
    sandbox_id: str,
    method: str,
    params: list | dict | None = None,
    rpc_url: str | None = None,
) -> dict[str, Any]:
    if not method.startswith(ALLOWED_PREFIXES):
        return {
            "success": False,
            "error": f"Method must start with one of {ALLOWED_PREFIXES}; got {method!r}",
        }

    short = sandbox_id[:8] if sandbox_id else ""
    url = rpc_url or f"http://rvp-jsonrpc-{short}:10011"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params if params is not None else [],
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.post(url, json=payload, headers={"Content-Type": "application/json"})
        body = r.json()
    except Exception as exc:
        log.exception("call_jsonrpc transport error")
        return {"success": False, "error": f"transport: {exc}", "url": url}

    if "error" in body:
        return {"success": False, "url": url, "error": body["error"]}

    return {
        "success": True,
        "url": url,
        "result": body.get("result"),
    }
