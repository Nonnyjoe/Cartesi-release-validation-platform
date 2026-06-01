---
id: restart-jsonrpc-clean-v2
name: Restart jsonrpc-api immediately after boot — API accessible (v2.x)
version: 1
min_node_major_version: 2
tags: [restart, clean-restart, jsonrpc, standalone, v2, phase2]
csv_ids: ["2.2"]
release_introduced: v2.0.0
component: jsonrpc
priority: high
timeout_seconds: 120
group: restart
suite_ids: [restart]
requires:
  - cartesi-node-v2
assertions:
  - type: service_restart
    service: jsonrpc
    verify_path: /readyz
    verify_timeout: 60
  - type: health_check
    service: jsonrpc
    path: /readyz
    expect_status: 200
  - type: json_rpc
    method: cartesi_listApplications
    use_app_address: false
---

## Description
CSV test 2.2 — Restart the jsonrpc-api service immediately after a clean boot
and verify the API is accessible.

## Steps
1. Restart the jsonrpc container.
2. Poll /healthz until it returns HTTP 200.
3. Call cartesi_listApplications to confirm API is functional.

## Expected Behaviour
- JSON-RPC API restarts cleanly.
- /healthz returns 200 within 60s.
- cartesi_listApplications succeeds after restart.
