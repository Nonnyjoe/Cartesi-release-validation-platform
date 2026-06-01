---
id: snapshot-per-input-v2
name: Configure per-input snapshots (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, persistence, snapshots, v2, phase9]
csv_ids: ["9.7"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
env_overrides:
  CARTESI_SNAPSHOT_POLICY: "every-input"
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e6732227d"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 2
---

## Description
CSV test 9.7 — Configure `CARTESI_SNAPSHOT_POLICY=every-input` and verify
per-input snapshots are taken correctly.

## Setup
Start sandbox with `CARTESI_SNAPSHOT_POLICY=every-input`.

## Steps
1. Submit two inputs.
2. Verify both inputs are processed normally.

## Expected Behaviour
- Both inputs are processed.
- Snapshot is taken after each input (verifiable via snapshot volume contents).
