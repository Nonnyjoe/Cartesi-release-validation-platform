---
id: config-ws-max-retries-v2
name: CARTESI_BLOCKCHAIN_WS_MAX_RETRIES=1 causes early WS failure (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, config, evm-reader, v2, phase14]
csv_ids: ["14.6"]
release_introduced: v2.0.0
component: evm-reader
priority: medium
timeout_seconds: 120
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_BLOCKCHAIN_WS_MAX_RETRIES: "1"
assertions:
  - type: service_restart
    service: anvil
    wait_healthy: false
    comment: "stopping anvil forces a WS reconnect attempt"
  - type: log_contains
    service: evm-reader
    text: "max retries"
    timeout_seconds: 60
---

## Description
CSV test 14.6 — Set `CARTESI_BLOCKCHAIN_WS_MAX_RETRIES=1` to limit reconnect
budget, then kill the WS provider and verify the evm-reader fails fast after
just 1 retry attempt.

## Setup
Start sandbox with `CARTESI_BLOCKCHAIN_WS_MAX_RETRIES=1`.

## Steps
1. Stop Anvil to force a WebSocket disconnect.
2. Assert evm-reader logs "max retries" within the timeout.

## Expected Behaviour
- evm-reader exhausts retry budget (1 attempt) quickly.
- Clear error log indicating retry limit was reached.
