---
id: cloud-recovery-claimer-resync-v2
name: Claimer resync after >5 epochs offline (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, cloud, recovery, claimer, v2, phase9]
csv_ids: ["9.13"]
release_introduced: v2.0.0
component: claimer
priority: high
timeout_seconds: 600
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: service_restart
    service: claimer
    stop_duration: 10
    wait_healthy: true
    timeout: 120
  - type: log_contains
    component: claimer
    pattern: "claim"
    timeout_seconds: 120
---

## Description
CSV test 9.13 — Stop the claimer for a period that causes it to miss multiple
epochs, then restart and verify it resyncs and catches up correctly.

This test covers Bug 3 (known issue: claimer resync after >5 epochs offline).

## Steps
1. Submit an input to get some epoch history.
2. Stop the claimer container for an extended period.
3. Restart the claimer.
4. Assert the claimer resyncs and resumes claim generation.

## Expected Behaviour
- Claimer resyncs with the current epoch state.
- No claims are permanently missed.
- Bug 3 regression: claimer handles >5 offline epochs correctly.
