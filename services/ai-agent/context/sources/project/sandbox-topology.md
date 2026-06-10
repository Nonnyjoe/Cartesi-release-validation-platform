# Sandbox Topology

Each sandbox is a set of Docker containers named with a prefix derived from the sandbox UUID's
first 8 hex characters (`{short_id}`). For sandbox `02edd147-...`, containers are
`rvp-anvil-02edd147`, `rvp-jsonrpc-02edd147`, etc.

## v2.x containers (current default)

| Container | Internal Port | Role |
|---|---|---|
| `rvp-db-{short}` | 5432 | Rollups state Postgres (separate from the orchestrator's DB) |
| `rvp-anvil-{short}` | 8545 | Local Anvil EVM chain |
| `rvp-evm-reader-{short}` | — | `cartesi-rollups-evm-reader` — watches InputBox events |
| `rvp-advancer-{short}` | 10012 | `cartesi-rollups-advancer` — state advancement, inspect API |
| `rvp-validator-{short}` | — | `cartesi-rollups-validator` — finalizes epochs |
| `rvp-claimer-{short}` | — | `cartesi-rollups-claimer` — submits claims to Authority on-chain |
| `rvp-jsonrpc-{short}` | 10011 | `cartesi-rollups-jsonrpc-api` — `cartesi_*` JSON-RPC |
| `rvp-cli-{short}` | — | Long-running container with `cartesi-rollups-cli`, `cast`, `forge` |

External ports are allocated dynamically by the sandbox-manager; consult `get_node_state` or
the orchestrator DB (`orchestrator.sandboxes.runtime_meta`) to find them.

## v1.x (legacy single-container)

The v1.x `cartesi/rollups-node` image runs everything in one container `rvp-node-{short}` and
exposes HTTP on 5004 (input bridge) and 4000 (GraphQL).

## How to talk to each service

| Service | Tool | Endpoint shape |
|---|---|---|
| Anvil RPC | `run_cast_command`, `call_jsonrpc` (eth_*), `send_advance_input` | `http://rvp-anvil-{short}:8545` |
| Cartesi JSON-RPC | `call_jsonrpc` | `http://rvp-jsonrpc-{short}:10011` POST `{"jsonrpc":"2.0","method":"cartesi_*",...}` |
| Inspect API | `call_inspect` | `http://rvp-advancer-{short}:10012/inspect/{app}/{query}` |
| Container logs | `read_logs` | uses `docker logs rvp-{component}-{short}` under the hood |
| CLI commands | `run_cli_command` | `docker exec rvp-cli-{short} {binary} {args...}` |
| Restart a container | `restart_component` (chaos mode only) | `docker restart rvp-{component}-{short}` |

## When to use which

- **Submit an input** → `send_advance_input` (preferred; standard envelope) or `chain_tx`-style
  call via `trigger_test`. For raw transactions, use `run_cast_command`.
- **Read epoch state** → `call_jsonrpc` with `cartesi_listEpochs` or
  `cartesi_getLastAcceptedEpochIndex`.
- **Read input/output state** → `call_jsonrpc` with `cartesi_listInputs`, `cartesi_listOutputs`,
  `cartesi_getInput`, `cartesi_getOutput`.
- **Read a notice payload** → `call_jsonrpc` with `cartesi_getOutput`, decode `payload` hex.
- **Validate a voucher** → `verify_voucher` or `run_cli_command` with
  `cartesi-rollups-cli validate {app} {output_index}`.
- **Watch what a service is doing** → `read_logs` with the right component name.
- **Run an arbitrary CLI command** → `run_cli_command` with `cartesi-rollups-cli` (e.g.
  `address-book`, `deploy`, `register`, `inspect`).
