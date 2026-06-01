---
id: snapshot-per-epoch-v2
name: Configure per-epoch snapshots (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, recovery, snapshot, v2, phase9]
csv_ids: ["9.8"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_SNAPSHOT_POLICY: "every-epoch"
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
  - type: log_contains
    service: advancer
    text: "snapshot"
    timeout_seconds: 60
---

## Description
CSV test 9.8 — Set `CARTESI_SNAPSHOT_POLICY=every-epoch` and verify the node
takes a snapshot at each epoch boundary.

## Setup
Start sandbox with `CARTESI_SNAPSHOT_POLICY=every-epoch`.

## Steps
1. Submit a ping input to advance the epoch.
2. Assert input is processed.
3. Assert advancer logs mention snapshot creation.

## Expected Behaviour
- Per-epoch snapshots are triggered automatically.
- Snapshot activity appears in advancer logs.
