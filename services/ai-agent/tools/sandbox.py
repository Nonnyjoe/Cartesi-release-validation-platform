"""Provision/teardown sandbox tools.

Both delegate to the orchestrator HTTP API, which already implements the proper run-creation
+ sandbox-request flow.
"""
from __future__ import annotations

import logging
import os

import httpx

log = logging.getLogger("ai-agent.sandbox_tool")

ORCH_URL = os.environ.get("ORCHESTRATOR_URL", "http://orchestrator:8000")


DEFAULT_RELEASE_TAG = "v2.0.0-alpha.11"
DEFAULT_IMAGE_TAG   = "cartesi/rollups-runtime:0.12.0-alpha.39"


async def provision_sandbox(
    release_tag: str | None = None,
    image_tag: str | None = None,
    triggered_by: str | None = "user",
    app_id: str | None = None,
) -> dict:
    """Trigger a new run + sandbox via the orchestrator's POST /runs endpoint.

    Returns the run_id; sandbox_id appears in the run details once provisioned.
    """
    payload = {
        "release_tag":   release_tag or DEFAULT_RELEASE_TAG,
        "image_tag":     image_tag or DEFAULT_IMAGE_TAG,
        "priority":      5,
        "triggered_by":  triggered_by,
        "requested_by":  "ai-agent",
    }
    if app_id:
        payload["app_id"] = app_id

    try:
        # Generous timeout: right after a Docker daemon restart the orchestrator
        # can be slow to accept run requests (see integration log §6, item 14).
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(f"{ORCH_URL}/runs", json=payload)
        if r.status_code >= 400:
            return {"success": False, "error": f"orchestrator {r.status_code}: {r.text[:300]}"}
        data = r.json()
    except Exception as exc:
        log.exception("provision_sandbox failed")
        return {"success": False, "error": str(exc)}

    return {
        "success": True,
        "run_id": data.get("id"),
        "status": data.get("status"),
        "hint": "Poll get_node_state or query_db to wait for sandbox ready.",
    }


async def teardown_sandbox(run_id: str) -> dict:
    """Cancel a run, which causes the sandbox-manager to teardown its containers."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{ORCH_URL}/runs/{run_id}/cancel")
        if r.status_code >= 400:
            return {"success": False, "error": f"orchestrator {r.status_code}: {r.text[:300]}"}
    except Exception as exc:
        return {"success": False, "error": str(exc)}
    return {"success": True, "run_id": run_id, "cancelled": True}
