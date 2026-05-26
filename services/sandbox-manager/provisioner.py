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
import hashlib
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Optional

import docker
import yaml
from docker.models.containers import Container
from docker.models.networks   import Network

from log_buffer import LogBatchBuffer

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

# ── Health + deployment timeouts ──────────────────────────────────────────────
SANDBOX_HEALTH_TIMEOUT = int(os.environ.get("SANDBOX_HEALTH_TIMEOUT", "60"))

# ── Cannon deployer ───────────────────────────────────────────────────────────
CANNON_DEPLOYER_IMAGE_PREFIX = "rvp-cannon-deployer"
CANNON_DEPLOYER_BUILD_PATH   = os.environ.get("CANNON_DEPLOYER_BUILD_PATH", "/app/cannon-deployer")
# Anvil account #0 private key (well-known test key, same as CARTESI_AUTH_PRIVATE_KEY)
DEPLOYER_KEY             = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
CONTRACTS_DEPLOY_TIMEOUT = int(os.environ.get("CONTRACTS_DEPLOY_TIMEOUT", "300"))

# ── Compose file directory ─────────────────────────────────────────────────────
COMPOSE_DIR = os.environ.get("SANDBOX_COMPOSE_DIR", "/tmp/rvp-sandboxes")

# ── App build / deploy configuration ─────────────────────────────────────────
APP_BUILD_DIR      = os.environ.get("APP_BUILD_DIR", "/tmp/rvp-app-builds")
APP_BUILD_TIMEOUT  = int(os.environ.get("APP_BUILD_TIMEOUT",  "600"))  # cartesi build seconds
APP_CLONE_TIMEOUT  = int(os.environ.get("APP_CLONE_TIMEOUT",  "120"))  # git clone seconds
APP_DEPLOY_TIMEOUT = int(os.environ.get("APP_DEPLOY_TIMEOUT", "120"))  # deploy exec seconds

# ── Build cache — snapshot volumes reused across runs ────────────────────────
# Each successful build is saved as a named Docker volume keyed on
# sha256(app_github_url + ":" + cli_version + ":" + commit_sha)[:16].
# Volumes are labelled so old entries can be found and evicted.
APP_CACHE_VOLUME_PREFIX = "rvp-cache"
APP_CACHE_MAX_PER_APP   = int(os.environ.get("APP_CACHE_MAX_PER_APP", "3"))


class SandboxProvisioner:

    def __init__(self):
        self._client: Optional[docker.DockerClient] = None
        # Per-sandbox stop events for log-streaming daemon threads
        self._log_stop_events: dict[str, threading.Event] = {}
        # Per-sandbox Docker volume name created during app build (for cleanup on teardown)
        self._per_sandbox_volumes: dict[str, str] = {}
        # Per-sandbox LogBatchBuffer (for flushing on teardown)
        self._log_buffers: dict[str, "LogBatchBuffer"] = {}
        # Per-cache-key build locks — prevents two concurrent runs from building
        # the same (app, cli_version, commit_sha) combination simultaneously.
        self._build_locks: dict[str, threading.Lock] = {}

    @property
    def client(self) -> docker.DockerClient:
        if self._client is None:
            # Use a long timeout so container.wait() doesn't time out during
            # slow operations like cannon contract deployment (~2-3 min).
            self._client = docker.from_env(timeout=600)
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
        step_cb=None,
        log_buffer: Optional["LogBatchBuffer"] = None,
        # Application build/deploy params — present when run has an app_id
        app_name:       Optional[str] = None,
        app_github_url: Optional[str] = None,
    ) -> dict:
        """
        Provision a sandbox.  step_cb(step, status, **detail) is called
        synchronously from the worker thread at each key provisioning step so
        callers can stream progress events without polling.

        log_buffer, when provided, receives ALL container log lines (from every
        container — including Anvil, build containers, and node services) as well
        as subprocess / exec_run output from clone, cartesi build, and deploy steps.
        Lines are batched before publishing so RabbitMQ is not flooded.

        When app_github_url is set (and node_major_version >= 2), the provisioner
        will also:
          1. Clone the application repo and run `cartesi build` (pre-run phase).
             Raises RuntimeError immediately if build fails — nothing else proceeds.
          2. After the node is ready, deploy the application contract on-chain by
             calling SelfHostedApplicationFactory.newApplication via `cast send`
             on a Foundry container connected to the sandbox network, then
             register with the node (best-effort; evm-reader auto-detects).
          3. Clean up the clone dir and per-sandbox snapshot volume on teardown.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None,
            self._provision_sync,
            sandbox_id, run_id, image_tag, port_offset,
            sdk_version, node_major_version, cli_version,
            devnet_version, contracts_version, step_cb, log_buffer,
            app_name, app_github_url,
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

    async def teardown(self, sandbox_id: str, container_ids: list[str], network_name: str,
                       per_sandbox_volume: Optional[str] = None):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None, self._teardown_sync, sandbox_id, container_ids, network_name,
            per_sandbox_volume,
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
        step_cb=None,
        log_buffer: Optional["LogBatchBuffer"] = None,
        app_name: Optional[str] = None,
        app_github_url: Optional[str] = None,
    ) -> dict:
        anvil_port, node_port, graphql_port = self._allocate_ports(port_offset)
        network_name = f"rvp-sbx-{sandbox_id[:8]}"

        log.info(
            "Provisioning sandbox %s (run=%s, node_major=%d, sdk=%s, cli=%s, devnet=%s, contracts=%s) ports=%d/%d/%d",
            sandbox_id, run_id, node_major_version, sdk_version, cli_version,
            devnet_version, contracts_version, anvil_port, node_port, graphql_port,
        )

        def _step(name: str, status: str = "ok", **detail):
            """Emit a provisioning step event via the caller-supplied callback."""
            if step_cb:
                try:
                    step_cb(name, status, **detail)
                except Exception as exc:
                    log.debug("step_cb error for step '%s': %s", name, exc)

        container_ids:      list[str] = []
        cli_container_name: Optional[str] = None
        snapshot_volume:    str = TEST_SNAPSHOT_VOLUME   # may be overridden by app build
        per_sandbox_volume: Optional[str] = None         # volume to delete on teardown
        app_address:        Optional[str] = None
        advancer_container_id: Optional[str] = None      # set after v2 services start

        # Track the log buffer so teardown can flush remaining lines
        if log_buffer is not None:
            self._log_buffers[sandbox_id] = log_buffer

        # ── Phase 0: App build (pre-run) ─────────────────────────────────────
        # Resolve the HEAD commit SHA (via git ls-remote, no full clone needed)
        # and check the build cache.  On a hit, copy the cached snapshot volume
        # into a fresh per-sandbox volume — no clone or `cartesi build` required.
        # On a miss, run the full build then save the result to the cache for
        # future runs.  Build failures abort immediately — nothing else proceeds.
        do_app = bool(app_github_url and cli_version and node_major_version >= 2)
        if do_app:
            _step("app_build_start", "info",
                  app=app_name or "", url=app_github_url)
            try:
                vol = self._get_or_build_app_sync(
                    sandbox_id, app_name or "app", app_github_url, cli_version,
                    step_cb=_step, log_buffer=log_buffer,
                )
                snapshot_volume    = vol
                per_sandbox_volume = vol
                self._per_sandbox_volumes[sandbox_id] = vol  # track for teardown
                _step("app_build_done", "ok",
                      app=app_name or "", snapshot_volume=vol)
            except Exception as exc:
                log.error("App build failed for sandbox %s (%s): %s",
                          sandbox_id, app_name, exc)
                _step("app_build_failed", "failed",
                      app=app_name or "", reason=str(exc)[:400])
                raise RuntimeError(f"App build failed: {exc}") from exc

        try:
            # 1. Isolated Docker network
            self.client.networks.create(
                name=network_name,
                driver="bridge",
                labels={"rvp.sandbox_id": sandbox_id, "rvp.run_id": run_id},
            )
            _step("network_created", network=network_name)

            # 2. Start Anvil
            anvil = self._start_anvil(sandbox_id, network_name, anvil_port)
            container_ids.append(anvil.id)
            _step("anvil_started", port=anvil_port, container_id=anvil.id[:12])

            # 3. Wait for Anvil to be ready before deploying or starting services
            log.info("Waiting for Anvil health in sandbox %s (timeout=%ds)…",
                     sandbox_id, SANDBOX_HEALTH_TIMEOUT)
            _step("anvil_health_check", "info")
            if not self._wait_for_anvil_health_sync(anvil.id, SANDBOX_HEALTH_TIMEOUT):
                _step("anvil_health_check", "failed",
                      reason=f"Not healthy after {SANDBOX_HEALTH_TIMEOUT}s")
                raise RuntimeError(
                    f"Anvil did not become healthy within {SANDBOX_HEALTH_TIMEOUT}s"
                )
            _step("anvil_healthy")

            # 4. Deploy rollups-contracts via cannon (when contracts_version is known)
            contract_addresses: Optional[dict] = None
            if contracts_version:
                _step("contracts_deploying", "info", contracts_version=contracts_version)
                try:
                    contract_addresses = self._deploy_contracts_sync(
                        sandbox_id, network_name, contracts_version,
                        anvil_container_id=anvil.id, step_cb=_step,
                    )
                    _step("contracts_deployed",
                          input_box=contract_addresses.get(
                              "CARTESI_CONTRACTS_INPUT_BOX_ADDRESS", ""))
                except Exception as exc:
                    log.error(
                        "Contract deployment failed for sandbox %s (%s): %s",
                        sandbox_id, contracts_version, exc,
                    )
                    _step("contracts_failed", "failed",
                          contracts_version=contracts_version,
                          reason=str(exc)[:300])
                    raise RuntimeError(
                        f"Contract deployment failed for contracts_version={contracts_version}: {exc}"
                    ) from exc
            else:
                _step("contracts_skipped", "info",
                      reason="No contracts_version for this release — using built-in devnet addresses")

            # 5. Start node services
            if node_major_version >= 2 and sdk_version:
                _step("node_starting", "info",
                      node_major_version=node_major_version, sdk_version=sdk_version)
                new_ids, cli_container_name, advancer_container_id = self._start_v2_services(
                    sandbox_id, network_name, sdk_version,
                    node_port, graphql_port,
                    cli_version=cli_version,
                    contract_addresses=contract_addresses,
                    snapshot_volume=snapshot_volume,
                )
                _step("node_started",
                      container_count=len(new_ids),
                      node_port=node_port,
                      graphql_port=graphql_port)
            else:
                _step("node_starting", "info", node_major_version=node_major_version)
                new_ids = self._start_v1_node(
                    sandbox_id, network_name, image_tag,
                    node_port, graphql_port,
                )
                _step("node_started",
                      container_count=len(new_ids),
                      node_port=node_port,
                      graphql_port=graphql_port)
            container_ids.extend(new_ids)

            # 6. Start service log-streaming daemon threads so logs from every
            #    container are captured and forwarded to the log buffer for
            #    persistent storage (+ real-time WebSocket delivery).
            #    All containers are streamed, including anvil and cli-tools.
            #
            #    We iterate over the already-tracked container_ids rather than
            #    calling containers.list() with a label filter.  containers.list()
            #    only returns *running* containers, so any container that exits
            #    quickly (e.g. evm-reader crashing on startup, cli-tools finishing)
            #    before this point would be silently skipped.  Using the IDs we
            #    already have guarantees every container gets a streaming thread,
            #    even if it has already exited — Docker still buffers its logs.
            if log_buffer is not None or step_cb:
                stop_event = threading.Event()
                self._log_stop_events[sandbox_id] = stop_event
                for cid in container_ids:
                    try:
                        c = self.client.containers.get(cid)
                        component = c.labels.get("rvp.component", "unknown")
                        # Skip ephemeral build containers — their logs are captured
                        # inline during the build phase, not via streaming threads.
                        if component in ("build-ctx", ""):
                            continue
                        threading.Thread(
                            target=self._stream_service_logs,
                            args=(c.id, component, sandbox_id, step_cb, log_buffer, stop_event),
                            daemon=True,
                            name=f"log-{sandbox_id[:8]}-{component}",
                        ).start()
                        log.debug("Started log stream for %s/%s", sandbox_id[:8], component)
                    except Exception as exc:
                        log.warning("Could not set up log stream for container %s: %s",
                                    cid[:12], exc)

            # 7. Deploy application contract (v2.x only, when app was built)
            if do_app and advancer_container_id:
                _step("app_deploy_start", "info", app=app_name or "")
                try:
                    app_address = self._deploy_app_sync(
                        sandbox_id, app_name or "app", advancer_container_id,
                        step_cb=_step, log_buffer=log_buffer,
                        network_name=network_name,
                        contract_addresses=contract_addresses,
                        snapshot_volume=snapshot_volume,
                    )
                    _step("app_deploy_done", "ok",
                          app=app_name or "", app_address=app_address)

                    # Wait for the evm-reader to pick up the ApplicationCreated
                    # event emitted by deployContracts.  The evm-reader watches
                    # the chain from the current block; with block-time=1s it
                    # processes the deploy block within 1-2 seconds.  We poll
                    # Anvil for 2 new blocks (confirmation window) then add a
                    # 5-second grace period for the evm-reader's internal
                    # registration pipeline.  Without this wait, tests that hit
                    # the jsonrpc-api immediately after ready see a 404 because
                    # the application isn't registered yet.
                    if log_buffer is not None:
                        log_buffer.append(
                            "deploy", "info",
                            "[deploy] Waiting for evm-reader to register application…",
                        )
                    self._wait_for_app_registration_sync(
                        anvil.id, app_address, _log=None, timeout=30,
                    )
                    if log_buffer is not None:
                        log_buffer.append(
                            "deploy", "info",
                            f"[deploy] evm-reader sync window elapsed — "
                            f"application {app_address} should be registered",
                        )
                        log_buffer.flush()

                except Exception as exc:
                    log.error("App deploy failed for sandbox %s (%s): %s",
                              sandbox_id, app_name, exc)
                    _step("app_deploy_failed", "failed",
                          app=app_name or "", reason=str(exc)[:400])
                    raise RuntimeError(f"App deploy failed: {exc}") from exc

            # 8. Write compose YAML for inspection
            compose_dict = self._build_compose_dict(
                sandbox_id, node_major_version, image_tag, sdk_version,
                anvil_port, node_port, graphql_port,
                cli_version=cli_version,
                contract_addresses=contract_addresses,
            )
            self._write_compose_yaml(sandbox_id, compose_dict)

        except Exception:
            log.warning("Provisioning failed for %s — cleaning up", sandbox_id)
            self._teardown_sync(sandbox_id, container_ids, network_name,
                                per_sandbox_volume=per_sandbox_volume)
            raise

        log.info("Sandbox %s provisioned: %d containers (cli=%s, app_address=%s)",
                 sandbox_id, len(container_ids), cli_container_name, app_address)
        return {
            "sandbox_id":           sandbox_id,
            "run_id":               run_id,
            "docker_network":       network_name,
            "container_ids":        container_ids,
            "anvil_port":           anvil_port,
            "node_port":            node_port,
            "graphql_port":         graphql_port,
            "cli_container_name":   cli_container_name,
            "app_address":          app_address,
            "per_sandbox_volume":   per_sandbox_volume,
        }

    # ── Container launchers ────────────────────────────────────────────────────

    def _start_anvil(self, sandbox_id: str, network: str, port: int) -> Container:
        return self.client.containers.run(
            ANVIL_IMAGE,
            # Single-element list — the Foundry image ENTRYPOINT is ['/bin/sh', '-c'].
            # docker-py splits plain strings by whitespace before passing them as CMD,
            # so Docker would run: /bin/sh -c anvil --host 0.0.0.0 ...
            # With -c, only the first word ('anvil') is the shell script; all flags
            # become positional args ($0, $1, …) and are silently dropped — Anvil
            # starts on 127.0.0.1 in instant-mine mode, unreachable from other
            # containers.  Wrapping the full command in a one-element list causes
            # Docker to receive Cmd=["anvil --host 0.0.0.0 ..."], so /bin/sh -c runs
            # the whole string as a proper shell script — all flags reach Anvil.
            command=["anvil --host 0.0.0.0 --port 8545 --block-time 1 --chain-id 31337"],
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
        contract_addresses: Optional[dict] = None,
        snapshot_volume: Optional[str] = None,
    ) -> tuple[list[str], Optional[str], Optional[str]]:
        """
        Start the full 6-service SDK stack for a v2.x node release.

        If cli_version is provided, also builds/reuses a per-version CLI image
        and starts a cli-tools container in the sandbox network.

        snapshot_volume overrides TEST_SNAPSHOT_VOLUME for the advancer mount.
        Use a per-sandbox volume when the app was built for this run.

        Returns (container_ids, cli_container_name, advancer_container_id).
        cli_container_name / advancer_container_id are None when unavailable.
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
            **(contract_addresses or DEVNET_ENV),
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
        # --default-block latest: evm-reader watches from its start block forward.
        # Since it starts before app deployment, it will see the ApplicationCreated
        # event when deployContracts is called ~30-60 s later.  "genesis" is not a
        # valid value for this flag (valid: latest, safe, pending, finalized).
        #
        # time.sleep(3): Anvil's health check uses exec_run (loopback :8545), which
        # passes before the bridge interface finishes binding.  A short sleep lets
        # the bridge IP stabilise so evm-reader's first connection attempt succeeds.
        #
        # restart_policy=on-failure: if evm-reader still loses the race, Docker
        # restarts it automatically so it will be up by the time tests run.
        time.sleep(3)
        evm_reader: Container = self.client.containers.run(
            runtime_image,
            command="cartesi-rollups-evm-reader --default-block latest",
            name=f"rvp-evm-reader-{short}",
            network=network,
            environment=common_env,
            restart_policy={"Name": "on-failure", "MaximumRetryCount": 10},
            detach=True,
            remove=False,
            labels={"rvp.sandbox_id": sandbox_id, "rvp.component": "evm-reader"},
        )
        ids.append(evm_reader.id)

        # ── advancer (mounts machine snapshot) ───────────────────────────────
        _snap_vol = snapshot_volume or TEST_SNAPSHOT_VOLUME
        snapshot_volumes = self._build_snapshot_volumes(sandbox_id, _snap_vol)
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
        advancer_cid = advancer.id

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
        return ids, cli_container_name, advancer_cid

    def _build_snapshot_volumes(self, sandbox_id: str,
                                   volume_name: Optional[str] = None) -> dict:
        """
        Return the Docker SDK volumes dict for the advancer snapshot mount.

        Uses volume_name if provided; falls back to TEST_SNAPSHOT_VOLUME.
        Returns an empty dict if the volume doesn't exist (advancer starts
        without a snapshot — health-check tests will still pass).
        """
        vol = volume_name or TEST_SNAPSHOT_VOLUME
        try:
            self.client.volumes.get(vol)
            log.info("Mounting volume %s as machine snapshot for sandbox %s", vol, sandbox_id)
            return {
                vol: {
                    "bind": "/var/lib/cartesi-rollups-node/snapshot",
                    "mode": "ro",
                }
            }
        except Exception:
            log.warning(
                "Volume %s not found — advancer will start without a machine snapshot. "
                "Use `make build-test-app` (generic) or trigger a run with an app to build one.",
                vol,
            )
            return {}

    # ── Application build cache ────────────────────────────────────────────────

    def _get_or_build_app_sync(
        self,
        sandbox_id:     str,
        app_name:       str,
        app_github_url: str,
        cli_version:    str,
        step_cb=None,
        log_buffer: Optional["LogBatchBuffer"] = None,
    ) -> str:
        """
        Return a per-sandbox Docker volume containing the Cartesi machine
        snapshot, either restored from the build cache or freshly built.

        Cache key = sha256(app_github_url + ":" + cli_version + ":" + HEAD SHA).
        The HEAD commit SHA is resolved with ``git ls-remote`` (no full clone).

        Cache hit  → copy cached volume to fresh per-sandbox volume (~2s).
        Cache miss → full clone + cartesi build, then save to cache volume.

        If the commit SHA cannot be resolved (no network, private repo without
        auth, etc.) the cache is skipped and a fresh build is always performed.
        """
        import hashlib as _hashlib

        short    = sandbox_id[:8]
        snap_vol = f"rvp-snapshot-{short}"

        def _log(level: str, msg: str) -> None:
            log.info("[build-cache] %s", msg)
            if log_buffer is not None:
                log_buffer.append("build", level, f"[build-cache] {msg}")

        # ── Resolve HEAD commit SHA (fast path — no clone) ─────────────────
        commit_sha: Optional[str] = None
        try:
            commit_sha = self._resolve_commit_sha_sync(app_github_url)
            _log("info", f"HEAD commit: {commit_sha[:12]}…  "
                         f"(app={app_name!r}, cli={cli_version})")
        except Exception as exc:
            _log("warn", f"Could not resolve commit SHA ({exc}) — "
                         "cache disabled, performing fresh build")

        # ── Compute cache key ───────────────────────────────────────────────
        cache_vol: Optional[str] = None
        cache_key: Optional[str] = None
        if commit_sha:
            raw      = f"{app_github_url}:{cli_version}:{commit_sha}"
            cache_key = hashlib.sha256(raw.encode()).hexdigest()[:16]
            cache_vol = f"{APP_CACHE_VOLUME_PREFIX}-{cache_key}"

        # ── Cache lookup + build under per-key lock ─────────────────────────
        if cache_key and cache_vol:
            lock = self._build_locks.setdefault(cache_key, threading.Lock())
            with lock:
                # Check for an existing cache volume (double-checked inside lock)
                try:
                    self.client.volumes.get(cache_vol)
                    # ── Cache HIT ──────────────────────────────────────────
                    _log("info",
                         f"Cache HIT [{cache_key}] — restoring snapshot "
                         f"(skipping clone + build)")
                    if step_cb:
                        step_cb("app_build_cache_hit", "ok",
                                app=app_name, cache_key=cache_key,
                                commit_sha=commit_sha[:12])
                    # Create a fresh per-sandbox volume and copy from cache
                    self._create_volume_from_cache_sync(
                        cache_vol, snap_vol, sandbox_id, _log,
                    )
                    _log("info", f"Snapshot restored to {snap_vol} from cache")
                    return snap_vol
                except docker.errors.NotFound:
                    pass

                # ── Cache MISS — full build ─────────────────────────────────
                _log("info",
                     f"Cache MISS [{cache_key}] — running full clone + build")
                if step_cb:
                    step_cb("app_build_cache_miss", "info",
                            app=app_name, cache_key=cache_key,
                            commit_sha=commit_sha[:12] if commit_sha else "")

                built_vol = self._build_app_sync(
                    sandbox_id, app_name, app_github_url, cli_version,
                    step_cb=step_cb, log_buffer=log_buffer,
                )

                # Save successful build to cache (non-fatal if it fails)
                _log("info", f"Saving build to cache volume {cache_vol}…")
                try:
                    self._save_snapshot_to_cache_sync(
                        built_vol, cache_vol,
                        app_github_url, cli_version, commit_sha, _log,
                    )
                    _log("info", f"Build cached as {cache_vol}")
                    if step_cb:
                        step_cb("app_build_cached", "ok",
                                app=app_name, cache_vol=cache_vol,
                                cache_key=cache_key)
                    # Evict old entries for this app beyond the keep limit
                    self._evict_old_build_cache_sync(
                        app_github_url, keep_n=APP_CACHE_MAX_PER_APP, log_fn=_log,
                    )
                except Exception as exc:
                    _log("warn",
                         f"Failed to save build to cache ({exc}) — "
                         "continuing; next run will rebuild")

                return built_vol
        else:
            # No commit SHA — build fresh without caching
            return self._build_app_sync(
                sandbox_id, app_name, app_github_url, cli_version,
                step_cb=step_cb, log_buffer=log_buffer,
            )

    def _resolve_commit_sha_sync(self, app_github_url: str) -> str:
        """
        Return the HEAD commit SHA for a Git repository using ``git ls-remote``.
        Does not clone — resolves the ref in a single network round-trip (~1s).
        Raises RuntimeError if the command fails or output is unparseable.
        """
        import subprocess as _subprocess
        result = _subprocess.run(
            ["git", "ls-remote", "--quiet", app_github_url, "HEAD"],
            capture_output=True, text=True,
            timeout=APP_CLONE_TIMEOUT,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git ls-remote failed (exit {result.returncode}): "
                f"{result.stderr.strip()[:300]}"
            )
        # Output: "<sha>\tHEAD\n"
        first_line = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
        sha = first_line.split("\t")[0].strip()
        if len(sha) == 40 and all(c in "0123456789abcdef" for c in sha):
            return sha
        raise RuntimeError(
            f"Could not parse SHA from git ls-remote output: {first_line!r}"
        )

    def _create_volume_from_cache_sync(
        self,
        cache_vol:  str,
        snap_vol:   str,
        sandbox_id: str,
        log_fn,
    ) -> None:
        """
        Create a fresh per-sandbox Docker volume and populate it by copying
        all files from the cache volume.  Uses Alpine so we have no dependency
        on utilities in any other container image.
        """
        # Create the destination volume (remove stale copy if present)
        try:
            self.client.volumes.get(snap_vol).remove(force=True)
        except Exception:
            pass
        self.client.volumes.create(
            snap_vol,
            labels={
                "rvp.sandbox_id": sandbox_id,
                "rvp.component":  "snapshot",
                "rvp.from_cache": cache_vol,
            },
        )
        self._copy_volume_sync(cache_vol, snap_vol, log_fn)

    def _save_snapshot_to_cache_sync(
        self,
        snap_vol:       str,
        cache_vol:      str,
        app_github_url: str,
        cli_version:    str,
        commit_sha:     str,
        log_fn,
    ) -> None:
        """
        Create a labelled cache Docker volume and copy the snapshot into it.
        Labels allow the eviction logic to find and age-out old entries.
        """
        import hashlib as _hashlib, time as _time
        app_url_hash = _hashlib.sha256(app_github_url.encode()).hexdigest()[:16]
        try:
            self.client.volumes.get(cache_vol).remove(force=True)
        except Exception:
            pass
        self.client.volumes.create(
            cache_vol,
            labels={
                "rvp.cache":          "true",
                "rvp.app_url_hash":   app_url_hash,
                "rvp.app_url":        app_github_url[:200],
                "rvp.cli_version":    cli_version,
                "rvp.commit_sha":     commit_sha,
                "rvp.built_at":       str(int(_time.time())),
            },
        )
        self._copy_volume_sync(snap_vol, cache_vol, log_fn)

    def _copy_volume_sync(self, src_vol: str, dst_vol: str, log_fn) -> None:
        """
        Copy all files from Docker volume src_vol into dst_vol.
        dst_vol must already exist.  Runs an Alpine container — no host path
        access required.
        """
        import time as _time
        cname = f"rvp-vol-copy-{int(_time.time() * 1000) % 1_000_000}"
        try:
            self.client.containers.get(cname).remove(force=True)
        except Exception:
            pass
        c = self.client.containers.run(
            "alpine:latest",
            command=["sh", "-c", "cp -r /src/. /dst/ && echo 'volume copy done'"],
            volumes={
                src_vol: {"bind": "/src", "mode": "ro"},
                dst_vol: {"bind": "/dst", "mode": "rw"},
            },
            name=cname,
            detach=True,
            remove=False,
        )
        try:
            result = c.wait(timeout=120)
            if result["StatusCode"] != 0:
                out = c.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Volume copy {src_vol!r} → {dst_vol!r} failed "
                    f"(exit {result['StatusCode']}): {out[-300:]}"
                )
        finally:
            try:
                c.remove(force=True)
            except Exception:
                pass

    def _evict_old_build_cache_sync(
        self,
        app_github_url: str,
        keep_n:         int,
        log_fn,
    ) -> None:
        """
        Remove old build-cache volumes for the given app, keeping only the
        most recent ``keep_n`` entries (ordered by the rvp.built_at label).
        Safe to call after every successful cache write.
        """
        import hashlib as _hashlib
        app_url_hash = _hashlib.sha256(app_github_url.encode()).hexdigest()[:16]
        try:
            volumes = self.client.volumes.list(
                filters={"label": [
                    "rvp.cache=true",
                    f"rvp.app_url_hash={app_url_hash}",
                ]},
            )
        except Exception as exc:
            log_fn("warn", f"Could not list cache volumes for eviction: {exc}")
            return
        if len(volumes) <= keep_n:
            return
        # Sort oldest first by rvp.built_at (epoch seconds stored as string label)
        def _built_at(v) -> int:
            return int((v.attrs.get("Labels") or {}).get("rvp.built_at", "0"))
        volumes.sort(key=_built_at)
        to_evict = volumes[: len(volumes) - keep_n]
        for vol in to_evict:
            try:
                vol.remove(force=True)
                log_fn("info", f"Evicted old cache volume {vol.name}")
            except Exception as exc:
                log_fn("warn", f"Could not evict cache volume {vol.name}: {exc}")

    # ── Application build + deploy ─────────────────────────────────────────────

    def _build_app_sync(
        self,
        sandbox_id:     str,
        app_name:       str,
        app_github_url: str,
        cli_version:    str,
        step_cb=None,
        log_buffer: Optional["LogBatchBuffer"] = None,
    ) -> str:
        """
        Clone the application repo, run `cartesi build` inside the cli-tools
        Docker image, and load the resulting machine snapshot into a named
        Docker volume.

        Returns the Docker volume name (e.g. "rvp-snapshot-<sandbox_id[:8]>").
        Raises RuntimeError on any failure — caller must treat this as fatal.

        Host-path approach (required on Docker Desktop for Mac)
        --------------------------------------------------------
        APP_BUILD_DIR must be bind-mounted from the HOST into the
        sandbox-manager container (see docker-compose.yml volumes).  This makes
        /tmp/rvp-app-builds a real macOS host path, so:
          • the builder container can mount it as a volume (host paths only), and
          • `cartesi build`'s internal sub-containers can also mount sub-paths
            under it (Docker Desktop allows /tmp by default).
        """
        import subprocess
        import os as _os
        import shutil as _shutil

        short           = sandbox_id[:8]
        build_dir       = _os.path.join(APP_BUILD_DIR, short)
        snap_volume_name = f"rvp-snapshot-{short}"

        # ── 1. git clone ──────────────────────────────────────────────────────
        if step_cb:
            step_cb("app_clone", "info", url=app_github_url)

        _os.makedirs(APP_BUILD_DIR, exist_ok=True)
        if _os.path.isdir(build_dir):
            _shutil.rmtree(build_dir, ignore_errors=True)

        clone_result = subprocess.run(
            ["git", "clone", "--depth", "1", app_github_url, build_dir],
            capture_output=True,
            text=True,
            timeout=APP_CLONE_TIMEOUT,
        )
        if log_buffer is not None:
            for line in (clone_result.stdout + clone_result.stderr).splitlines():
                line = line.strip()
                if line:
                    log_buffer.append("build", "info", f"[clone] {line}")
        if clone_result.returncode != 0:
            raise RuntimeError(
                f"git clone failed (exit {clone_result.returncode}): "
                f"{clone_result.stderr[-600:]}"
            )

        log.info("Cloned %s → %s", app_github_url, build_dir)

        # ── 2. cartesi build (inside cli-tools image, Docker socket mounted) ─
        if step_cb:
            step_cb("app_cartesi_build", "info",
                    app=app_name, cli_version=cli_version)

        cli_image    = self._ensure_cli_image_sync(cli_version)
        builder_name = f"rvp-builder-{short}"

        try:
            old = self.client.containers.get(builder_name)
            old.remove(force=True)
        except Exception:
            pass

        builder: Container = self.client.containers.run(
            cli_image,
            command=["cartesi", "build"],
            name=builder_name,
            working_dir=build_dir,  # identity mount: container path == host path
            volumes={
                build_dir:               {"bind": build_dir, "mode": "rw"},
                "/var/run/docker.sock":  {"bind": "/var/run/docker.sock", "mode": "rw"},
            },
            detach=True,
            remove=False,
            labels={"rvp.sandbox_id": sandbox_id, "rvp.component": "app-builder"},
        )
        try:
            # Stream build logs in real-time so progress is visible during the build
            if log_buffer is not None:
                def _stream_build_logs():
                    try:
                        for raw in builder.logs(stream=True, follow=True,
                                                stdout=True, stderr=True):
                            line = raw.decode("utf-8", errors="replace").rstrip()
                            if line:
                                log_buffer.append("build", "info", f"[cartesi build] {line}")
                    except Exception:
                        pass
                build_log_thread = threading.Thread(
                    target=_stream_build_logs, daemon=True,
                    name=f"build-log-{sandbox_id[:8]}"
                )
                build_log_thread.start()

            result = builder.wait(timeout=APP_BUILD_TIMEOUT)

            # Ensure log thread finishes before we proceed
            if log_buffer is not None:
                build_log_thread.join(timeout=5)

            if result["StatusCode"] != 0:
                # Fetch full logs for error context (streaming thread may have missed tail)
                build_logs = builder.logs(
                    stdout=True, stderr=True
                ).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"cartesi build exited {result['StatusCode']}. "
                    f"Last output: {build_logs[-1200:]}"
                )
        finally:
            try:
                builder.remove(force=True)
            except Exception:
                pass

        # Verify snapshot was produced
        image_dir = _os.path.join(build_dir, ".cartesi", "image")
        if not _os.path.isdir(image_dir):
            raise RuntimeError(
                f"cartesi build succeeded but .cartesi/image/ not found in {build_dir}. "
                "The CLI version may not support this project type."
            )
        log.info("cartesi build complete — snapshot at %s", image_dir)

        # ── 3. Create snapshot volume and load snapshot files into it ─────────
        if step_cb:
            step_cb("app_snapshot_loading", "info", volume=snap_volume_name)

        try:
            self.client.volumes.get(snap_volume_name).remove(force=True)
        except Exception:
            pass
        self.client.volumes.create(
            snap_volume_name,
            labels={"rvp.sandbox_id": sandbox_id, "rvp.component": "snapshot"},
        )

        loader_name = f"rvp-snap-loader-{short}"
        try:
            old = self.client.containers.get(loader_name)
            old.remove(force=True)
        except Exception:
            pass

        loader: Container = self.client.containers.run(
            "alpine:latest",
            command=["sh", "-c", "cp -r /src/. /dst/ && echo 'snapshot loaded'"],
            name=loader_name,
            volumes={
                image_dir:        {"bind": "/src", "mode": "ro"},
                snap_volume_name: {"bind": "/dst", "mode": "rw"},
            },
            detach=True,
            remove=False,
        )
        try:
            loader_result = loader.wait(timeout=60)
            if loader_result["StatusCode"] != 0:
                out = loader.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Snapshot copy to volume failed: {out[-400:]}"
                )
        finally:
            try:
                loader.remove(force=True)
            except Exception:
                pass

        log.info("Machine snapshot loaded into volume %s for sandbox %s",
                 snap_volume_name, sandbox_id)
        return snap_volume_name

    def _deploy_app_sync(
        self,
        sandbox_id:            str,
        app_name:              str,
        advancer_container_id: str,
        step_cb=None,
        log_buffer: Optional["LogBatchBuffer"] = None,
        network_name: Optional[str] = None,
        contract_addresses: Optional[dict] = None,
        snapshot_volume: Optional[str] = None,
    ) -> str:
        """
        Deploy the application contract externally using cast send on the
        SelfHostedApplicationFactory, then register the application with the
        running node.

        This is the workaround for `cartesi-rollups-cli deploy application
        --register` always failing when run via exec_run inside the advancer
        container (the runtime image does not ship the operator CLI binary).

        Steps
        -----
        1. Read the 32-byte machine template hash from the snapshot volume
           using an Alpine helper container (no shell tool assumptions).
        2. Predict the application contract address with ``cast call``
           (simulation only — no state change, no gas).
        3. Deploy the application on-chain with ``cast send`` against the
           SelfHostedApplicationFactory in the sandbox Anvil network.
        4. Register the application with the node (best-effort).  The
           evm-reader watches the factory's ApplicationCreated events and
           will register the app automatically; the CLI call here is a
           belt-and-suspenders measure.

        Returns the deployed application contract address (0x…).
        Raises RuntimeError if the deploy fails or the address cannot be
        determined.
        """
        import hashlib as _hashlib

        salt          = "0x" + _hashlib.sha256(sandbox_id.encode()).hexdigest()
        short         = sandbox_id[:8]
        snap_vol      = snapshot_volume or TEST_SNAPSHOT_VOLUME

        # Resolve Anvil container ID so we can use network_mode=container:<id>
        # (same pattern as the cannon deployer).  Bridge DNS fails on Mac Docker
        # Desktop, but localhost:8545 inside Anvil's network namespace is reliable.
        anvil_name = f"rvp-anvil-{short}"
        try:
            anvil_cid = self.client.containers.get(anvil_name).id
        except Exception as exc:
            raise RuntimeError(
                f"Could not find Anvil container {anvil_name!r}: {exc}"
            ) from exc
        anvil_url = "http://localhost:8545"
        addrs         = contract_addresses or DEVNET_ENV
        factory_addr  = addrs.get(
            "CARTESI_CONTRACTS_SELF_HOSTED_APPLICATION_FACTORY_ADDRESS"
        )
        if not factory_addr:
            raise RuntimeError(
                "CARTESI_CONTRACTS_SELF_HOSTED_APPLICATION_FACTORY_ADDRESS "
                "not found in contract_addresses"
            )
        # Anvil account #0 is both authority owner and app owner —
        # same key used by all node services.
        OWNER = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
        # Epoch length must be > 0; use 1 to match CARTESI_EPOCH_LENGTH=1 set in
        # the node services environment.
        EPOCH_LENGTH = 1

        def _log(level: str, msg: str) -> None:
            log.info("[deploy] %s", msg)
            if log_buffer is not None:
                log_buffer.append("deploy", level, f"[deploy] {msg}")

        _log("info", f"Starting external deploy for {app_name!r} (cast workaround)")
        _log("info", f"Factory: {factory_addr}  Salt: {salt[:18]}…")
        if log_buffer is not None:
            log_buffer.flush()

        # ── 1. Machine hash ───────────────────────────────────────────────────
        _log("info", f"Reading machine hash from snapshot volume {snap_vol!r}…")
        machine_hash = self._read_machine_hash_sync(snap_vol, _log)
        _log("info", f"Machine hash: {machine_hash[:10]}…{machine_hash[-6:]}")

        # ── 2. Predict address (cast call — no state change) ─────────────────
        _log("info", "Predicting application address via calculateAddresses…")
        app_address = self._cast_predict_app_address_sync(
            sandbox_id, anvil_cid, anvil_url, factory_addr,
            OWNER, EPOCH_LENGTH, machine_hash, salt, _log,
        )
        _log("info", f"Application will be at: {app_address}")

        # ── 3. Deploy on-chain (cast send) ────────────────────────────────────
        _log("info", "Deploying application contract on-chain via deployContracts…")
        self._cast_deploy_app_sync(
            sandbox_id, anvil_cid, anvil_url, factory_addr,
            OWNER, EPOCH_LENGTH, machine_hash, salt, _log,
        )
        _log("info", f"Application deployed at {app_address}")

        # ── 4. Register with node (best-effort) ───────────────────────────────
        self._register_app_with_node_sync(advancer_container_id, app_address, _log)

        if log_buffer is not None:
            log_buffer.flush()

        log.info("Application %r deployed at %s (sandbox %s)",
                 app_name, app_address, sandbox_id)
        return app_address

    # ── Deploy helpers ─────────────────────────────────────────────────────────

    def _read_machine_hash_sync(
        self,
        snapshot_volume: str,
        log_fn,
    ) -> str:
        """
        Read the 32-byte Cartesi machine template hash from a snapshot Docker
        volume.  Returns the hash as a 0x-prefixed lowercase hex string
        (66 chars total: "0x" + 64 hex digits).

        Runs an Alpine container with the volume mounted read-only so we make
        no assumptions about which utilities are installed in the advancer image.
        """
        import time as _time
        cname = f"rvp-hash-reader-{int(_time.time() * 1000) % 1_000_000}"
        try:
            self.client.containers.get(cname).remove(force=True)
        except Exception:
            pass

        # od -An -tx1  : hex dump, no address column, one byte per space-separated field
        # tr -d ' \n'  : strip all spaces and newlines → 64 contiguous lowercase hex chars
        # hexdump fallback for Alpine versions that ship busybox od with different flags
        c = self.client.containers.run(
            "alpine:latest",
            command=[
                "sh", "-c",
                "od -An -tx1 /snap/hash 2>/dev/null | tr -d ' \\n' || "
                "hexdump -ve '1/1 \"%02x\"' /snap/hash 2>/dev/null",
            ],
            volumes={snapshot_volume: {"bind": "/snap", "mode": "ro"}},
            name=cname,
            detach=True,
            remove=False,
        )
        try:
            result = c.wait(timeout=15)
            raw    = c.logs(stdout=True, stderr=False).decode("utf-8", errors="replace").strip()
            if result["StatusCode"] != 0 or not raw:
                raise RuntimeError(
                    f"Hash-reader container exited {result['StatusCode']}, "
                    f"output: {raw!r}"
                )
            hex_str = raw.strip().lower()
            if len(hex_str) == 64 and all(ch in "0123456789abcdef" for ch in hex_str):
                return "0x" + hex_str
            raise RuntimeError(
                f"Expected 64 hex chars for machine hash, got: {hex_str!r}"
            )
        finally:
            try:
                c.remove(force=True)
            except Exception:
                pass

    def _cast_predict_app_address_sync(
        self,
        sandbox_id:      str,
        anvil_cid:       str,
        anvil_url:       str,
        factory:         str,
        owner:           str,
        epoch_length:    int,
        machine_hash:    str,
        salt:            str,
        log_fn,
    ) -> str:
        """
        Predict the application contract address by calling
        SelfHostedApplicationFactory.calculateAddresses (view, no gas).

        v2.2.0 ABI:
          calculateAddresses(address,uint256,address,bytes32,bytes,bytes32)
              returns (address appAddress, address authorityAddress)

        Parameters:
          authorityOwner  — owner of the new authority  (Anvil account #0)
          epochLength     — must be > 0 (we use 1)
          appOwner        — owner of the new application (Anvil account #0)
          templateHash    — Cartesi machine hash (bytes32)
          dataAvailability— ABI-encoded DA config; 0x = Ethereum calldata (default)
          salt            — deterministic CREATE2 salt (bytes32)

        Returns the first address from the tuple (application address).
        """
        short = sandbox_id[:8]
        cname = f"rvp-cast-predict-{short}"
        try:
            self.client.containers.get(cname).remove(force=True)
        except Exception:
            pass

        # Single-element list command: the Foundry image entrypoint is
        # ['/bin/sh', '-c'].  docker-py splits plain strings by whitespace
        # before passing them, so we wrap the full shell command in a
        # one-element list so Docker sees Cmd=["cast call …"] and the
        # entrypoint runs it as a proper shell script.
        # network_mode=container:<anvil_id>: share Anvil's network namespace so
        # localhost:8545 works — bridge DNS fails on Docker Desktop Mac.
        cmd = [
            f"cast call --rpc-url {anvil_url} {factory}"
            f" 'calculateAddresses(address,uint256,address,bytes32,bytes,bytes32)(address,address)'"
            f" {owner} {epoch_length} {owner} {machine_hash} 0x {salt}"
        ]
        c = self.client.containers.run(
            ANVIL_IMAGE,
            command=cmd,
            name=cname,
            network_mode=f"container:{anvil_cid}",
            detach=True,
            remove=False,
        )
        try:
            result = c.wait(timeout=30)
            raw    = c.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            log_fn("debug", f"calculateAddresses raw output: {raw.strip()[:300]}")
            if result["StatusCode"] != 0:
                raise RuntimeError(
                    f"calculateAddresses failed (exit {result['StatusCode']}): "
                    f"{raw.strip()[-400:]}"
                )
            # calculateAddresses returns (address, address).
            # cast prints each ABI-decoded value on a separate line.
            # First line is the application address, second is the authority address.
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            addr_line = lines[0] if lines else ""
            addr_raw  = addr_line[2:] if addr_line.startswith("0x") else addr_line
            if len(addr_raw) >= 40:
                return "0x" + addr_raw[-40:].lower()
            raise RuntimeError(
                f"Could not parse application address from calculateAddresses output: "
                f"{raw.strip()!r}"
            )
        finally:
            try:
                c.remove(force=True)
            except Exception:
                pass

    def _cast_deploy_app_sync(
        self,
        sandbox_id:      str,
        anvil_cid:       str,
        anvil_url:       str,
        factory:         str,
        owner:           str,
        epoch_length:    int,
        machine_hash:    str,
        salt:            str,
        log_fn,
    ) -> None:
        """
        Deploy the application + authority contracts on-chain by calling
        SelfHostedApplicationFactory.deployContracts via ``cast send``.

        v2.2.0 ABI:
          deployContracts(address,uint256,address,bytes32,bytes,bytes32)
              returns (IApplication, IAuthority)

        Uses DEPLOYER_KEY (Anvil account #0) to sign the transaction.
        dataAvailability=0x → Ethereum calldata (default).
        """
        short = sandbox_id[:8]
        cname = f"rvp-cast-deploy-{short}"
        try:
            self.client.containers.get(cname).remove(force=True)
        except Exception:
            pass

        # Single-element list — same reason as cast call above.
        # network_mode=container:<anvil_id>: share Anvil's network namespace so
        # localhost:8545 works — bridge DNS fails on Docker Desktop Mac.
        cmd = [
            f"cast send --rpc-url {anvil_url} --private-key {DEPLOYER_KEY} {factory}"
            f" 'deployContracts(address,uint256,address,bytes32,bytes,bytes32)'"
            f" {owner} {epoch_length} {owner} {machine_hash} 0x {salt}"
        ]
        c = self.client.containers.run(
            ANVIL_IMAGE,
            command=cmd,
            name=cname,
            network_mode=f"container:{anvil_cid}",
            detach=True,
            remove=False,
        )
        try:
            result = c.wait(timeout=APP_DEPLOY_TIMEOUT)
            raw    = c.logs(stdout=True, stderr=True).decode("utf-8", errors="replace")
            level  = "info" if result["StatusCode"] == 0 else "error"
            for line in raw.splitlines():
                line = line.strip()
                if line:
                    log_fn(level, f"[cast send] {line}")
            if result["StatusCode"] != 0:
                raise RuntimeError(
                    f"cast send (deploy) failed (exit {result['StatusCode']}): "
                    f"{raw.strip()[-600:]}"
                )
        finally:
            try:
                c.remove(force=True)
            except Exception:
                pass

    def _register_app_with_node_sync(
        self,
        advancer_container_id: str,
        app_address:           str,
        log_fn,
    ) -> None:
        """
        Attempt to register the already-deployed application with the running
        node using ``cartesi-rollups-cli register application``.

        This is a best-effort step.  The evm-reader service watches the
        SelfHostedApplicationFactory for ApplicationCreated events and will
        register the application automatically once the deployment block is
        processed.  If the CLI binary is absent from the runtime image (which
        is common for minimal distroless builds), we log and continue.
        """
        import time as _time
        # Give the evm-reader a moment to process the deployment block before
        # we attempt a CLI-based registration.
        _time.sleep(3)
        try:
            advancer = self.client.containers.get(advancer_container_id)
            ec, out = advancer.exec_run(
                ["cartesi-rollups-cli", "register", "application",
                 "--address", app_address],
                stdout=True, stderr=True, demux=False,
            )
            out_str = out.decode("utf-8", errors="replace") if out else ""
            if ec == 0:
                log_fn("info", f"Node CLI registration succeeded for {app_address}")
            else:
                log_fn("info",
                       f"CLI register returned exit {ec} — evm-reader auto-detection "
                       f"still active.  Output: {out_str[:300]}")
        except Exception as exc:
            log_fn("info",
                   f"CLI register skipped ({type(exc).__name__}: {exc}) — "
                   "evm-reader will detect ApplicationCreated event automatically")

    def _wait_for_app_registration_sync(
        self,
        anvil_container_id: str,
        app_address: str,
        _log=None,
        timeout: int = 30,
    ) -> None:
        """
        Wait until Anvil has mined at least 2 blocks past the deploy block
        (so the evm-reader's subscription window definitely contains the
        ApplicationCreated event), then sleep an additional grace period.

        This prevents tests from hitting the jsonrpc-api immediately after the
        ready signal, before the evm-reader has registered the application.

        Uses exec_run inside the Anvil container (cast block-number) so we
        don't need an extra container or an exposed port.

        Silently returns on any error — this is a best-effort sync step.
        """
        import time as _time
        BLOCKS_TO_WAIT = 2
        GRACE_SECONDS  = 5

        try:
            anvil = self.client.containers.get(anvil_container_id)

            # Snapshot the block number right after deploy
            ec, out = anvil.exec_run(
                ["cast", "block-number", "--rpc-url", "http://localhost:8545"]
            )
            if ec != 0:
                log.debug("block-number check failed (exit %d) — skipping sync wait", ec)
                _time.sleep(GRACE_SECONDS)
                return
            deploy_block = int(out.decode("utf-8", errors="replace").strip())

            log.info(
                "[deploy-sync] Deploy block=%d — waiting for +%d blocks on Anvil…",
                deploy_block, BLOCKS_TO_WAIT,
            )

            deadline = _time.time() + timeout
            while _time.time() < deadline:
                ec2, out2 = anvil.exec_run(
                    ["cast", "block-number", "--rpc-url", "http://localhost:8545"]
                )
                if ec2 == 0:
                    current = int(out2.decode("utf-8", errors="replace").strip())
                    if current >= deploy_block + BLOCKS_TO_WAIT:
                        log.info(
                            "[deploy-sync] Block %d reached (+%d) — "
                            "sleeping %ds grace period for evm-reader",
                            current, current - deploy_block, GRACE_SECONDS,
                        )
                        _time.sleep(GRACE_SECONDS)
                        return
                _time.sleep(1)

            log.warning(
                "[deploy-sync] Timeout waiting for +%d blocks — "
                "proceeding anyway (evm-reader may not have registered app yet)",
                BLOCKS_TO_WAIT,
            )
            _time.sleep(GRACE_SECONDS)

        except Exception as exc:
            log.debug("[deploy-sync] Skipping block-wait due to error: %s", exc)
            _time.sleep(GRACE_SECONDS)

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
            "FROM docker:27-cli\n"
            "RUN apk add --no-cache nodejs npm\n"
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

    # ── Cannon deployer image + contract deployment ────────────────────────────

    def _ensure_cannon_deployer_image_sync(self, contracts_version: str,
                                             step_cb=None) -> str:
        """
        Return a Docker image tag for rvp-cannon-deployer:<contracts_version>.

        On first call for a given contracts_version the image is built from
        CANNON_DEPLOYER_BUILD_PATH (mounted into the sandbox-manager container).
        Subsequent calls for the same version return instantly from image cache.

        Raises RuntimeError if the build fails.
        """
        image_name = f"{CANNON_DEPLOYER_IMAGE_PREFIX}:{contracts_version}"

        try:
            self.client.images.get(image_name)
            log.info("Cannon deployer image %s already cached — reusing", image_name)
            return image_name
        except docker.errors.ImageNotFound:
            pass

        log.info("Building cannon deployer image %s from %s (~2-5 min first time)…",
                 image_name, CANNON_DEPLOYER_BUILD_PATH)
        if step_cb:
            step_cb("deployer_image_building", "info",
                    image=image_name,
                    note="First use — building cannon deployer Docker image (2-5 min)")
        try:
            self.client.images.build(
                path=CANNON_DEPLOYER_BUILD_PATH,
                tag=image_name,
                rm=True,
            )
            log.info("Built cannon deployer image %s successfully", image_name)
            if step_cb:
                step_cb("deployer_image_ready", "ok", image=image_name)
            return image_name
        except docker.errors.BuildError as exc:
            raise RuntimeError(
                f"Failed to build cannon deployer image {image_name}: {exc}"
            ) from exc

    def _deploy_contracts_sync(
        self, sandbox_id: str, network_name: str, contracts_version: str,
        anvil_container_id: str,
        step_cb=None,
    ) -> dict:
        """
        Run the cannon-deployer container in the Anvil container's network namespace
        (network_mode=container:<id>) so it reaches Anvil on localhost:8545.

        This avoids all Docker bridge DNS timing issues and hairpin NAT problems:
        the deployer inherits the Anvil container's network interfaces, sees Anvil
        on localhost just like the exec_run health check does, and routes outbound
        traffic (GitHub tarball download) through Anvil's bridge → host.

        The deployer container is removed after extraction (win or lose).
        Raises RuntimeError on non-zero exit or unparseable output.
        """
        import json as _json

        short         = sandbox_id[:8]
        deployer_name = f"rvp-deployer-{short}"

        image = self._ensure_cannon_deployer_image_sync(contracts_version, step_cb=step_cb)

        log.info(
            "Deploying rollups-contracts %s for sandbox %s via cannon "
            "(network_mode=container:%s, ANVIL_URL=http://localhost:8545)…",
            contracts_version, sandbox_id, anvil_container_id[:12],
        )

        container = self.client.containers.run(
            image,
            name=deployer_name,
            # Share Anvil's network namespace: deployer sees Anvil on localhost:8545.
            # No bridge DNS race, no hairpin NAT — identical to what exec_run uses.
            network_mode=f"container:{anvil_container_id}",
            environment={
                "CONTRACTS_VERSION": contracts_version,
                "ANVIL_URL":         "http://localhost:8545",
                "DEPLOYER_KEY":      DEPLOYER_KEY,
            },
            detach=True,
            remove=False,
            labels={"rvp.sandbox_id": sandbox_id, "rvp.component": "cannon-deployer"},
        )

        try:
            result = container.wait(timeout=CONTRACTS_DEPLOY_TIMEOUT)
            if result["StatusCode"] != 0:
                stderr = container.logs(
                    stdout=False, stderr=True
                ).decode("utf-8", errors="replace")
                raise RuntimeError(
                    f"Contract deployment exited {result['StatusCode']}. "
                    f"Last stderr: {stderr[-2000:]}"
                )

            stdout = container.logs(
                stdout=True, stderr=False
            ).decode("utf-8", errors="replace")

            # deploy-contracts.sh emits one JSON object as the final line of stdout
            json_line = None
            for line in reversed(stdout.splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    json_line = line
                    break

            if not json_line:
                raise RuntimeError(
                    f"Contract deployment produced no JSON on stdout. "
                    f"stdout: {stdout[-1000:]}"
                )

            try:
                addresses = _json.loads(json_line)
            except _json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Contract deployment stdout JSON parse failed: {exc}. "
                    f"json_line={json_line!r:.200} "
                    f"full_stdout={stdout[-2000:]}"
                ) from exc
            log.info(
                "Contracts deployed for sandbox %s: InputBox=%s AuthFactory=%s",
                sandbox_id,
                addresses.get("input_box", "?"),
                addresses.get("authority_factory", "?"),
            )
            return {
                "CARTESI_CONTRACTS_INPUT_BOX_ADDRESS":
                    addresses["input_box"],
                "CARTESI_CONTRACTS_AUTHORITY_FACTORY_ADDRESS":
                    addresses["authority_factory"],
                "CARTESI_CONTRACTS_APPLICATION_FACTORY_ADDRESS":
                    addresses["application_factory"],
                "CARTESI_CONTRACTS_SELF_HOSTED_APPLICATION_FACTORY_ADDRESS":
                    addresses["self_hosted_application_factory"],
            }
        finally:
            # Always remove the deployer (it has exited by this point)
            try:
                container.remove(force=True)
                log.debug("Removed cannon deployer container %s", deployer_name)
            except Exception as exc:
                log.debug("Could not remove deployer container %s: %s",
                          deployer_name, exc)

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
        contract_addresses: Optional[dict] = None,
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
                **(contract_addresses or DEVNET_ENV),
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

    # ── Service log streaming ──────────────────────────────────────────────────

    # Level patterns used to classify log lines from container stdout/stderr
    _LEVEL_ERROR_RE = re.compile(r'\b(ERROR|CRITICAL|FATAL|error|critical|fatal)\b')
    _LEVEL_WARN_RE  = re.compile(r'\b(WARN|WARNING|warn|warning)\b')
    _LEVEL_DEBUG_RE = re.compile(r'\b(DEBUG|TRACE|debug|trace)\b')

    def _classify_level(self, line: str) -> str:
        if self._LEVEL_ERROR_RE.search(line):
            return "error"
        if self._LEVEL_WARN_RE.search(line):
            return "warn"
        if self._LEVEL_DEBUG_RE.search(line):
            return "debug"
        return "info"

    def _stream_service_logs(
        self,
        container_id: str,
        component: str,
        sandbox_id: str,
        step_cb,
        log_buffer: Optional["LogBatchBuffer"],
        stop_event: threading.Event,
    ) -> None:
        """
        Background daemon thread: tail a container's logs and forward every line
        to log_buffer for batch persistence (log_batch RabbitMQ events → DB +
        live WebSocket broadcast).

        The thread retries automatically when the container restarts, which is
        important for services with restart_policy (e.g. evm-reader).  It exits
        cleanly when stop_event is set (sandbox teardown) or the container is
        removed from Docker entirely.

        Note: step_cb is intentionally NOT called here.  Calling it per-line
        would schedule a separate _publish_event coroutine on the event loop for
        every single log line from every container — potentially thousands per
        second during node startup — flooding the event loop and the shared
        RabbitMQ channel.  Log lines are delivered via log_buffer (batched) which
        is both efficient and the canonical persistence path.
        """
        short = sandbox_id[:8]
        log.debug("Log stream started for %s/%s (%s)", short, component, container_id[:12])

        since: Optional[float] = None   # Unix timestamp — set after first successful read

        while not stop_event.is_set():
            try:
                container = self.client.containers.get(container_id)
                kwargs: dict = {"stream": True, "follow": True}
                if since is not None:
                    # On retry after a restart: only fetch lines we haven't seen.
                    # Subtract a 2-second overlap to avoid missing lines that
                    # arrived in the last tick before the stream closed.
                    kwargs["since"] = max(0.0, since - 2.0)

                for raw_line in container.logs(**kwargs):
                    if stop_event.is_set():
                        break
                    since = time.time()
                    line  = raw_line.decode("utf-8", errors="replace").rstrip()
                    if not line:
                        continue
                    level = self._classify_level(line)
                    if log_buffer is not None:
                        try:
                            log_buffer.append(component, level, line[:2000])
                        except Exception:
                            pass

            except docker.errors.NotFound:
                # Container removed (sandbox teardown) — exit cleanly.
                log.debug("Container %s gone, log stream done for %s/%s",
                          container_id[:12], short, component)
                break
            except Exception as exc:
                if stop_event.is_set():
                    break
                # Stream disconnected — container is probably restarting.
                # Wait up to 2 s (interruptible by stop_event) then retry.
                log.debug("Log stream interrupted for %s/%s: %s — retrying",
                          short, component, exc)
                stop_event.wait(timeout=2.0)

        log.debug("Log stream done for %s/%s", short, component)

    # ── Teardown ───────────────────────────────────────────────────────────────

    def _teardown_sync(self, sandbox_id: str, container_ids: list[str], network_name: str,
                        per_sandbox_volume: Optional[str] = None):
        # Signal log-streaming threads to stop before we remove the containers
        stop_event = self._log_stop_events.pop(sandbox_id, None)
        if stop_event:
            stop_event.set()

        # Flush and stop the log batch buffer so no lines are lost during teardown
        log_buffer = self._log_buffers.pop(sandbox_id, None)
        if log_buffer is not None:
            try:
                log_buffer.stop()
            except Exception as exc:
                log.debug("LogBatchBuffer stop error for sandbox %s: %s", sandbox_id, exc)
        # Resolve per-sandbox volume from the in-process tracking dict if not passed in
        if not per_sandbox_volume:
            per_sandbox_volume = self._per_sandbox_volumes.pop(sandbox_id, None)
        else:
            self._per_sandbox_volumes.pop(sandbox_id, None)

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

        import shutil as _shutil
        import os as _os

        # Remove per-sandbox snapshot volume (only exists when app was built for this run)
        if per_sandbox_volume:
            try:
                vol = self.client.volumes.get(per_sandbox_volume)
                vol.remove(force=True)
                log.info("Removed per-sandbox snapshot volume %s", per_sandbox_volume)
            except Exception as exc:
                log.warning("Could not remove volume %s: %s", per_sandbox_volume, exc)

        # Remove app build directory (clone + .cartesi/image) if it still exists
        build_dir = _os.path.join(APP_BUILD_DIR, sandbox_id[:8])
        if _os.path.isdir(build_dir):
            try:
                _shutil.rmtree(build_dir, ignore_errors=True)
                log.info("Removed app build dir %s", build_dir)
            except Exception as exc:
                log.warning("Could not remove app build dir %s: %s", build_dir, exc)

        # Clean up compose file directory
        compose_dir = _os.path.join(COMPOSE_DIR, f"sbx-{sandbox_id[:8]}")
        try:
            _shutil.rmtree(compose_dir, ignore_errors=True)
        except Exception:
            pass
