"""
tools/graphql.py
query_graphql, call_inspect
"""
import logging
import re
from typing import Any

import httpx

log = logging.getLogger("ai-agent.tools.graphql")


async def query_graphql(
    query: str,
    graphql_url: str,
    variables: dict | None = None,
) -> dict[str, Any]:
    """
    Execute any GraphQL query against the node API.
    Returns the full response including data and errors.
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                graphql_url,
                json={"query": query, "variables": variables or {}},
                headers={"Content-Type": "application/json"},
            )
        body = resp.json()
        return {
            "success": "errors" not in body,
            "data": body.get("data"),
            "errors": body.get("errors"),
            "status_code": resp.status_code,
        }
    except Exception as exc:
        log.warning("query_graphql error: %s", exc)
        return {"success": False, "error": str(exc)}


async def call_inspect(
    payload: str,
    node_http_url: str,
) -> dict[str, Any]:
    """
    Send a synchronous inspect-state call. Does not produce L1 transactions.
    payload: hex-encoded string, e.g. '0x' for empty.
    """
    try:
        # Normalise payload — ensure hex prefix
        if not payload.startswith("0x"):
            payload = "0x" + payload

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(f"{node_http_url}/inspect/{payload}")
        body = resp.json()
        return {
            "success": resp.status_code == 200,
            "status": body.get("status"),
            "reports": body.get("reports", []),
            "processed_input_count": body.get("processed_input_count"),
            "exception_payload": body.get("exception_payload"),
            "status_code": resp.status_code,
        }
    except Exception as exc:
        log.warning("call_inspect error: %s", exc)
        return {"success": False, "error": str(exc)}
