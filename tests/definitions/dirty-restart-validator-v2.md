---
id: dirty-restart-validator-v2
name: Restart validator with heavy history — state integrity maintained (v2.x)
version: 1
min_node_major_version: 2
tags: [restart, dirty-restart, validator, standalone, persistence, v2, phase9]
csv_ids: ["9.5"]
release_introduced: v2.0.0
component: validator
priority: high
timeout_seconds: 240
group: dirty_restart
suite_ids: [dirty_restart]
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: service_restart
    service: validator
    verify_path: /readyz
    verify_timeout: 90
  - type: health_check
    service: validator
    path: /readyz
    expect_status: 200
---

## Description
CSV test 9.5 — Restart the validator with existing epoch history and verify
state integrity is maintained.

## Steps
1. Submit an input to create epoch history.
2. Restart the validator container.
3. Verify validator recovers to healthy state.

## Expected Behaviour
- Validator re-validates from correct checkpoint after restart.
- No false-positive or false-negative claim submissions.
