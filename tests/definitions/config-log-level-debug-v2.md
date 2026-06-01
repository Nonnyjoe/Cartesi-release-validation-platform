---
id: config-log-level-debug-v2
name: CARTESI_LOG_LEVEL=debug produces debug messages (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, config, logging, v2, phase14]
csv_ids: ["14.1"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 60
env_overrides:
  CARTESI_LOG_LEVEL: "debug"
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: log_contains
    component: advancer
    pattern: "DEBUG"
    timeout_seconds: 30
---

## Description
CSV test 14.1 — Set `CARTESI_LOG_LEVEL=debug` and verify debug-level messages
appear across services.

## Setup
Start sandbox with `CARTESI_LOG_LEVEL=debug` environment variable.

## Steps
1. Submit a ping input.
2. Assert advancer logs contain DEBUG-level messages.

## Expected Behaviour
- DEBUG log level messages appear in service logs.
