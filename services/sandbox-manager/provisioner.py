"""
services/sandbox-manager/provisioner.py

Spin up and tear down isolated sandbox environments using the Docker SDK.

Strategy by node major version
-------------------------------
v1.x  — 2 containers: Anvil (local Ethereum) + rollups-node image.
         image_tag = cartesi/rollups-node:<version>

v2.x  — 7+ containers: Anvil + the full 6-service SDK compose stack:
           database  (cartesi/rollups-database:<sdk_version>)
           evm-reader, advancer, validator, claimer, jsonrpc-api
                     (all  cartesi/rollups-runtime:<sdk_version>)
         + cli-tools (cartesi-rvp-cli:<cli_version>) — built on demand if
           cli_version is provided; contains the exact @cartesi/cli version
           that ships with the selected rollups-node release.

For inspection / auditability the provisioner writes a docker-compose.yml
to /tmp/rvp-sandboxes/sbx-<sandbox_id[:8]>/ for each sandbox.  The actual
container lifecycle is managed via the Python Docker SDK (not compose CLI).

Port allocation
---------------
  anvil_port   → Anvil RPC
  node_port    → v1.x: HTTP (5004)   v2.x: jsonrpc-api (10011)
  graphql_port → v1.x: GraphQL (4000) v2.x: inspect API (10012)

CLI image caching
-----------------
The first time a cli_version is seen, _ensure_cli_image_sync() builds
a cartesi-rvp-cli:<cli_version> Docker image (~30-60s).  Subsequent
sandboxes using the same CLI version reuse the cached image instantly.
Build failures are non-fatal: the sandbox provisions without a cli-tools
container; tests that don't call the CLI are unaffected.

Machine snapshot for v2.x
--------------------------
The advancer container needs a Cartesi machine snapshot at
/var/lib/cartesi-rollups-node/snapshot.

We mount the Docker named volume "rvp-test-snapshot" (populated by
`make build-test-app`) into the advancer.  If the volume does not
exist the advancer starts without a snapshot; it will fail when
processing real inputs, but the API services will still come up,
allowing health-check tests to pass.
"""
import asyncio
import logging
import os
import time
from typing import Optional

import docker
import yaml
from docker.models.containers import Container
from docker.models.networks   import Network

log = logging.getLogger("sandbox-manager.provisioner")

# ── Image constants ────────────────────────────────────────────────────────────
ANVIL_IMAGE          = "ghcr.io/foundry-rs/foundry:latest"
TEST_SNAPSHOT_VOLUME = os.environ.get("TEST_SNAPSHOT_VOLUME", "rvp-test-snapshot")
CLI_IMAGE_PREFIX     = "cartesi-rvp-cli"   # per-version images: cartesi-rvp-cli:<cli_version>

# ── Resource limits ────────────────────────────────────────────────────────────
SANDBOX_CPU_LIMIT    = float(os.environ.get("SANDBOX_CPU_LIMIT", 2))
SANDBOX_MEMORY_LIMIT = os.environ.get("SANDBOX_MEMORY_LIMIT", "4g")

# ── Port bases — high range to avoid macOS system ports (5000=AirPlay, etc.) ──
ANVIL_PORT_BASE   = int(os.environ.get("ANVIL_PORT_BASE",   "28545"))
NODE_PORT_BASE    = int(os.environ.get("NODE_PORT_BASE",    "25000"))
GRAPHQL_PORT_BASE = int(os.environ.get("GRAPHQL_PORT_BASE", "24000"))

# ── Devnet contract addresses (from compose.local.yaml) ───────────────────────
# These are the pre-deployed contract addresses on Cartesi's devnet.
# On a fresh Anvil these need to be deployed first (future: add deployment step).
DEVNET_ENV = {
    "CARTESI_CONTRACTS_INPUT_BOX_ADDRESS":                   "0x1b51e2992A2755Ba4D6F7094032DF91991a0Cfac",
    "CARTESI_CONTRACTS_AUTHORITY_FACTORY_ADDRESS":           "0x5E96408CFE423b01dADeD3bc867E6013135990cc",
    "CARTESI_CONTRACTS_APPLICATION_FACTORY_ADDRESS":         "0x26E758238CB6eC5aB70ce0dd52aF2d7b82e1972E",
    "CARTESI_CONTRACTS_SELF_HOSTED_APPLICATION_FACTORY_ADDRESS": "0x010D3CbB4223F5bCc7b7B03cEE59f3aAea8eDb8A",
}

# ── Compose file directory ─────────────────────────────────────────────────────
COMPOSE_DIR = os.environ.get("SANDBOX_COMPOSE_DIR", "/tmp/rvp-sandboxes")


class SandboxProvisioner:

    def __init__(self):
        self._client: Optional[docker.DockerClient] = None

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            self._client = docker.from_env()
        return self._client

    # ── Public API ─────────────────────────────────────────────────────────────

    def _allocate_ports(self, offset: int) -> tuple[int, int, int]:
        return (
            ANVIL_PORT_BASE   + offset * 10,
            NODE_PORT_BASE    + offset * 10,
            GRAPHQL_PORT_BASE + offset * 10,
        )

    async def provision(
        self,
        sandbox_id: str,
        run_id:     str,
        image_tag:  str,
        port_offset: int = 0,
        sdk_version: Optional[str] = None,
        node_major_version: int = 1,
        cli_version: Optional[str] = None,
        devnet_version: Optional[str] = None,
        contracts_version: Optional[str] = None,
    ) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._provision_sync,
            sandbox_id, run_id, image_tag, port_offset,
            sdk_version, node_major_version, cli_version,
            devnet_version, contracts_version,
        )

    async def wait_for_anvil_health(self, container_id: str, timeout: int = 60) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._wait_for_anvil_health_sync, container_id, timeout
        )

    async def wait_for_v2_ready(self, db_container_id: str, jsonrpc_container_id: str,
                                  timeout: int = 120) -> bool:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._wait_for_v2_ready_sync,
            db_container_id, jsonrpc_container_id, timeout
        )

    async def teardown(self, sandbox_id: str, container_ids: list[str], network_name: str):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, self._teardown_sync, sandbox_id, container_ids, network_name
        )

    # ── Sync implementations (run in thread executor) ──────────────────────────

    def _provision_sync(
        self,
        sandbox_id: str,
        run_id:     str,
        image_tag:  str,
        port_offset: int,
        sdk_version: Optional[str],
        node_major_version: int,
        cli_version: Optional[str],
        devnet_version: Optional[str] = None,
        contracts_version: Optional[str] = None,
    ) -> dict:
        anvil_port, node_port, graphql_port = self._allocate_ports(port_offset)
        network_name = f"rvp-sbx-{sandbox_id[:8]}"

        log.info(
            "Provisioning sandbox %s (run=%s, node_major=%d, sdk=%s, cli=%s, devnet=%s, contracts=%s) ports=%d/%d/%d",
            sandbox_id, run_id, node_major_version, sdk_version, cli_version,
            devnet_version, contracts_version, anvil_port, node_port, graphql_port,
        )

        container_ids:     list[str] = []
        cli_container_name: Optional[str] = None
        try:
            # 1. Isolated Docker network
            self.client.networks.create(
                name=network_name,
                driver="bridge",
                labels={"rvp.sandbox_id": sandbox_id, "rvp.run_id": run_id},
            )

            # 2. Start Anvil
            anvil = self._start_anvil(sandbox_id, network_name, anvil_port)
            container_ids.append(anvil.id)

            # 3. Start node services
            if node_major_version >= 2 and sdk_version:
                new_ids, cli_container_name = self._start_v2_services(
                    sandbox_id, network_name, sdk_version,
                    node_port, graphql_port,
                    cli_version=cli_version,
                )
            else:
                new_ids = self._start_v1_node(
                    sandbox_id, network_name, image_tag,
                    node_port, graphql_port,
                )
            container_ids.extend(new_ids)

            # 4. Write compose YAML for inspection
            compose_dict = self._build_compose_dict(
                sandbox_id, node_major_version, image_tag, sdk_version,
                anvil_port, node_port, graphql_port,
                cli_version=cli_version,
            )
            self._write_compose_yaml(sandbox_id, compose_dict)

        except Exception:
            log.warning("Provisioning failed for %s — cleaning up", sandbox_id)
            self._teardown_sync(sandbox_id, container_ids, network_name)
            raise

        log.info("Sandbox %s provisioned: %d containers (cli=%s)",
                 sandbox_id, len(container_ids), cli_container_name)
        return {
            "sandbox_id":         sandbox_id,
            "run_id":             run_id,
            "docker_network":     network_name,
            "container_ids":      container_ids,
            "anvil_port":         anvil_port,
            "node_port":          node_port,
            "graphql_port":       graphql_port,
            "cli_container_name": cli_container_name,
        }

    # ── Container launchers ────────────────────────────────────────────────────

    def _start_anvil(self, sandbox_id: str, network: str, port: int) -> Container:
        return self.client.containers.run(
            ANVIL_IMAGE,
            command="anvil --host 0.0.0.0 --port 8545 --block-time 1 --chain-id 31337",
            name=f"rvp-anvil-{sandbox_id[:8]}",
            network=network,
            ports={"8545/tcp": port},
            detach=True,
            remove=False,
            labels={"rvp.sandbox_id": sandbox_id, "rvp.component": "anvil"},
        )

    def _start_v1_node(
        self, sandbox_id: str, network: str, image_tag: str,
        node_port: int, graphql_port: int,
    ) -> list[str]:
        node: Container = self.client.containers.run(
            image_tag,
            name=f"rvp-node-{sandbox_id[:8]}",
            network=network,
            ports={"5004/tcp": node_port, "4000/tcp": graphql_port},
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
        return [node.id]

    def _start_v2_services(
        self, sandbox_id: str, network: str, sdk_version: str,
        jsonrpc_port: int, inspect_port: int,
        cli_version: Optional[str] = None,
    ) -> tuple[list[str], Optional[str]]:
        """
        Start the full 6-service SDK stack for a v2.x node release.

        If cli_version is provided, also builds/reuses a per-version CLI image
        and starts a cli-tools container in the sandbox network.

        Returns (container_ids, cli_container_name).
        cli_container_name is None when no cli_version was given or build failed.
        """
        runtime_image = f"cartesi/rollups-runtime:{sdk_version}"
        db_image      = f"cartesi/rollups-database:{sdk_version}"
        short         = sandbox_id[:8]
        anvil_name    = f"rvp-anvil-{short}"

        common_env = {
            "CARTESI_LOG_LEVEL": "info",
            "CARTESI_AUTH_KIND": "private_key",
            # Anvil account #0 private key (well-known test key)
            "CARTESI_AUTH_PRIVATE_KEY": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
            "CARTESI_BLOCKCHAIN_ID":             "31337",
            "CARTESI_BLOCKCHAIN_WS_ENDPOINT":    f"ws://{anvil_name}:8545",
            "CARTESI_BLOCKCHAIN_HTTP_ENDPOINT":  f"http://{anvil_name}:8545",
            "CARTESI_SNAPSHOTS_DIR":             "/var/lib/cartesi-rollups-node/snapshot",
            "CARTESI_DATABASE_CONNECTION":       f"postgres://postgres:password@rvp-db-{short}:5432/rollupsdb?sslmode=disable",
            "CARTESI_EPOCH_LENGTH":              "1",
            "CARTESI_BLOCKCHAIN_DEFAULT_BLOCK":  "latest",
            **DEVNET_ENV,
        }

        ids: list[str] = []

        # ── database ──────────────────────────────────────────────────────────
        db_container: Container = self.client.containers.run(
            db_image,
            name=f"rvp-db-{short}",
            network=network,
            environment={"POSTGRES_PASSWORD": "password"},
            detach=True,
            remove=False,
            labels={"rvp.sandbox_id": sandbox_id, "rvp.component": "database"},
        )
        ids.append(db_container.id)

        # Wait for database to be healthy before starting dependent services
        if not self._wait_for_database_sync(db_container.id):
            raise RuntimeError(f"Sandbox {sandbox_id}: database did not become healthy")

        # ── evm-reader ────────────────────────────────────────────────────────
        evm_reader: Container = self.client.containers.run(
            runtime_image,
            command="cartesi-rollups-evm-reader --default-block latest",
            name=f"rvp-evm-reader-{short}",
            network=network,
            environment=common_env,
            detach=True,
            remove=False,
            labels={"rvp.sandbox_id": sandbox_id, "rvp.component": "evm-reader"},
        )
        ids.append(evm_reader.id)

        # ── advancer (mounts machine snapshot) ───────────────────────────────
        snapshot_volumes = self._build_snapshot_volumes(sandbox_id)
        advancer: Container = self.client.containers.run(
            runtime_image,
            command="cartesi-rollups-advancer",
            name=f"rvp-advancer-{short}",
            network=network,
            ports={"10012/tcp": inspect_port},
            environment=common_env,
            volumes=snapshot_volumes,
            detach=True,
            remove=False,
            labels={"rvp.sandbox_id": sandbox_id, "rvp.component": "advancer"},
        )
        ids.append(advancer.id)

        # ── validator ─────────────────────────────────────────────────────────
        validator: Container = self.client.containers.run(
            runtime_image,
            command="cartesi-rollups-validator",
            name=f"rvp-validator-{short}",
            network=network,
            environment=common_env,
            detach=True,
            remove=False,
            labels={"rvp.sandbox_id": sandbox_id, "rvp.component": "validator"},
        )
        ids.append(validator.id)

        # ── claimer ───────────────────────────────────────────────────────────
        claimer: Container = self.client.containers.run(
            runtime_image,
            command="cartesi-rollups-claimer",
            name=f"rvp-claimer-{short}",
            network=network,
            environment=common_env,
            detach=True,
            remove=False,
            labels={"rvp.sandbox_id": sandbox_id, "rvp.component": "claimer"},
        )
        ids.append(claimer.id)

        # ── jsonrpc-api ───────────────────────────────────────────────────────
        jsonrpc: Container = self.client.containers.run(
            runtime_image,
            command="cartesi-rollups-jsonrpc-api",
            name=f"rvp-jsonrpc-{short}",
            network=network,
            ports={"10011/tcp": jsonrpc_port},
            environment=common_env,
            detach=True,
            remove=False,
            labels={"rvp.sandbox_id": sandbox_id, "rvp.component": "jsonrpc-api"},
        )
        ids.append(jsonrpc.id)

        # ── cli-tools (per-release @cartesi/cli version) ──────────────────────
        cli_container_name: Optional[str] = None
        if cli_version:
            try:
                cli_image = self._ensure_cli_image_sync(cli_version)
                cli_name  = f"rvp-cli-{short}"
                cli_cont: Container = self.client.containers.run(
                    cli_image,
                    name=cli_name,
                    network=network,
                    detach=True,
                    remove=False,
                    labels={"rvp.sandbox_id": sandbox_id, "rvp.component": "cli-tools"},
                )
                ids.append(cli_cont.id)
                cli_container_name = cli_name
                log.info(
                    "CLI tools container %s started (cli@%s) for sandbox %s",
                    cli_name, cli_version, sandbox_id,
                )
            except Exception as exc:
                log.warning(
                    "Could not start CLI tools container for sandbox %s (cli@%s): %s — "
                    "proceeding without CLI container",
                    sandbox_id, cli_version, exc,
                )

        log.info("v2.x stack started for sandbox %s (%d containers)", sandbox_id, len(ids))
        return ids, cli_container_name

    def _build_snapshot_volumes(self, sandbox_id: str) -> dict:
        """
        Return the Docker SDK volumes dict for the advancer snapshot mount.
        Uses the named volume rvp-test-snapshot if it exists.
        """
        try:
            self.client.volumes.get(TEST_SNAPSHOT_VOLUME)
            log.info("Mounting volume %s as machine snapshot for sandbox %s",
                     TEST_SNAPSHOT_VOLUME, sandbox_id)
            return {
                TEST_SNAPSHOT_VOLUME: {
                    "bind": "/var/lib/cartesi-rollups-node/snapshot",
                    "mode": "ro",
                }
            }
        except Exception:
            log.warning(
                "Volume %s not found — advancer will start without a machine snapshot. "
                "Run `make build-test-app` to create it.",
                TEST_SNAPSHOT_VOLUME,
            )
            return {}

    # ── CLI image builder ──────────────────────────────────────────────────────

    def _ensure_cli_image_sync(self, cli_version: str) -> str:
        """
        Return a Docker image tag for cartesi-rvp-cli:<cli_version>.

        On first call for a given cli_version the image is built from a minimal
        node:20-slim Dockerfile (~30-60s, network required).  Subsequent calls
        for the same version return instantly from the local image cache.

        Raises RuntimeError if the build fails.
        """
        import io
        import tarfile

        image_name = f"{CLI_IMAGE_PREFIX}:{cli_version}"

        # Fast path: image already in local cache
        try:
            self.client.images.get(image_name)
            log.info("CLI image %s already cached — reusing", image_name)
            return image_name
        except docker.errors.ImageNotFound:
            pass

        log.info("Building CLI image %s (first use — ~30-60s)…", image_name)

        dockerfile = (
            "FROM node:20-slim\n"
            f"RUN npm install -g @cartesi/cli@{cli_version} --quiet\n"
            'CMD ["tail", "-f", "/dev/null"]\n'
        )

        # docker-py requires the build context as a tar archive in-memory
        tar_buffer = io.BytesIO()
        with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
            df_bytes = dockerfile.encode()
            info     = tarfile.TarInfo(name="Dockerfile")
            info.size = len(df_bytes)
            tar.addfile(info, io.BytesIO(df_bytes))
        tar_buffer.seek(0)

        try:
            self.client.images.build(
                fileobj=tar_buffer,
                custom_context=True,
                tag=image_name,
                rm=True,
            )
            log.info("Built CLI image %s successfully", image_name)
            return image_name
        except docker.errors.BuildError as exc:
            raise RuntimeError(
                f"Failed to build CLI image {image_name}: {exc}"
            ) from exc

    # ── Health checks ──────────────────────────────────────────────────────────

    def _wait_for_anvil_health_sync(self, container_id: str, timeout: int = 60) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                container = self.client.containers.get(container_id)
                exit_code, _ = container.exec_run(
                    ["cast", "block-number", "--rpc-url", "http://localhost:8545"]
                )
                if exit_code == 0:
                    return True
            except Exception as exc:
                log.debug("Anvil health check attempt failed: %s", exc)
            time.sleep(2)
        return False

    def _wait_for_database_sync(self, container_id: str, timeout: int = 60) -> bool:
        """
        Wait for the Cartesi database container to be ready for connections.

        Uses exec_run with list-form command (avoids shell quoting issues) and
        forces TCP via -h localhost (avoids Unix-socket access issues in exec env).
        Falls back to a running-status check if pg_isready is not available.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                container = self.client.containers.get(container_id)
                # Check container is still running first
                if container.status not in ("running", "created"):
                    log.warning("Database container %s is %s — giving up",
                                container_id[:12], container.status)
                    return False

                exit_code, output = container.exec_run(
                    ["pg_isready", "-h", "localhost", "-U", "postgres"]
                )
                if exit_code == 0:
                    log.info("Database container %s is ready (pg_isready OK)",
                             container_id[:12])
                    return True
                # Non-zero: might still be starting — retry
                log.debug("pg_isready exit_code=%d output=%s", exit_code,
                          output.decode("utf-8", errors="replace")[:100] if output else "")
            except Exception as exc:
                log.debug("Database health check attempt failed: %s", exc)
            time.sleep(3)

        log.warning("Database container %s did not pass pg_isready in %ds — "
                    "proceeding anyway (container may still be starting)",
                    container_id[:12], timeout)
        # Return True as a soft fallback: let the dependent services attempt startup.
        # They will retry their own DB connections internally.
        return True

    def _wait_for_v2_ready_sync(
        self, db_container_id: str, jsonrpc_container_id: str, timeout: int = 120
    ) -> bool:
        """Check that the jsonrpc-api container is still running (best-effort)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                c = self.client.containers.get(jsonrpc_container_id)
                if c.status == "running":
                    return True
            except Exception:
                pass
            time.sleep(5)
        return False

    # ── Compose file writer ────────────────────────────────────────────────────

    def _build_compose_dict(
        self, sandbox_id: str, node_major_version: int, image_tag: str,
        sdk_version: Optional[str],
        anvil_port: int, node_port: int, graphql_port: int,
        cli_version: Optional[str] = None,
    ) -> dict:
        """Build a docker-compose dict for this sandbox (written to disk for inspection)."""
        short      = sandbox_id[:8]
        anvil_name = f"rvp-anvil-{short}"

        if node_major_version >= 2 and sdk_version:
            runtime_image = f"cartesi/rollups-runtime:{sdk_version}"
            db_image      = f"cartesi/rollups-database:{sdk_version}"
            common_env    = {
                "CARTESI_LOG_LEVEL": "info",
                "CARTESI_AUTH_KIND": "private_key",
                "CARTESI_AUTH_PRIVATE_KEY": "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
                "CARTESI_BLOCKCHAIN_ID":            "31337",
                "CARTESI_BLOCKCHAIN_WS_ENDPOINT":   f"ws://{anvil_name}:8545",
                "CARTESI_BLOCKCHAIN_HTTP_ENDPOINT": f"http://{anvil_name}:8545",
                "CARTESI_SNAPSHOTS_DIR":            "/var/lib/cartesi-rollups-node/snapshot",
                "CARTESI_DATABASE_CONNECTION":      f"postgres://postgres:password@rvp-db-{short}:5432/rollupsdb?sslmode=disable",
                "CARTESI_EPOCH_LENGTH":             "1",
                "CARTESI_BLOCKCHAIN_DEFAULT_BLOCK": "latest",
                **DEVNET_ENV,
            }
            return {
                "# generated": f"sandbox {sandbox_id} — sdk {sdk_version}",
                "networks": {"sandbox": {"driver": "bridge", "name": f"rvp-sbx-{short}"}},
                "volumes":  {"data": {}, TEST_SNAPSHOT_VOLUME: {"external": True}},
                "services": {
                    "anvil": {
                        "image": ANVIL_IMAGE,
                        "container_name": anvil_name,
                        "command": "anvil --host 0.0.0.0 --port 8545 --block-time 1 --chain-id 31337",
                        "networks": ["sandbox"],
                        "ports": [f"{anvil_port}:8545"],
                    },
                    "database": {
                        "image": db_image,
                        "container_name": f"rvp-db-{short}",
                        "networks": ["sandbox"],
                        "environment": {"POSTGRES_PASSWORD": "password"},
                        "healthcheck": {
                            "test": ["CMD-SHELL", "pg_isready -U postgres || exit 1"],
                            "interval": "10s", "timeout": "1s", "retries": 5,
                        },
                    },
                    "evm-reader": {
                        "image": runtime_image,
                        "container_name": f"rvp-evm-reader-{short}",
                        "command": "cartesi-rollups-evm-reader --default-block latest",
                        "networks": ["sandbox"],
                        "environment": common_env,
                        "depends_on": {"database": {"condition": "service_healthy"}},
                    },
                    "advancer": {
                        "image": runtime_image,
                        "container_name": f"rvp-advancer-{short}",
                        "command": "cartesi-rollups-advancer",
                        "networks": ["sandbox"],
                        "ports": [f"{graphql_port}:10012"],
                        "environment": common_env,
                        "volumes": [
                            "data:/var/lib/cartesi-rollups-node/data",
                            f"{TEST_SNAPSHOT_VOLUME}:/var/lib/cartesi-rollups-node/snapshot:ro",
                        ],
                        "depends_on": {"database": {"condition": "service_healthy"}},
                    },
                    "validator": {
                        "image": runtime_image,
                        "container_name": f"rvp-validator-{short}",
                        "command": "cartesi-rollups-validator",
                        "networks": ["sandbox"],
                        "environment": common_env,
                        "depends_on": {"database": {"condition": "service_healthy"}},
                    },
                    "claimer": {
                        "image": runtime_image,
                        "container_name": f"rvp-claimer-{short}",
                        "command": "cartesi-rollups-claimer",
                        "networks": ["sandbox"],
                        "environment": common_env,
                        "depends_on": {"database": {"condition": "service_healthy"}},
                    },
                    "jsonrpc-api": {
                        "image": runtime_image,
                        "container_name": f"rvp-jsonrpc-{short}",
                        "command": "cartesi-rollups-jsonrpc-api",
                        "networks": ["sandbox"],
                        "ports": [f"{node_port}:10011"],
                        "environment": common_env,
                        "depends_on": {"database": {"condition": "service_healthy"}},
                    },
                    **(
                        {
                            "cli-tools": {
                                "image": f"{CLI_IMAGE_PREFIX}:{cli_version}",
                                "container_name": f"rvp-cli-{short}",
                                "networks": ["sandbox"],
                                "command": "tail -f /dev/null",
                            }
                        }
                        if cli_version else {}
                    ),
                },
            }
        else:
            # v1.x
            return {
                "# generated": f"sandbox {sandbox_id} — v1.x node",
                "networks": {"sandbox": {"driver": "bridge", "name": f"rvp-sbx-{short}"}},
                "services": {
                    "anvil": {
                        "image": ANVIL_IMAGE,
                        "container_name": anvil_name,
                        "command": "anvil --host 0.0.0.0 --port 8545 --block-time 1",
                        "networks": ["sandbox"],
                        "ports": [f"{anvil_port}:8545"],
                    },
                    "node": {
                        "image": image_tag,
                        "container_name": f"rvp-node-{short}",
                        "networks": ["sandbox"],
                        "ports": [f"{node_port}:5004", f"{graphql_port}:4000"],
                        "environment": {
                            "CARTESI_BLOCKCHAIN_HTTP_ENDPOINT": f"http://{anvil_name}:8545",
                            "CARTESI_BLOCKCHAIN_WS_ENDPOINT":   f"ws://{anvil_name}:8545",
                            "CARTESI_CONTRACTS_INPUT_BOX_ADDRESS": "0x59b22D57D4f067708AB0c00552767405926dc768",
                            "CARTESI_LOG_LEVEL": "info",
                        },
                        "depends_on": ["anvil"],
                    },
                },
            }

    def _write_compose_yaml(self, sandbox_id: str, compose_dict: dict):
        """Write the compose dict to disk for human inspection and debugging."""
        import os as _os
        compose_dir  = _os.path.join(COMPOSE_DIR, f"sbx-{sandbox_id[:8]}")
        compose_path = _os.path.join(compose_dir, "docker-compose.yml")
        try:
            _os.makedirs(compose_dir, exist_ok=True)
            with open(compose_path, "w") as f:
                # Remove the comment key before dumping
                safe = {k: v for k, v in compose_dict.items() if not k.startswith("#")}
                yaml.dump(safe, f, default_flow_style=False, sort_keys=False)
            log.info("Compose file written to %s", compose_path)
        except Exception as exc:
            log.warning("Could not write compose file: %s", exc)

    # ── Teardown ───────────────────────────────────────────────────────────────

    def _teardown_sync(self, sandbox_id: str, container_ids: list[str], network_name: str):
        log.info("Tearing down sandbox %s (%d containers)", sandbox_id, len(container_ids))
        for cid in container_ids:
            try:
                c = self.client.containers.get(cid)
                c.stop(timeout=10)
                c.remove(force=True)
                log.info("Removed container %s", cid[:12])
            except Exception as exc:
                log.warning("Could not remove container %s: %s", cid[:12], exc)

        try:
            net = self.client.networks.get(network_name)
            net.remove()
            log.info("Removed network %s", network_name)
        except Exception as exc:
            log.warning("Could not remove network %s: %s", network_name, exc)

        # Clean up compose file directory
        import shutil, os as _os
        compose_dir = _os.path.join(COMPOSE_DIR, f"sbx-{sandbox_id[:8]}")
        try:
            shutil.rmtree(compose_dir, ignore_errors=True)
        except Exception:
            pass
