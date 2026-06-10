"""
tools/node.py
read_logs, get_node_state
"""
import logging
from typing import Any

import docker
import httpx

log = logging.getLogger("ai-agent.tools.node")


async def read_logs(
    sandbox_id: str,
    component: str = "advancer",
    tail: int = 100,
) -> dict[str, Any]:
    """
    Read stdout/stderr logs from a sandbox container.
    component: advancer | claimer | validator | jsonrpc | evm-reader | anvil | cli | db | node
    'node' falls back to 'advancer' for v2.x sandboxes (no monolithic node container).
    """
    short = sandbox_id[:8] if sandbox_id else ""
    if component == "node":
        candidates = [f"rvp-node-{short}", f"rvp-advancer-{short}", f"rvp-jsonrpc-{short}"]
    elif component == "jsonrpc":
        candidates = [f"rvp-jsonrpc-{short}", f"rvp-jsonrpc-api-{short}"]
    else:
        candidates = [f"rvp-{component}-{short}"]

    client = docker.from_env()
    for name in candidates:
        try:
            container = client.containers.get(name)
            raw = container.logs(stdout=True, stderr=True, tail=tail)
            lines = raw.decode("utf-8", errors="replace").splitlines()
            return {
                "success":    True,
                "container":  name,
                "component":  component,
                "lines":      lines,
                "line_count": len(lines),
            }
        except docker.errors.NotFound:
            continue
        except Exception as exc:
            log.warning("read_logs error on %s: %s", name, exc)
            return {"success": False, "error": str(exc), "container": name}

    return {"success": False, "error": f"No matching container. Tried: {candidates}"}


async def get_node_state(
    graphql_url: str,
    node_http_url: str,
) -> dict[str, Any]:
    """
    Full snapshot of the node: input count, current epoch, open vouchers, health.
    """
    query = """
    {
      inputs { totalCount }
      epochs { edges { node { index status } } }
      vouchers { totalCount }
      notices { totalCount }
    }
    """
    state: dict[str, Any] = {}

    # GraphQL state
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(graphql_url, json={"query": query})
            data = resp.json().get("data", {})
        state["input_count"]   = data.get("inputs", {}).get("totalCount", 0)
        state["voucher_count"] = data.get("vouchers", {}).get("totalCount", 0)
        state["notice_count"]  = data.get("notices", {}).get("totalCount", 0)
        epochs = data.get("epochs", {}).get("edges", [])
        state["epochs"] = [e["node"] for e in epochs]
        state["current_epoch"] = epochs[-1]["node"] if epochs else None
    except Exception as exc:
        state["graphql_error"] = str(exc)

    # Health check
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            health = await client.get(f"{node_http_url}/healthz")
        state["health_status"] = health.status_code
        state["healthy"] = health.status_code == 200
    except Exception as exc:
        state["health_status"] = None
        state["healthy"] = False
        state["health_error"] = str(exc)

    return {"success": True, "state": state}
