---
id: dirty-restart-database-v2
name: Restart database with active connections — data persisted and reconnections work (v2.x)
version: 1
min_node_major_version: 2
tags: [restart, dirty-restart, database, standalone, persistence, v2, phase9]
csv_ids: ["9.6"]
release_introduced: v2.0.0
component: database
priority: critical
timeout_seconds: 240
group: dirty_restart
suite_ids: [dirty_restart]
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a227265676973746572227d"
    comment: "create data before restart"
  - type: service_restart
    service: database
    verify_path: ""
    verify_timeout: 45
  - type: health_check
    service: advancer
    path: /readyz
    expect_status: 200
    wait_before_seconds: 10
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 1
---

## Description
CSV test 9.6 — Restart the database while services have active connections and
verify data is persisted and reconnections succeed.

## Steps
1. Submit a register action to create data.
2. Restart the database container (dirty, with active connections).
3. Wait for advancer to reconnect (/readyz).
4. Assert the previously submitted input is still in cartesi_listInputs.

## Expected Behaviour
- PostgreSQL WAL ensures data durability across restart.
- All services reconnect within 60s.
- Historical data is intact.
