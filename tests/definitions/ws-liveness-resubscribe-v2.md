---
id: ws-liveness-resubscribe-v2
name: WS liveness timeout triggers evm-reader auto-resubscribe (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, recovery, evm-reader, websocket, v2, phase9]
csv_ids: ["9.22"]
release_introduced: v2.0.0
component: evm-reader
priority: medium
timeout_seconds: 180
group: chaos
suite_ids: [chaos]
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: health_check
    service: evm-reader
    path: /readyz
    expect_status: 200
  - type: log_contains
    service: evm-reader
    text: "resubscrib"
    timeout_seconds: 150
    comment: "verify resubscribe log appears after WS liveness timeout"
---

## Description
CSV test 9.22 — Simulate a WS liveness timeout (120s of no new blocks) and
verify the evm-reader resubscribes automatically without manual intervention.

## Setup
Pause block production for 120+ seconds (e.g., `cast rpc evm_setIntervalMining 0`).

## Steps
1. Stop Anvil's auto-mining to pause block production.
2. Wait 120+ seconds for the liveness timeout to fire.
3. Resume mining.
4. Assert evm-reader logs show resubscribe event.
5. Assert /healthz still returns 200.

## Expected Behaviour
- evm-reader detects liveness failure and resubscribes.
- No manual restart required.
- Subsequent inputs are processed normally.
