---
id: config-log-level-warn-v2
name: CARTESI_LOG_LEVEL=warn suppresses info messages (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, config, logging, v2, phase14]
csv_ids: ["14.2"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 90
requires:
  - anvil
  - cartesi-node-v2
env_overrides:
  CARTESI_LOG_LEVEL: "warn"
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: log_contains
    component: advancer
    pattern: "WARN"
    timeout_seconds: 30
  - type: log_contains
    component: advancer
    pattern: "INFO"
    timeout_seconds: 10
    expect_absent: true
---

## Description
CSV test 14.2 — Set `CARTESI_LOG_LEVEL=warn` and verify info-level messages
are suppressed while warnings and errors are still visible.

## Setup
Start sandbox with `CARTESI_LOG_LEVEL=warn`.

## Steps
1. Submit a ping input.
2. Assert no INFO messages appear in advancer logs.
3. Assert WARN messages still appear if triggered.

## Expected Behaviour
- INFO-level messages suppressed at warn log level.
- WARN and ERROR messages still appear.
