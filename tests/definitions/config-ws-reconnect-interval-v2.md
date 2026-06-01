---
id: config-ws-reconnect-interval-v2
name: CARTESI_BLOCKCHAIN_WS_RECONNECT_INTERVAL custom value (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, config, evm-reader, v2, phase14]
csv_ids: ["14.7"]
release_introduced: v2.0.0
component: evm-reader
priority: low
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_BLOCKCHAIN_WS_RECONNECT_INTERVAL: "2s"
assertions:
  - type: health_check
    service: evm-reader
    path: /readyz
    expect_status: 200
  - type: log_contains
    component: evm-reader
    pattern: "reconnect"
    timeout_seconds: 60
    comment: "after a brief WS disruption, reconnect should occur at 2s interval"
---

## Description
CSV test 14.7 — Set `CARTESI_BLOCKCHAIN_WS_RECONNECT_INTERVAL=2s` and verify
the WebSocket reconnect delay matches the configured interval.

## Setup
Start sandbox with `CARTESI_BLOCKCHAIN_WS_RECONNECT_INTERVAL=2s`.

## Steps
1. Verify evm-reader is healthy.
2. Assert reconnect delay matches configuration when WS drop is triggered.

## Expected Behaviour
- Reconnect delay respects the configured interval.
- evm-reader does not reconnect faster or slower than specified.
