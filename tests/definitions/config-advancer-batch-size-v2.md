---
id: config-advancer-batch-size-v2
name: CARTESI_ADVANCER_INPUT_BATCH_SIZE=1 processes inputs individually (v2.x)
version: 1
min_node_major_version: 2
tags: [standalone, config, advancer, batch-size, v2, phase14]
csv_ids: ["14.5"]
release_introduced: v2.0.0
component: advancer
priority: medium
timeout_seconds: 120
env_overrides:
  CARTESI_ADVANCER_INPUT_BATCH_SIZE: "1"
requires:
  - anvil
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e6732227d"
  - type: json_rpc
    method: cartesi_listInputs
    use_app_address: true
    expect_count: 2
---

## Description
CSV test 14.5 — Set `CARTESI_ADVANCER_INPUT_BATCH_SIZE=1` and verify single-input
batching processes all inputs correctly.

## Setup
Start sandbox with `CARTESI_ADVANCER_INPUT_BATCH_SIZE=1`.

## Steps
1. Submit two inputs.
2. Verify both are processed (one at a time).

## Expected Behaviour
- Both inputs are processed correctly in single-input batches.
