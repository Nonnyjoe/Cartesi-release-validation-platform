---
id: jsonrpc-processed-input-count-v2
name: cartesi_getProcessedInputCount increments correctly (v2.x)
version: 1
min_node_major_version: 2
tags: [json-rpc, inputs, v2, phase8]
csv_ids: ["8.10"]
release_introduced: v2.0.0
component: jsonrpc
priority: medium
timeout_seconds: 120
requires:
  - cartesi-node-v2
assertions:
  - type: chain_tx
    payload: "0x7b22616374696f6e223a2270696e67227d"
  - type: json_rpc
    method: cartesi_getProcessedInputCount
    use_app_address: true
    expect_has_field: "data"
---

## Description
CSV test 8.10 — Verify `cartesi_getProcessedInputCount` returns a count that
increments after new inputs are processed.

## Steps
1. Submit a ping input.
2. Call `cartesi_getProcessedInputCount` with the app address.
3. Assert `processedInputCount` is present and > 0.

## Expected Behaviour
- `result.processedInputCount` is a non-negative integer that increments with each processed input.
