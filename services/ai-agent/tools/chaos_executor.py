"""
services/ai-agent/tools/chaos_executor.py

Executors for chaos-mode-only tools:
  - restart_component: stop + start named container via Docker SDK
  - pause_network: disconnect/reconnect Anvil from sandbox network
"""
import asyncio
import logging
import time

import docker
from docker.errors import APIError

log = logging.getLogger("ai-agent.chaos")


def _get_client() -> docker.DockerClient:
    return docker.from_env()


async def execute_restart_component(inputs: dict, ctx: dict) -> dict:
    """Stop and restart a sandbox container, return health status after restart."""
    component = inputs.get("component", "node")
    wait = min(int(inputs.get("wait_seconds", 5)), 30)

    container_ids: dict = ctx.get("container_ids", {})
    container_id = container_ids.get(component)

    if not container_id:
        return {"error": f"No container ID found for component '{component}' in sandbox context"}

    client = _get_client()
    try:
        container = client.containers.get(container_id)
        log.info("[chaos] Restarting %s container %s", component, container_id[:12])
        t0 = time.monotonic()

        await asyncio.to_thread(container.restart, timeout=10)
        await asyncio.sleep(wait)

        container.reload()
        status = container.status
        elapsed = round(time.monotonic() - t0, 2)

        return {
            "component": component,
            "container_id": container_id[:12],
            "status_after_restart": status,
            "elapsed_seconds": elapsed,
            "healthy": status == "running",
        }
    except APIError as e:
        return {"error": f"Docker API error: {e}"}


async def execute_pause_network(inputs: dict, ctx: dict) -> dict:
    """Disconnect Anvil from sandbox network, sleep, reconnect, report outcome."""
    duration = min(int(inputs.get("duration_seconds", 10)), 60)
    network_name: str = ctx.get("docker_network", "")
    container_ids: dict = ctx.get("container_ids", {})
    anvil_id = container_ids.get("anvil")

    if not network_name or not anvil_id:
        return {"error": "Missing docker_network or anvil container_id in sandbox context"}

    client = _get_client()
    try:
        network = client.networks.get(network_name)
        container = client.containers.get(anvil_id)

        log.info("[chaos] Disconnecting Anvil (%s) from network %s for %ds", anvil_id[:12], network_name, duration)
        await asyncio.to_thread(network.disconnect, container)
        await asyncio.sleep(duration)
        await asyncio.to_thread(network.connect, container)

        container.reload()
        return {
            "partition_duration_seconds": duration,
            "anvil_status_after_reconnect": container.status,
            "network": network_name,
            "recovered": container.status == "running",
        }
    except APIError as e:
        # Try to reconnect even on error
        try:
            await asyncio.to_thread(network.connect, container)
        except Exception:
            pass
        return {"error": f"Docker API error: {e}"}
