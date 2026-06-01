---
id: cloud-recovery-db-failure-v2
name: DB failure — shut down and restart recovers gracefully (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cloud, recovery, database, v2, phase9]
csv_ids: ["9.15"]
release_introduced: v2.0.0
component: advancer
priority: high
timeout_seconds: 300
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: service_restart
    service: database
    wait_healthy: true
    timeout: 90
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 9.15 — Simulate a database failure by stopping and restarting the
database container, and verify the node recovers gracefully.

## Steps
1. Submit a ping input.
2. Restart the database container.
3. Assert services reconnect to the DB.
4. Assert input is still indexed after recovery.

## Expected Behaviour
- Services handle DB disconnection gracefully (no panics).
- Services reconnect automatically when DB is restored.
- Data persists correctly after DB recovery.
