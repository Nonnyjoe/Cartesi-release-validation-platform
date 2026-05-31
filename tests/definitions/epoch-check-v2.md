---
id: epoch-check-v2
name: Epoch Tracking (v2.x)
version: 1
min_node_major_version: 2
tags: [epoch, consensus, v2]
release_introduced: v2.0.0
component: validator
priority: high
timeout_seconds: 180
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0xdeadbeef"
  - type: json_rpc
    method: cartesi_listEpochs
    use_app_address: true
    expect_count: 1
---

## Description
Verifies the v2.x epoch tracking pipeline: send an input, then confirm at least
one epoch is tracked by the node via the JSON-RPC API.

## Steps
1. Submit a `0xdeadbeef` advance-state input via the InputBox contract.
2. Call `cartesi_listEpochs(app_address)` and assert at least 1 epoch is returned.
3. Scan advancer/validator logs for the word "epoch".

## Expected Behaviour
After an input is sent, the node tracks it within an epoch. `cartesi_listEpochs`
returns ≥1 epoch entries for the application.

## Notes
v2.x tracks epochs differently from v1.x — epochs are created per input batch
rather than by block-time. No need to advance Anvil blocks to close an epoch.
