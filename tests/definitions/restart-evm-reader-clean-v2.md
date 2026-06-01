---
id: restart-evm-reader-clean-v2
name: Restart evm-reader immediately after boot — L1 RPC connection (v2.x)
version: 1
min_node_major_version: 2
tags: [restart, clean-restart, evm-reader, standalone, v2, phase2]
csv_ids: ["2.4"]
release_introduced: v2.0.0
component: evm-reader
priority: high
timeout_seconds: 120
group: restart
suite_ids: [restart]
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: service_restart
    service: evm-reader
    verify_path: /readyz
    verify_timeout: 60
  - type: health_check
    service: evm-reader
    path: /readyz
    expect_status: 200
---

## Description
CSV test 2.4 — Restart the evm-reader service immediately after a clean boot
and verify it re-establishes the L1 RPC connection.

## Steps
1. Restart the evm-reader container.
2. Poll /healthz until it returns HTTP 200.
3. Assert evm-reader is healthy (WS subscription re-established) within 60s.

## Expected Behaviour
- evm-reader restarts and reconnects to Anvil via WebSocket.
- /healthz returns 200 within 60s.
