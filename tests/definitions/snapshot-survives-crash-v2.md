---
id: snapshot-survives-crash-v2
name: Snapshot survives unclean shutdown (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, recovery, snapshot, dirty-restart, v2, phase9]
csv_ids: ["9.10"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 180
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_SNAPSHOT_POLICY: "every-input"
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: service_restart
    service: advancer
    hard_kill: true
    wait_healthy: true
    timeout: 90
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 9.10 — Submit an input, hard-kill the advancer (simulating a crash),
and verify the snapshot persists and state is correctly restored on restart.

## Setup
Start sandbox with `CARTESI_SNAPSHOT_POLICY=every-input`.

## Steps
1. Submit a ping input.
2. Hard-kill the advancer (SIGKILL, not graceful).
3. Restart the advancer.
4. Assert input is still indexed and state is consistent.

## Expected Behaviour
- Snapshot persists on disk after unclean shutdown.
- Advancer recovers from snapshot on restart.
- No data corruption or state inconsistency.
