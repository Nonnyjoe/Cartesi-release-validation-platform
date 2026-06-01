---
id: ws-max-retries-exceeded-v2
name: Exceeding WS max retries logs graceful failure (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, recovery, evm-reader, websocket, v2, phase9]
csv_ids: ["9.23"]
release_introduced: v2.0.0
component: evm-reader
priority: medium
timeout_seconds: 120
env_overrides:
  CARTESI_BLOCKCHAIN_WS_MAX_RETRIES: "1"
requires:
  - cartesi-node-v2
assertions:
  - type: log_contains
    service: evm-reader
    text: "max retries"
    timeout_seconds: 60
    comment: "verify graceful failure log when retries are exhausted"
---

## Description
CSV test 9.23 — Set `CARTESI_BLOCKCHAIN_WS_MAX_RETRIES=1` and kill the
WebSocket connection to verify the evm-reader logs a graceful failure without
panicking.

## Setup
This test requires:
1. `CARTESI_BLOCKCHAIN_WS_MAX_RETRIES=1` environment variable.
2. Disrupting the Anvil WS connection (e.g., network partition) to force reconnect failure.

## Steps
1. Start node with WS max retries = 1.
2. Disrupt the WS connection to exhaust retries.
3. Assert evm-reader logs "max retries" error.
4. Assert no panic/crash in logs.

## Expected Behaviour
- evm-reader fails gracefully after 1 retry.
- Error is logged clearly (no stack overflow or panic).
