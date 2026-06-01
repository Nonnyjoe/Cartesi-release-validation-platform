---
id: restart-database-clean-v2
name: Restart database immediately after boot — schema intact and services reconnect (v2.x)
version: 1
min_node_major_version: 2
tags: [restart, clean-restart, database, standalone, v2, phase2]
csv_ids: ["2.6"]
release_introduced: v2.0.0
component: database
priority: high
timeout_seconds: 180
group: restart
suite_ids: [restart]
requires:
  - cartesi-node-v2
assertions:
  - type: service_restart
    service: database
    verify_path: ""
    verify_timeout: 30
    comment: "Database restart — no HTTP healthz; wait for dependent services to reconnect"
  - type: health_check
    service: advancer
    path: /readyz
    expect_status: 200
    wait_before_seconds: 10
  - type: health_check
    service: jsonrpc
    path: /readyz
    expect_status: 200
  - type: json_rpc
    method: cartesi_listApplications
    use_app_address: false
---

## Description
CSV test 2.6 — Restart the database service immediately after a clean boot and
verify the schema is intact and dependent services reconnect successfully.

## Steps
1. Restart the database container.
2. Wait 10s for dependent services to detect the restart.
3. Poll advancer /readyz until HTTP 200 (DB connection re-established).
4. Verify jsonrpc-api /readyz returns 200.
5. Call cartesi_listApplications to confirm full stack is functional.

## Expected Behaviour
- Database restarts cleanly (schema migrations do not re-run on clean state).
- Advancer and jsonrpc-api reconnect to DB within 60s.
- JSON-RPC API is fully functional after reconnection.
