---
id: restart-from-epoch-snapshot-v2
name: Restart from epoch snapshot — correct state restoration (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, recovery, snapshot, restart, v2, phase9]
csv_ids: ["9.9"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 180
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_SNAPSHOT_POLICY: "every-epoch"
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67222c22726567223a317d"
  - type: service_restart
    service: advancer
    wait_healthy: true
    timeout: 60
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 9.9 — Submit an input, take an epoch snapshot, restart the advancer,
and verify state is restored correctly from the snapshot.

## Setup
Start sandbox with `CARTESI_SNAPSHOT_POLICY=every-epoch`.

## Steps
1. Submit a ping input.
2. Restart the advancer container.
3. Assert the advancer recovers and the input is still in the DB.

## Expected Behaviour
- Advancer restarts and resumes from the epoch snapshot.
- No inputs are lost or double-processed.
