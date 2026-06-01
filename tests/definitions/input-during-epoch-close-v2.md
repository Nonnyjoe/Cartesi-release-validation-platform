---
id: input-during-epoch-close-v2
name: Submit input while epoch is closing — race condition handled (v2.x)
version: 1
min_node_major_version: 2
tags: [inputs, edge-case, race-condition, v2, phase3]
csv_ids: ["3.19"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 180
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
    comment: "first input — triggers epoch processing"
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e6722 2c22736571223a327d"
    comment: "second input — submitted while first epoch is closing"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 2
---

## Description
CSV test 3.19 — Submit an input that closes the epoch, then immediately send
another input, verifying the race condition between epoch close and new input
arrival is handled correctly.

## Steps
1. Submit a first input that advances the epoch boundary.
2. Submit a second input immediately (race condition timing).
3. Assert both inputs are eventually indexed.

## Expected Behaviour
- Both inputs are processed correctly.
- No inputs are dropped during epoch close race condition.
- The second input is assigned to the new epoch.
