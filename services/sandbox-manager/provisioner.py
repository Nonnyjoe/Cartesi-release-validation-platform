"""
services/sandbox-manager/provisioner.py
Uses the Docker SDK to spin up and tear down sandbox environments.

Each sandbox = one Docker network + containers:
  - anvil          (Foundry local chain)
  - cartesi-node   (the rollups node image under test)
"""
import asyncio
import logging
import os
import uuid
from typing import Optional

import docker
from docker.models.containers import Container
from docker.models.networks import Network

log = logging.getLogger("sandbox-manager.provisioner")

SANDBOX_CPU_LIMIT    = float(os.environ.get("SANDBOX_CPU_LIMIT", 2))
SANDBOX_MEMORY_LIMIT = os.environ.get("SANDBOX_MEMORY_LIMIT", "4g")
ANVIL_IMAGE          = "ghcr.io/foundry-rs/foundry:latest"
SANDBOX_BASE_IMAGE   = "cartesi-rvp-sandbox:base"

# Ports are allocated dynamically starting from these bases
ANVIL_PORT_BASE   = 8545
NODE_PORT_BASE    = 5000
GRAPHQL_PORT_BASE = 4000


class SandboxProvisioner:

    def __init__(self):
        self._client = docker.from_env()

    def _allocate_ports(self, offset: int) -> tuple[int, int, int]:
        """Return (anvil_port, node_port, graphql_port) offset from bases."""
        return (
            ANVIL_PORT_BASE   + offset * 10,
            NODE_PORT_BASE    + offset * 10,
            GRAPHQL_PORT_BASE + offset * 10,
        )

    async def provision(
        self,
        sandbox_id: str,
        run_id: str,
        image_tag: str,
        port_offset: int = 0,
    ) -> dict:
        """
        Spin up a sandbox.  Returns a dict with connection info.
        Runs blocking Docker calls in a thread executor.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._provision_sync,
            sandbox_id, run_id, image_tag, port_offset,
        )

    def _provision_sync(self, sandbox_id: str, run_id: str, image_tag: str, port_offset: int) -> dict:
        anvil_port, node_port, graphql_port = self._allocate_ports(port_offset)
        network_name = f"rvp-sbx-{sandbox_id[:8]}"

        log.info("Provisioning sandbox %s (run=%s) ports=%d/%d/%d",
                 sandbox_id, run_id, anvil_port, node_port, graphql_port)

        # 1. Create isolated Docker network
        network: Network = self._client.networks.create(
            name=network_name,
            driver="bridge",
            labels={"rvp.sandbox_id": sandbox_id, "rvp.run_id": run_id},
        )

        container_ids = []

        # 2. Start Anvil (local Ethereum node)
        anvil: Container = self._client.containers.run(
            ANVIL_IMAGE,
            command=f"anvil --host 0.0.0.0 --port 8545 --block-time 1",
            name=f"rvp-anvil-{sandbox_id[:8]}",
            network=network_name,
            ports={"8545/tcp": anvil_port},
            cpu_period=100000,
            cpu_quota=int(SANDBOX_CPU_LIMIT * 100000),
            mem_limit=SANDBOX_MEMORY_LIMIT,
            detach=True,
            remove=False,
            labels={"rvp.sandbox_id": sandbox_id, "rvp.component": "anvil"},
        )
        container_ids.append(anvil.id)

        # 3. Start Cartesi rollups node
        node: Container = self._client.containers.run(
            image_tag,
            name=f"rvp-node-{sandbox_id[:8]}",
            network=network_name,
            ports={
                "5004/tcp": node_port,
                "4000/tcp": graphql_port,
            },
            environment={
                "CARTESI_BLOCKCHAIN_HTTP_ENDPOINT": f"http://rvp-anvil-{sandbox_id[:8]}:8545",
                "CARTESI_BLOCKCHAIN_WS_ENDPOINT":   f"ws://rvp-anvil-{sandbox_id[:8]}:8545",
                "CARTESI_CONTRACTS_INPUT_BOX_ADDRESS": "0x59b22D57D4f067708AB0c00552767405926dc768",
                "CARTESI_LOG_LEVEL": "info",
            },
            cpu_period=100000,
            cpu_quota=int(SANDBOX_CPU_LIMIT * 100000),
            mem_limit=SANDBOX_MEMORY_LIMIT,
            detach=True,
            remove=False,
            labels={"rvp.sandbox_id": sandbox_id, "rvp.component": "node"},
        )
        container_ids.append(node.id)

        log.info("Sandbox %s provisioned: anvil=%s node=%s", sandbox_id, anvil.id[:12], node.id[:12])

        return {
            "sandbox_id":    sandbox_id,
            "run_id":        run_id,
            "docker_network": network_name,
            "container_ids": container_ids,
            "anvil_port":    anvil_port,
            "node_port":     node_port,
            "graphql_port":  graphql_port,
        }

    async def teardown(self, sandbox_id: str, container_ids: list[str], network_name: str):
        """Stop and remove all containers + the network for a sandbox."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, self._teardown_sync, sandbox_id, container_ids, network_name
        )

    def _teardown_sync(self, sandbox_id: str, container_ids: list[str], network_name: str):
        log.info("Tearing down sandbox %s", sandbox_id)
        for cid in container_ids:
            try:
                c = self._client.containers.get(cid)
                c.stop(timeout=10)
                c.remove(force=True)
                log.info("Removed container %s", cid[:12])
            except Exception as exc:
                log.warning("Could not remove container %s: %s", cid[:12], exc)

        try:
            net = self._client.networks.get(network_name)
            net.remove()
            log.info("Removed network %s", network_name)
        except Exception as exc:
            log.warning("Could not remove network %s: %s", network_name, exc)
